"""Export the prototype engine's outputs as one JSON file for the frontend demo.

    python -m scripts.export_demo            (run from backend/)
Writes ../frontend/public/demo-data.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import state                                                    # noqa: E402
from app.domain import FUELS, ROUTES, VESSEL_TYPES, Scenario, CII_LABELS  # noqa: E402
from app.qiea import MOQIEA, pick_knee                                   # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo-data.json"
MAIN_YEAR = 2030
YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
STORM_ROUTES = {"singapore": 2.6, "klang": 2.6, "haldia": 3.2, "vizag": 2.4, "colombo": 1.4}


def r(x, n=2):
    return float(round(float(x), n))


def optimise(sc: Scenario, seed=1, gens=200):
    fm = state.fleet_model(sc)
    res = MOQIEA(fm, generations=gens, seed=seed, snapshot_every=4).run()
    k = pick_knee(res["F"], res["V"])
    feas = res["V"] <= 1e-9
    return fm, res, k, feas


def front(fm, res, feas, limit=60):
    F = res["F"][feas]
    idx = np.where(feas)[0]
    order = np.argsort(F[:, 0])
    pts = []
    for j in order[: limit]:
        pts.append({"cost": r(F[j, 0]), "co2": r(F[j, 1]), "energy": r(F[j, 2]), "i": int(idx[j])})
    return pts


def main():
    pred = state.predictor()
    out: dict = {"meta": {"main_year": MAIN_YEAR, "years": YEARS}}
    out["fuels"] = [{"key": f.key, "name": f.name, "wtt": f.wtt, "ttw": f.ttw, "wtw": f.wtw, "cf": f.cf,
                     "color": f.color, "origin": f.origin} for f in FUELS]
    out["routes"] = [{"key": rt.key, "name": rt.name, "dest": rt.dest, "nm": rt.distance_nm,
                      "demand": rt.demand_kt, "path": [[p[1], p[0]] for p in rt.waypoints]} for rt in ROUTES]
    out["fleet"] = [{"id": v.id, "name": v.name, "type": v.type, "dwt": v.dwt, "vd": r(v.design_speed, 1),
                     "age": v.age} for v in state.FLEET]
    out["types"] = {t.key: t.name for t in VESSEL_TYPES}

    years = {}
    for y in YEARS:
        fm, res, k, feas = optimise(Scenario(year=y))
        bau = fm.plan(fm.bau_genes())
        best = fm.plan(fm.bits_to_int(res["bits"][k]))
        for p in (bau, best):
            p.pop("genes", None)
        entry = {"bau": bau, "opt": best}
        if y == MAIN_YEAR:
            entry["front"] = front(fm, res, feas)
            F = res["F"][feas]
            idx = np.where(feas)[0]
            extremes = {"cheapest": int(idx[np.argmin(F[:, 0])]), "greenest": int(idx[np.argmin(F[:, 1])]), "balanced": k}
            entry["extremes"] = {}
            for name, i in extremes.items():
                pl = fm.plan(fm.bits_to_int(res["bits"][i]))
                pl.pop("genes", None)
                entry["extremes"][name] = pl
            # qubit replay: per snapshot, per vessel 10 qubit angles (rounded)
            entry["snapshots"] = [{"gen": s["gen"], "theta": np.round(np.array(s["theta"]), 3).tolist()}
                                  for s in res["snapshots"]]
            entry["history"] = [{k2: (r(v2, 3) if isinstance(v2, float) else v2) for k2, v2 in h.items()}
                                for h in res["history"]]
            entry["evals"] = res["evals"]
            entry["seconds"] = r(res["seconds"], 1)
        years[str(y)] = entry
        print(y, "BAU", round(bau["objectives"]["wtw_kt"]), round(bau["objectives"]["cost_musd"]),
              "OPT", round(best["objectives"]["wtw_kt"]), round(best["objectives"]["cost_musd"]), best["cii_counts"], flush=True)
    out["years"] = years

    # storm mode on the main year
    sc = Scenario(year=MAIN_YEAR, weather_hs_add=STORM_ROUTES)
    fm_s, res_s, k_s, _ = optimise(sc)
    # keeping the calm-weather plan in the storm, vs re-planning for the storm
    fm_calm, res_calm, k_calm, _ = optimise(Scenario(year=MAIN_YEAR))
    storm_keep = fm_s.plan(fm_calm.bits_to_int(res_calm["bits"][k_calm]))
    storm_keep.pop("genes", None)
    replan = fm_s.plan(fm_s.bits_to_int(res_s["bits"][k_s]))
    replan.pop("genes", None)
    out["storm"] = {"routes": STORM_ROUTES, "center": [88.5, 14.5], "keep": storm_keep, "replan": replan,
                    "seconds": r(res_s["seconds"], 1)}
    print("storm keep", round(storm_keep["objectives"]["wtw_kt"]), "replan", round(replan["objectives"]["wtw_kt"]))

    # predictor
    s = pred.summary()
    v = state.FLEET[12]
    ex = pred.explain({"mcr_kw": v.mcr_kw, "design_speed": v.design_speed, "aux_sea_kw": v.aux_sea_kw},
                      {"speed": v.design_speed * 0.95, "draft_ratio": 0.92, "hs": 3.4, "wind": 13.0,
                       "wind_angle": 25.0, "days_dd": 610.0, "age": v.age})
    out["predictor"] = {"metrics": s["metrics"], "parity": s["parity"][:300], "circuit": s["circuit"],
                        "explain": {"vessel": v.name, **{k2: (r(v2, 2) if isinstance(v2, float) else v2) for k2, v2 in ex.items()}}}
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print("wrote", OUT, OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
