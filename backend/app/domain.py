"""Domain data: fuels, vessel types, routes, fleet and year-dependent policy scenarios.

All figures are documented engineering approximations (IMO 4th GHG Study, FuelEU Maritime
Annex II defaults, IMO CII guidelines G1-G4, MEPC 83 Net-Zero Framework draft). They are
scenario assumptions, deliberately centralised here so they can be audited and changed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

# ----------------------------------------------------------------------------------------
# Fuels (exactly 8 -> encoded with 3 qubits per vessel)
# ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Fuel:
    key: str
    name: str
    lhv: float            # MJ/kg
    wtt: float            # well-to-tank gCO2e/MJ
    ttw: float            # tank-to-wake gCO2e/MJ (incl. CH4 slip / N2O)
    cf: float             # CII carbon factor, t CO2 / t fuel (TtW CO2 only, as regulation counts it)
    kit: str              # engine/tank retrofit family
    pilot: float          # share of energy from VLSFO pilot fuel
    eff: float            # energy multiplier vs diesel engine (fuel cell < 1)
    price: dict           # $/t by year (interpolated)
    available_from: int
    max_route_nm: float = 1e9
    color: str = "#888"
    origin: str = ""

    @property
    def wtw(self) -> float:
        return self.wtt + self.ttw


FUELS: list[Fuel] = [
    Fuel("vlsfo", "VLSFO", 40.2, 13.2, 78.2, 3.114, "diesel", 0.0, 1.00,
         {2025: 600, 2050: 650}, 2020, color="#6b7280", origin="Crude oil refining"),
    Fuel("lng", "LNG", 49.1, 18.5, 70.7, 2.750, "lng", 0.01, 1.00,
         {2025: 620, 2050: 660}, 2020, color="#60a5fa", origin="Fossil gas, liquefied (3.1% methane slip)"),
    Fuel("biolng", "Bio-LNG", 49.1, 5.0, 14.7, 2.750, "lng", 0.01, 1.00,
         {2025: 1500, 2035: 1250, 2050: 1100}, 2025, color="#22d3ee", origin="Biomethane from waste, liquefied"),
    Fuel("meoh", "Methanol (grey)", 19.9, 31.3, 69.1, 1.375, "methanol", 0.03, 1.00,
         {2025: 400, 2050: 420}, 2024, color="#a78bfa", origin="Natural-gas reforming"),
    Fuel("emeoh", "e-Methanol", 19.9, 9.0, 1.0, 1.375, "methanol", 0.03, 1.00,
         {2025: 1900, 2030: 1500, 2040: 1100, 2050: 900}, 2025, color="#c084fc",
         origin="Green H2 + captured CO2"),
    Fuel("nh3", "Ammonia (grey)", 18.6, 121.0, 5.0, 0.0, "ammonia", 0.07, 1.03,
         {2025: 450, 2050: 480}, 2026, color="#fbbf24", origin="Steam-methane reforming (Haber-Bosch)"),
    Fuel("gnh3", "Green Ammonia", 18.6, 8.0, 5.0, 0.0, "ammonia", 0.07, 1.03,
         {2025: 1100, 2030: 900, 2040: 700, 2050: 600}, 2027, color="#34d399",
         origin="Electrolytic H2 (renewables) + air N2"),
    Fuel("h2", "Green H2 (LH2)", 120.0, 12.0, 0.0, 0.0, "hydrogen", 0.0, 0.88,
         {2025: 8000, 2030: 6000, 2040: 4200, 2050: 3500}, 2026, max_route_nm=900,
         color="#f472b6", origin="Electrolysis + liquefaction, fuel cell"),
]
FUEL_IDX = {f.key: i for i, f in enumerate(FUELS)}
N_FUELS = len(FUELS)

KIT_CAPEX_PER_KW = {"diesel": 0.0, "lng": 900.0, "methanol": 400.0, "ammonia": 700.0, "hydrogen": 1800.0}
SHORE_POWER_KIT_USD = 750_000.0
CRF = 0.1175                      # capital recovery factor, 10 % over 20 years
ACTIVE_OPEX_USD = 2_600_000.0     # crew, maintenance, insurance per trading vessel-year
LAYUP_OPEX_USD = 450_000.0
SHORE_POWER_USD_PER_KWH = 0.12
VLSFO_LHV = 40.2
REF_GHG_2008 = 93.3               # IMO NZF reference intensity, gCO2e/MJ
FUELEU_REF = 91.16                # FuelEU reference intensity, gCO2e/MJ

# ----------------------------------------------------------------------------------------
# Vessel types
# ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class VesselType:
    key: str
    name: str
    kind: str                     # container | bulk | tanker
    dwt: tuple                    # (low, high)
    design_speed: float           # knots
    mcr_per_dwt: float            # kW per t DWT (scales MCR)
    aux_sea_kw: float
    aux_port_kw: float
    cii_a: float
    cii_c: float
    cii_d: tuple                  # rating boundaries d1..d4


VESSEL_TYPES: list[VesselType] = [
    VesselType("feeder", "Container feeder", "container", (20000, 26000), 18.5, 0.55, 900, 700,
               1984, 0.489, (0.83, 0.94, 1.07, 1.19)),
    VesselType("panamax", "Container Panamax", "container", (55000, 65000), 21.0, 0.50, 1500, 1200,
               1984, 0.489, (0.83, 0.94, 1.07, 1.19)),
    VesselType("handy", "Handysize bulker", "bulk", (32000, 38000), 14.0, 0.21, 500, 400,
               4745, 0.622, (0.86, 0.94, 1.06, 1.18)),
    VesselType("supra", "Supramax bulker", "bulk", (55000, 61000), 14.5, 0.165, 600, 450,
               4745, 0.622, (0.86, 0.94, 1.06, 1.18)),
    VesselType("mr", "MR product tanker", "tanker", (47000, 52000), 14.5, 0.18, 700, 900,
               5247, 0.610, (0.82, 0.93, 1.08, 1.28)),
]
VT_IDX = {v.key: i for i, v in enumerate(VESSEL_TYPES)}
CII_LABELS = ["A", "B", "C", "D", "E"]

# ----------------------------------------------------------------------------------------
# Routes (Chennai hub network) -- max 7 so that route+idle fits 3 qubits
# ----------------------------------------------------------------------------------------
CHENNAI = (13.10, 80.30)

@dataclass
class Route:
    key: str
    name: str
    dest: str
    kinds: tuple
    distance_nm: float
    port_days: float              # per round trip, both ends
    demand_kt: float              # cargo per year (one direction, laden)
    min_sailings: int
    hs_mean: float                # significant wave height, m
    wind_mean: float              # m/s
    eu_share: float               # share of emissions under EU ETS / FuelEU
    fuels_from: dict              # fuel key -> first year bunkering available
    shore_power_from: dict        # port -> first year available (Chennai + destination)
    grid: dict                    # port -> {year: kgCO2e/kWh}
    waypoints: list = field(default_factory=list)   # [lat, lon] one-way

ALL_FUELS_HUB = {"vlsfo": 2020, "lng": 2020, "biolng": 2025, "meoh": 2024, "emeoh": 2025,
                 "nh3": 2026, "gnh3": 2027, "h2": 2028}
INDIA_FUELS = {"vlsfo": 2020, "lng": 2027, "biolng": 2030, "meoh": 2026, "emeoh": 2028,
               "nh3": 2028, "gnh3": 2030, "h2": 2030}
INDIA_GRID = {2025: 0.71, 2030: 0.55, 2035: 0.42, 2040: 0.32, 2050: 0.15}

ROUTES: list[Route] = [
    Route("colombo", "Chennai - Colombo", "Colombo", ("container",), 590, 2.0, 4300, 104, 1.6, 7.0, 0.0,
          {**INDIA_FUELS, "lng": 2026}, {"Chennai": 2027, "Colombo": 2030},
          {"Chennai": INDIA_GRID, "Colombo": {2025: 0.50, 2050: 0.20}},
          [[13.10, 80.30], [11.0, 81.0], [8.5, 82.0], [6.6, 81.9], [5.75, 80.6], [6.3, 79.7], [6.95, 79.84]]),
    Route("singapore", "Chennai - Singapore", "Singapore", ("container",), 1590, 2.5, 3900, 52, 1.5, 6.5, 0.0,
          ALL_FUELS_HUB, {"Chennai": 2027, "Singapore": 2025},
          {"Chennai": INDIA_GRID, "Singapore": {2025: 0.41, 2050: 0.25}},
          [[13.10, 80.30], [10.5, 86.0], [6.2, 94.8], [4.2, 98.4], [2.6, 101.2], [1.25, 103.8]]),
    Route("klang", "Chennai - Port Klang", "Port Klang", ("container",), 1450, 2.5, 3100, 52, 1.4, 6.0, 0.0,
          {**INDIA_FUELS, "lng": 2025, "biolng": 2028, "meoh": 2025}, {"Chennai": 2027, "Port Klang": 2029},
          {"Chennai": INDIA_GRID, "Port Klang": {2025: 0.58, 2050: 0.25}},
          [[13.10, 80.30], [10.5, 86.0], [6.2, 94.8], [4.2, 98.4], [3.0, 101.3]]),
    Route("rotterdam", "Chennai - Rotterdam", "Rotterdam", ("container",), 7150, 4.0, 1900, 26, 2.2, 9.0, 0.5,
          ALL_FUELS_HUB, {"Chennai": 2027, "Rotterdam": 2025},
          {"Chennai": INDIA_GRID, "Rotterdam": {2025: 0.30, 2035: 0.12, 2050: 0.03}},
          [[13.10, 80.30], [8.5, 82.0], [5.75, 80.6], [7.0, 76.5], [11.5, 62.0], [12.6, 51.8], [12.3, 45.0],
           [12.6, 43.4], [15.0, 41.8], [20.0, 38.5], [27.5, 34.0], [29.9, 32.55], [31.6, 32.3],
           [33.5, 28.0], [36.0, 15.2], [37.8, 10.3], [37.5, 1.0], [36.0, -4.5], [35.95, -5.6],
           [36.4, -7.5], [37.0, -9.4], [43.3, -9.8], [48.6, -5.7], [50.1, -1.0], [51.0, 1.6], [51.95, 3.95]]),
    Route("vizag", "Chennai - Visakhapatnam", "Visakhapatnam", ("bulk",), 340, 3.0, 12000, 52, 1.4, 6.5, 0.0,
          INDIA_FUELS, {"Chennai": 2027, "Visakhapatnam": 2028},
          {"Chennai": INDIA_GRID, "Visakhapatnam": INDIA_GRID},
          [[13.10, 80.30], [14.8, 80.6], [16.2, 81.7], [17.0, 82.7], [17.68, 83.30]]),
    Route("jebelali", "Chennai - Jebel Ali", "Jebel Ali", ("tanker",), 2600, 4.0, 3900, 26, 1.9, 8.0, 0.0,
          {**INDIA_FUELS, "lng": 2025, "meoh": 2025}, {"Chennai": 2027, "Jebel Ali": 2030},
          {"Chennai": INDIA_GRID, "Jebel Ali": {2025: 0.45, 2050: 0.20}},
          [[13.10, 80.30], [8.5, 82.0], [5.75, 80.6], [7.0, 76.5], [15.0, 66.0], [22.8, 60.3],
           [25.2, 57.4], [26.5, 56.6], [26.1, 55.6], [25.02, 55.03]]),
    Route("haldia", "Chennai - Haldia", "Haldia", ("bulk",), 780, 4.0, 7500, 26, 1.6, 7.0, 0.0,
          INDIA_FUELS, {"Chennai": 2027, "Haldia": 2031},
          {"Chennai": INDIA_GRID, "Haldia": INDIA_GRID},
          [[13.10, 80.30], [15.5, 81.2], [18.5, 86.2], [21.0, 88.2], [22.03, 88.06]]),
]
N_ROUTES = len(ROUTES)
SPEED_LEVELS = np.linspace(0.55, 1.0, 8)          # fraction of design speed (3 qubits)


def interp_year(table: dict, year: float) -> float:
    ys = sorted(table)
    return float(np.interp(year, ys, [table[y] for y in ys]))


def step_year(table: dict, year: float) -> float:
    val = table[min(table)]
    for y in sorted(table):
        if year >= y:
            val = table[y]
    return val


# ----------------------------------------------------------------------------------------
# Policy scenario for a given year
# ----------------------------------------------------------------------------------------
ETS_EUR = {2025: 75, 2030: 130, 2035: 160, 2040: 190, 2050: 250}
FUELEU_RED = {2025: 0.02, 2030: 0.06, 2035: 0.145, 2040: 0.31, 2045: 0.62, 2050: 0.80}
IMO_BASE_RED = {2027: 0.0, 2028: 0.04, 2030: 0.08, 2035: 0.30, 2040: 0.65, 2050: 0.95}
IMO_DIRECT_RED = {2027: 0.0, 2028: 0.17, 2030: 0.21, 2035: 0.43, 2040: 0.80, 2050: 1.0}
CII_Z = {2023: 5, 2024: 7, 2025: 9, 2026: 11, 2030: 21.5, 2040: 40, 2050: 60}
EUR_USD = 1.08


@dataclass
class Scenario:
    year: int = 2030
    ets_eur: float | None = None           # override EU ETS price
    imo_nzf: bool = True
    imo_tier2_usd: float = 380.0
    imo_tier1_usd: float = 100.0
    fuel_price_mult: dict = field(default_factory=dict)   # fuel key -> multiplier
    demand_mult: float = 1.0
    emission_cap_pct: float | None = None  # % of baseline WtW allowed
    min_cii: str = "C"
    banned_fuels: list = field(default_factory=list)
    weather_hs_add: dict = field(default_factory=dict)    # route key -> added Hs (storm mode)

    def ets_usd(self) -> float:
        eur = self.ets_eur if self.ets_eur is not None else interp_year(ETS_EUR, self.year)
        return eur * EUR_USD

    def fueleu_target(self) -> float:
        return FUELEU_REF * (1 - step_year(FUELEU_RED, self.year))

    def imo_targets(self) -> tuple[float, float]:
        if not self.imo_nzf or self.year < 2028:
            return 1e9, 1e9
        base = REF_GHG_2008 * (1 - interp_year(IMO_BASE_RED, self.year))
        direct = REF_GHG_2008 * (1 - interp_year(IMO_DIRECT_RED, self.year))
        return base, direct

    def cii_reduction(self) -> float:
        return interp_year(CII_Z, self.year) / 100.0

    def fuel_price(self, f: Fuel) -> float:
        return interp_year(f.price, self.year) * self.fuel_price_mult.get(f.key, 1.0)


# ----------------------------------------------------------------------------------------
# Fleet (40 vessels, deterministic)
# ----------------------------------------------------------------------------------------
@dataclass
class Vessel:
    id: int
    name: str
    type: str
    dwt: float
    design_speed: float
    mcr_kw: float
    aux_sea_kw: float
    aux_port_kw: float
    age: float
    days_since_drydock: float
    kits: tuple                   # installed fuel kits
    shore_power: bool


_NAMES = ["Kaveri", "Godavari", "Narmada", "Tapti", "Krishna", "Ganga", "Yamuna", "Sutlej", "Beas",
          "Chenab", "Mahanadi", "Periyar", "Pamba", "Tungabhadra", "Sharavati", "Vaigai", "Palar",
          "Pennar", "Brahmani", "Baitarani", "Damodar", "Teesta", "Subansiri", "Lohit", "Manas",
          "Sabarmati", "Mahi", "Luni", "Ravi", "Jhelum", "Indus", "Gomti", "Ghaghara", "Son",
          "Betwa", "Chambal", "Ken", "Sharda", "Bhima", "Kosi"]


def build_fleet(seed: int = 7, counts: dict | None = None) -> list[Vessel]:
    counts = counts or {"feeder": 10, "panamax": 8, "handy": 8, "supra": 6, "mr": 8}
    rng = np.random.default_rng(seed)
    fleet: list[Vessel] = []
    i = 0
    for tkey, n in counts.items():
        vt = VESSEL_TYPES[VT_IDX[tkey]]
        for _ in range(n):
            dwt = float(rng.uniform(*vt.dwt))
            kits = ["diesel"]
            if tkey == "panamax" and rng.random() < 0.3:
                kits.append("lng")
            if tkey == "feeder" and rng.random() < 0.15:
                kits.append("methanol")
            name = f"MV {_NAMES[i % len(_NAMES)]}" + ("" if i < len(_NAMES) else f" {i // len(_NAMES) + 1}")
            fleet.append(Vessel(
                id=i, name=name, type=tkey, dwt=round(dwt),
                design_speed=vt.design_speed + float(rng.normal(0, 0.4)),
                mcr_kw=round(vt.mcr_per_dwt * dwt * float(rng.uniform(0.9, 1.1))),
                aux_sea_kw=vt.aux_sea_kw, aux_port_kw=vt.aux_port_kw,
                age=float(rng.integers(2, 22)), days_since_drydock=float(rng.integers(30, 850)),
                kits=tuple(kits), shore_power=bool(rng.random() < 0.1),
            ))
            i += 1
    return fleet
