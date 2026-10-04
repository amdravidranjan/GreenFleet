"""Green fleet deployment model: decision encoding, repair, and vectorised evaluation.

Decision per vessel i (10 bits = 10 qubits):
    route gene  (3 bits) -> idle or one of the routes compatible with the vessel's cargo kind
    speed gene  (3 bits) -> one of 8 slow-steaming levels (55 %..100 % of design speed)
    fuel gene   (3 bits) -> one of 8 fuels (repaired to VLSFO if not bunkerable on that route/year)
    shore power (1 bit)  -> retrofit / use cold ironing where the ports offer it

Objectives (all minimised, per year):
    f1 total cost  [M$]  = fuel + retrofit capex + opex + EU ETS + FuelEU penalty + IMO NZF levy
    f2 well-to-wake GHG [kt CO2e]
    f3 energy use  [kt VLSFO-equivalent]
Constraints: cargo demand and sailing frequency per route, per-vessel CII rating, optional fleet
emission cap. Handled with Deb's constraint-domination.
"""
from __future__ import annotations

import numpy as np

from .domain import (FUELS, ROUTES, VESSEL_TYPES, VT_IDX, SPEED_LEVELS, KIT_CAPEX_PER_KW, SHORE_POWER_KIT_USD,
                     CRF, ACTIVE_OPEX_USD, LAYUP_OPEX_USD, SHORE_POWER_USD_PER_KWH, VLSFO_LHV, EUR_USD,
                     CII_LABELS, Scenario, Vessel, interp_year)

N_BITS = 10
DOMESTIC = {"vizag", "haldia"}          # Indian coastal trades: outside IMO NZF scope
CARGO_FACTOR = 0.75
TRADING_DAYS = 350


class FleetModel:
    def __init__(self, fleet: list[Vessel], predictor, scenario: Scenario, fuel_table_cache: dict | None = None):
        self.fleet, self.pred, self.sc = fleet, predictor, scenario
        self.N, self.R = len(fleet), len(ROUTES)
        self._cache = fuel_table_cache if fuel_table_cache is not None else {}
        self._build_vessel_arrays()
        self._build_route_tables()
        self._build_scenario_vectors()

    # ------------------------------------------------------------------ static tables
    def _build_vessel_arrays(self):
        f = self.fleet
        self.dwt = np.array([v.dwt for v in f], float)
        self.vd = np.array([v.design_speed for v in f], float)
        self.mcr = np.array([v.mcr_kw for v in f], float)
        vt = [VESSEL_TYPES[VT_IDX[v.type]] for v in f]
        self.kind = [t.kind for t in vt]
        self.cii_req0 = np.array([t.cii_a * v.dwt ** (-t.cii_c) for t, v in zip(vt, f)])
        self.cii_d = np.array([t.cii_d for t in vt])
        opts = []
        for i in range(self.N):
            compat = [0] + [r + 1 for r, rt in enumerate(ROUTES) if self.kind[i] in rt.kinds]
            opts.append([compat[k % len(compat)] for k in range(8)])
        self.route_opts = np.array(opts)                                   # (N, 8)
        self.COMPAT = np.array([[r == 0 or r in o for r in range(self.R + 1)] for o in opts])

    def _fuel_per_day(self):
        key = tuple(sorted(self.sc.weather_hs_add.items()))
        if key in self._cache:
            return self._cache[key]
        N, R, S = self.N, self.R, len(SPEED_LEVELS)
        drafts, angles = (0.95, 0.5), (0.0, 90.0, 180.0)
        cols = {k: [] for k in ("mcr", "design_speed", "speed", "draft_ratio", "hs", "wind", "wind_angle",
                                "days_dd", "age", "aux_kw")}
        for i, v in enumerate(self.fleet):
            for r, rt in enumerate(ROUTES):
                hs = rt.hs_mean + self.sc.weather_hs_add.get(rt.key, 0.0)
                wind = rt.wind_mean + 3.0 * self.sc.weather_hs_add.get(rt.key, 0.0)
                for s in SPEED_LEVELS:
                    for d in drafts:
                        for a in angles:
                            for k, val in (("mcr", v.mcr_kw), ("design_speed", v.design_speed),
                                           ("speed", v.design_speed * s), ("draft_ratio", d), ("hs", hs),
                                           ("wind", wind), ("wind_angle", a), ("days_dd", v.days_since_drydock),
                                           ("age", v.age), ("aux_kw", v.aux_sea_kw)):
                                cols[k].append(val)
        pred = self.pred.predict(**{k: np.array(v) for k, v in cols.items()})
        table = pred.reshape(N, R, S, len(drafts) * len(angles)).mean(-1)
        self._cache[key] = table
        return table

    def _build_route_tables(self):
        N, R, S = self.N, self.R, len(SPEED_LEVELS)
        fpd = self._fuel_per_day()                                         # t VLSFO-eq / sea day
        shp = (N, R + 1, S)
        self.TRIPS, self.E_SEA, self.E_PORT, self.PORT_KWH, self.NM, self.CARGO, self.FPD = (np.zeros(shp) for _ in range(7))
        for r, rt in enumerate(ROUTES):
            v = self.vd[:, None] * SPEED_LEVELS[None, :]
            sea_rt = 2 * rt.distance_nm / (24 * v)
            trips = TRADING_DAYS / (sea_rt + rt.port_days)
            aux_port = np.array([x.aux_port_kw for x in self.fleet])[:, None]
            self.TRIPS[:, r + 1] = trips
            self.FPD[:, r + 1] = fpd[:, r]
            self.E_SEA[:, r + 1] = trips * sea_rt * fpd[:, r] * VLSFO_LHV * 1000
            self.PORT_KWH[:, r + 1] = trips * rt.port_days * aux_port * 24
            self.E_PORT[:, r + 1] = self.PORT_KWH[:, r + 1] * 220e-6 * VLSFO_LHV * 1000
            self.NM[:, r + 1] = trips * 2 * rt.distance_nm
            self.CARGO[:, r + 1] = trips * self.dwt[:, None] * CARGO_FACTOR / 1000       # kt / yr
        self.demand = np.array([rt.demand_kt for rt in ROUTES]) * self.sc.demand_mult
        self.min_sail = np.array([rt.min_sailings for rt in ROUTES], float)

    # ------------------------------------------------------------------ scenario vectors
    def _build_scenario_vectors(self):
        sc, y = self.sc, self.sc.year
        self.PRICE_MJ = np.array([sc.fuel_price(f) / (f.lhv * 1000) for f in FUELS])
        self.WTW = np.array([f.wtw for f in FUELS])
        self.TTW = np.array([f.ttw for f in FUELS])
        self.CF_MJ = np.array([f.cf / (f.lhv * 1000) for f in FUELS])      # t CO2 per MJ
        self.PILOT = np.array([f.pilot for f in FUELS])
        self.EFF = np.array([f.eff for f in FUELS])
        av = np.ones((self.R + 1, len(FUELS)), bool)
        for r, rt in enumerate(ROUTES):
            for k, f in enumerate(FUELS):
                av[r + 1, k] = (rt.fuels_from.get(f.key, 9999) <= y and f.available_from <= y
                                and f.key not in sc.banned_fuels and rt.distance_nm <= f.max_route_nm)
        self.AVAIL = av
        cov, grid = np.zeros(self.R + 1), np.zeros(self.R + 1)
        for r, rt in enumerate(ROUTES):
            ports = list(rt.shore_power_from)
            on = [p for p in ports if rt.shore_power_from[p] <= y]
            cov[r + 1] = len(on) / len(ports)
            grid[r + 1] = np.mean([interp_year(rt.grid[p], y) for p in on]) if on else 0.0
        self.SP_COV, self.GRID = cov, grid                                   # kg CO2e / kWh
        self.EU = np.array([0.0] + [rt.eu_share for rt in ROUTES])
        self.INTL = np.array([0.0] + [0.0 if rt.key in DOMESTIC else 1.0 for rt in ROUTES])
        self.KIT_CAPEX = np.zeros((self.N, len(FUELS)))
        for i, v in enumerate(self.fleet):
            for k, f in enumerate(FUELS):
                if f.kit not in v.kits:
                    self.KIT_CAPEX[i, k] = KIT_CAPEX_PER_KW[f.kit] * v.mcr_kw * CRF
        self.SP_CAPEX = np.array([0.0 if v.shore_power else SHORE_POWER_KIT_USD * CRF for v in self.fleet])
        self.ets = sc.ets_usd() * (0.7 if y == 2025 else 1.0)
        self.fueleu_target = sc.fueleu_target()
        self.imo_base, self.imo_direct = sc.imo_targets()
        self.cii_req = self.cii_req0 * (1 - sc.cii_reduction())
        self.min_rating = CII_LABELS.index(sc.min_cii)
        self.emission_cap = None

    # ------------------------------------------------------------------ encoding
    @staticmethod
    def bits_to_int(bits: np.ndarray) -> np.ndarray:
        """bits (..., N, 10) -> genes (..., N, 4) [route_gene, speed, fuel, shore]."""
        w = np.array([4, 2, 1])
        return np.stack([bits[..., 0:3] @ w, bits[..., 3:6] @ w, bits[..., 6:9] @ w, bits[..., 9]], -1).astype(int)

    def decode(self, genes: np.ndarray):
        genes = np.asarray(genes).reshape(-1, self.N, 4)
        ii = np.arange(self.N)[None, :]
        route = self.route_opts[ii, genes[..., 0] % 8]
        speed = genes[..., 1] % 8
        fuel = genes[..., 2] % 8
        sp = genes[..., 3] % 2
        route, speed = self._repair(route, speed)
        fuel = np.where(self.AVAIL[route, fuel], fuel, 0)
        return route, speed, fuel, sp

    def _repair(self, route, speed):
        """Deterministic capacity repair (same for every algorithm): for each route short of cargo
        or sailings, first speed up its own ships one level at a time, then pull in idle compatible
        ships (largest first). Keeps decoding a pure function of the genes."""
        route, speed = route.copy(), speed.copy()
        P = route.shape[0]
        ii = np.broadcast_to(np.arange(self.N), route.shape)
        rows = np.arange(P)
        for r in range(1, self.R + 1):
            need_c, need_s = self.demand[r - 1], self.min_sail[r - 1]
            compat = self.COMPAT[:, r][None, :]
            for _ in range(3 * self.N):
                on = route == r
                cap = (self.CARGO[ii, r, speed] * on).sum(1)
                sail = (self.TRIPS[ii, r, speed] * on).sum(1)
                short = (cap < need_c) | (sail < need_s)
                if not short.any():
                    break
                idle = (route == 0) & compat
                slow = on & (speed < 7)
                has_idle, has_slow = idle.any(1), slow.any(1)
                use_speed = short & has_slow & (~has_idle | (cap >= 0.9 * need_c))
                use_idle = short & ~use_speed & has_idle
                if not (use_speed.any() or use_idle.any()):
                    break
                j = np.argmin(np.where(slow, speed, 99), 1)
                speed[rows[use_speed], j[use_speed]] += 1
                k = np.argmax(np.where(idle, self.dwt[None, :], -1), 1)
                route[rows[use_idle], k[use_idle]] = r
        return route, speed

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, genes: np.ndarray, detail: bool = False):
        route, speed, fuel, sp = self.decode(genes)
        ii = np.arange(self.N)[None, :]
        active = route > 0
        trips = self.TRIPS[ii, route, speed]
        cov = self.SP_COV[route] * sp
        e_port_fuel = self.E_PORT[ii, route, speed] * (1 - cov)
        kwh_grid = self.PORT_KWH[ii, route, speed] * cov
        E = (self.E_SEA[ii, route, speed] + e_port_fuel) * self.EFF[fuel]
        e_main, e_pilot = E * (1 - self.PILOT[fuel]), E * self.PILOT[fuel]
        fuel_cost = e_main * self.PRICE_MJ[fuel] + e_pilot * self.PRICE_MJ[0]
        wtw_t = (e_main * self.WTW[fuel] + e_pilot * self.WTW[0]) / 1e6 + kwh_grid * self.GRID[route] / 1000
        ttw_t = (e_main * self.TTW[fuel] + e_pilot * self.TTW[0]) / 1e6
        co2_cii_t = e_main * self.CF_MJ[fuel] + e_pilot * self.CF_MJ[0]
        e_all = E + kwh_grid * 3.6
        intensity = np.where(e_all > 0, wtw_t * 1e6 / np.maximum(e_all, 1), 0.0)
        eu = self.EU[route]
        ets = eu * ttw_t * self.ets
        fueleu = eu * np.maximum(intensity - self.fueleu_target, 0) * e_all / (np.maximum(intensity, 1) * 41000) * 2400 * EUR_USD
        intl = self.INTL[route]
        tier2 = np.maximum(intensity - self.imo_base, 0) * e_all / 1e6
        tier1 = np.maximum(intensity - self.imo_direct, 0) * e_all / 1e6 - tier2
        imo = intl * (tier2 * self.sc.imo_tier2_usd + np.maximum(tier1, 0) * self.sc.imo_tier1_usd)
        capex = active * (self.KIT_CAPEX[ii, fuel] + sp * self.SP_CAPEX[None, :])
        opex = np.where(active, ACTIVE_OPEX_USD, LAYUP_OPEX_USD)
        shore_cost = kwh_grid * SHORE_POWER_USD_PER_KWH
        cost_v = fuel_cost + capex + opex + ets + fueleu + imo + shore_cost

        nm = self.NM[ii, route, speed]
        attained = np.where(active, co2_cii_t * 1e6 / (self.dwt * np.maximum(nm, 1)), 0.0)
        ratio = attained / self.cii_req
        rating = (ratio[..., None] > self.cii_d[None]).sum(-1)
        cii_viol = (active & (rating > self.min_rating)).sum(-1)

        cargo = self.CARGO[ii, route, speed]
        P = route.shape[0]
        cap_r, sail_r = np.zeros((P, self.R)), np.zeros((P, self.R))
        for r in range(self.R):
            m = route == r + 1
            cap_r[:, r] = (cargo * m).sum(-1)
            sail_r[:, r] = (trips * m).sum(-1)
        viol = (np.maximum(1 - cap_r / self.demand, 0).sum(-1) + np.maximum(1 - sail_r / self.min_sail, 0).sum(-1)
                + 0.15 * cii_viol)
        F = np.stack([cost_v.sum(-1) / 1e6, wtw_t.sum(-1) / 1e3, E.sum(-1) / VLSFO_LHV / 1e6], -1)
        if self.emission_cap is not None:
            viol = viol + np.maximum(F[:, 1] / self.emission_cap - 1, 0)
        if not detail:
            return F, viol
        return F, viol, dict(route=route, speed=speed, fuel=fuel, sp=sp * (self.SP_COV[route] > 0), trips=trips,
                             fuel_cost=fuel_cost, capex=capex, opex=opex, ets=ets, fueleu=fueleu, imo=imo,
                             shore_cost=shore_cost, wtw=wtw_t, ttw=ttw_t, energy=E, rating=rating, cii_ratio=ratio,
                             cargo=cargo, cap_r=cap_r, sail_r=sail_r, intensity=intensity, cost=cost_v,
                             fpd=self.FPD[ii, route, speed], nm=nm)

    # ------------------------------------------------------------------ business-as-usual plan
    def bau_genes(self) -> np.ndarray:
        """Today's operations: native fuel, 85 % design speed, no shore power, greedy assignment."""
        genes = np.zeros((self.N, 4), int)
        s85 = int(np.argmin(np.abs(SPEED_LEVELS - 0.85)))
        genes[:, 1] = s85
        for i, v in enumerate(self.fleet):
            genes[i, 2] = 1 if "lng" in v.kits and self.AVAIL[1:, 1].any() else 0
        cargo = self.CARGO[:, :, s85]
        trips = self.TRIPS[:, :, s85]
        free = set(range(self.N))
        for r in np.argsort([-rt.distance_nm for rt in ROUTES]) + 1:
            cap = sail = 0.0
            while cap < self.demand[r - 1] * 1.02 or sail < self.min_sail[r - 1]:
                cands = [i for i in free if r in self.route_opts[i]]
                if not cands:
                    break
                i = max(cands, key=lambda k: self.dwt[k])
                free.discard(i)
                genes[i, 0] = int(np.where(self.route_opts[i] == r)[0][0])
                cap += cargo[i, r]
                sail += trips[i, r]
                if genes[i, 2] == 1 and not self.AVAIL[r, 1]:
                    genes[i, 2] = 0
        return genes

    def plan(self, genes: np.ndarray) -> dict:
        """Human-readable plan for one solution."""
        F, viol, d = self.evaluate(genes[None], detail=True)
        vessels = []
        for i, v in enumerate(self.fleet):
            r = int(d["route"][0, i])
            vessels.append({
                "id": v.id, "name": v.name, "type": v.type, "dwt": v.dwt,
                "route": ROUTES[r - 1].key if r else None,
                "speed_kn": round(float(self.vd[i] * SPEED_LEVELS[d["speed"][0, i]]), 1) if r else 0.0,
                "speed_pct": round(float(SPEED_LEVELS[d["speed"][0, i]]) * 100) if r else 0,
                "fuel": FUELS[int(d["fuel"][0, i])].key if r else None,
                "shore_power": bool(d["sp"][0, i]) if r else False,
                "trips": round(float(d["trips"][0, i]), 1),
                "fuel_t_per_day": round(float(d["fpd"][0, i]), 1),
                "cost_musd": round(float(d["cost"][0, i]) / 1e6, 3),
                "wtw_kt": round(float(d["wtw"][0, i]) / 1e3, 3),
                "cii": CII_LABELS[int(d["rating"][0, i])] if r else None,
                "cii_ratio": round(float(d["cii_ratio"][0, i]), 3),
                "intensity": round(float(d["intensity"][0, i]), 1),
            })
        routes = [{"key": rt.key, "demand_kt": float(self.demand[r]), "capacity_kt": round(float(d["cap_r"][0, r])),
                   "sailings": round(float(d["sail_r"][0, r]), 1), "min_sailings": int(self.min_sail[r])}
                  for r, rt in enumerate(ROUTES)]
        tot = lambda k: float(d[k][0].sum())
        mix = {}
        for f in FUELS:
            mask = (d["fuel"][0] == FUELS.index(f)) & (d["route"][0] > 0)
            mix[f.key] = float(d["energy"][0][mask].sum() / max(d["energy"][0][d["route"][0] > 0].sum(), 1))
        return {
            "objectives": {"cost_musd": float(F[0, 0]), "wtw_kt": float(F[0, 1]), "energy_kt": float(F[0, 2])},
            "violation": float(viol[0]),
            "cost_breakdown": {k: tot(k) / 1e6 for k in ("fuel_cost", "capex", "opex", "ets", "fueleu", "imo", "shore_cost")},
            "fuel_mix": mix, "vessels": vessels, "routes": routes,
            "cii_counts": {lab: int(((d["rating"][0] == j) & (d["route"][0] > 0)).sum()) for j, lab in enumerate(CII_LABELS)},
            "genes": genes.tolist(),
        }
