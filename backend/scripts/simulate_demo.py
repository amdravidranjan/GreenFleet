"""Build the SIMULATED storyline used by the demo video on top of the exported engine data.

Kept from the real prototype (export_demo.py): fleet, routes, fuels, business-as-usual plans
and costs, fuel-predictor metrics / parity points / Shapley explanation.
Simulated (illustrative, not optimiser output): optimised plans per year, the Pareto menu,
qubit-collapse replay, storm re-plan and the assistant scenario.

    python -m scripts.simulate_demo     (run from backend/, after export_demo)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

PATH = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo-data.json"
rng = np.random.default_rng(42)

# fuel mix of the optimised fleet (share of ships) per year — ammonia overtakes LNG ~2033
MIX = {
    2025: {"vlsfo": .40, "lng": .25, "biolng": .12, "meoh": .10, "emeoh": .08, "h2": .05},
    2030: {"vlsfo": .20, "lng": .22, "biolng": .16, "emeoh": .17, "gnh3": .17, "h2": .08},
    2035: {"vlsfo": .08, "lng": .14, "biolng": .18, "emeoh": .20, "gnh3": .32, "h2": .08},
    2040: {"lng": .07, "biolng": .18, "emeoh": .20, "gnh3": .45, "h2": .10},
    2045: {"lng": .03, "biolng": .15, "emeoh": .20, "gnh3": .52, "h2": .10},
    2050: {"biolng": .12, "emeoh": .20, "gnh3": .58, "h2": .10},
}
COST_FACTOR = {2025: .97, 2030: .91, 2035: .85, 2040: .76, 2045: .72, 2050: .69}
H2_OK = {"vizag", "colombo", "haldia"}
SPEED_PCT = 81


def make_plan(d, bau, mix, cost_factor, speed_pct=SPEED_PCT, wobble=0.0):
    fuels = {f["key"]: f for f in d["fuels"]}
    active = [v for v in bau["vessels"] if v["route"]]
    n = len(active)
    quota = {k: int(round(s * n)) for k, s in mix.items()}
    while sum(quota.values()) < n:
        quota[max(mix, key=mix.get)] += 1
    while sum(quota.values()) > n:
        quota[max(mix, key=mix.get)] -= 1
    assign = {}
    pool = sorted(active, key=lambda v: (v["route"] not in H2_OK, v["id"]))
    for v in pool:                                   # hydrogen first, on short routes only
        if quota.get("h2", 0) and v["route"] in H2_OK:
            assign[v["id"]] = "h2"
            quota["h2"] -= 1
    order = [k for k in ("gnh3", "emeoh", "biolng", "lng", "meoh", "vlsfo") if quota.get(k)]
    rest = [v for v in sorted(active, key=lambda v: -v["dwt"] if "dwt" in v else v["id"]) if v["id"] not in assign]
    for v in rest:
        k = next((k for k in order if quota.get(k, 0) > 0), "vlsfo")
        assign[v["id"]] = k
        quota[k] = quota.get(k, 0) - 1
    vessels, energy = [], {}
    for v in bau["vessels"]:
        nv = dict(v)
        if v["route"]:
            f = assign[v["id"]]
            sp = speed_pct + int(rng.integers(-4, 5))
            speed_factor = (sp / 85) ** 2 * (1 + wobble)
            nv.update(fuel=f, speed_pct=sp, speed_kn=round(v["speed_kn"] * sp / 85, 1),
                      shore_power=bool(rng.random() < 0.6),
                      wtw_kt=round(v["wtw_kt"] * speed_factor * fuels[f]["wtw"] / 91.4, 3),
                      fuel_t_per_day=round(v["fuel_t_per_day"] * (sp / 85) ** 3, 1))
            ratio = 0.62 + 0.25 * rng.random() if f in ("vlsfo", "lng", "meoh", "biolng") else 0.35 + 0.3 * rng.random()
            nv["cii"] = "A" if ratio < 0.83 else "B" if ratio < 0.94 else "C"
            energy[f] = energy.get(f, 0) + v["wtw_kt"] * speed_factor
        vessels.append(nv)
    tot_e = sum(energy.values())
    wtw = sum(v["wtw_kt"] for v in vessels if v["route"])
    cost = bau["objectives"]["cost_musd"] * cost_factor
    cb = {k: v * cost_factor for k, v in bau["cost_breakdown"].items()}
    return {
        "objectives": {"cost_musd": round(cost, 1), "wtw_kt": round(wtw, 1), "energy_kt": round(bau["objectives"]["energy_kt"] * 0.78, 1)},
        "cost_breakdown": cb, "fuel_mix": {k: e / tot_e for k, e in energy.items()}, "vessels": vessels,
        "routes": bau["routes"], "cii_counts": {c: sum(1 for v in vessels if v["route"] and v["cii"] == c) for c in "ABCDE"},
    }


def qubit_replay(d, plan, snaps=60):
    fuels = [f["key"] for f in d["fuels"]]
    N = len(d["fleet"])
    target = np.zeros((N, 10), int)
    for v in plan["vessels"]:
        i = v["id"]
        rk = [r["key"] for r in d["routes"]].index(v["route"]) + 1 if v["route"] else 0
        sl = int(round((v["speed_pct"] / 100 - 0.55) / (0.45 / 7))) if v["route"] else 0
        fk = fuels.index(v["fuel"]) if v["fuel"] else 0
        for b in range(3):
            target[i, b] = (rk >> (2 - b)) & 1
            target[i, 3 + b] = (max(min(sl, 7), 0) >> (2 - b)) & 1
            target[i, 6 + b] = (fk >> (2 - b)) & 1
        target[i, 9] = int(v["shore_power"])
    tau = rng.uniform(0.3, 0.85, (N, 10))
    width = rng.uniform(0.05, 0.12, (N, 10))
    phase = rng.uniform(0, 2 * np.pi, (N, 10))
    out, hist = [], []
    eps = 0.04
    for s in range(snaps):
        x = s / (snaps - 1)
        settle = 1 / (1 + np.exp(-(x - tau) / width))
        end = np.where(target == 1, np.pi / 2 - eps, eps)
        wob = 0.32 * np.sin(phase + x * 22) * (1 - settle) * min(1, x * 6)
        th = np.pi / 4 + (end - np.pi / 4) * settle + wob
        th = np.clip(th, eps, np.pi / 2 - eps)
        out.append({"gen": int(x * 199), "theta": np.round(th, 3).tolist()})
        p = np.clip(np.sin(th) ** 2, 1e-6, 1 - 1e-6)
        ent = float((-(p * np.log2(p) + (1 - p) * np.log2(1 - p))).mean())
        hist.append({"gen": int(x * 199), "evals": int(120 * (x * 199 + 1)), "entropy": round(ent, 3),
                     "feasible": int(round(40 * (1 - math.exp(-5 * x)))) if x > 0.05 else 0})
    return out, hist


def main():
    d = json.loads(PATH.read_text())
    for y, mix in MIX.items():
        e = d["years"][str(y)]
        e["opt"] = make_plan(d, e["bau"], mix, COST_FACTOR[y])
        for k in ("front", "extremes", "snapshots", "history"):
            e.pop(k, None)
    main = d["years"]["2030"]
    bau = main["bau"]["objectives"]
    bal = main["opt"]
    cheap = make_plan(d, main["bau"], {"vlsfo": .35, "lng": .35, "biolng": .1, "meoh": .1, "emeoh": .05, "h2": .05}, 0.84, 78)
    green = make_plan(d, main["bau"], {"biolng": .2, "emeoh": .25, "gnh3": .45, "h2": .1}, 1.16, 76)
    main["extremes"] = {"cheapest": cheap, "balanced": bal, "greenest": green}
    pts = []
    c0, c1 = cheap["objectives"]["cost_musd"], green["objectives"]["cost_musd"]
    e0, e1 = cheap["objectives"]["wtw_kt"], green["objectives"]["wtw_kt"]
    for k in range(34):
        u = k / 33
        cost = c0 + (c1 - c0) * u
        co2 = e1 + (e0 - e1) * (1 - u) ** 2.2
        pts.append({"cost": round(cost + rng.normal(0, 1.5), 1), "co2": round(co2 + rng.normal(0, 6), 1)})
    pts += [{"cost": bal["objectives"]["cost_musd"], "co2": bal["objectives"]["wtw_kt"], "pick": "balanced"},
            {"cost": c0, "co2": e0, "pick": "cheapest"}, {"cost": c1, "co2": e1, "pick": "greenest"}]
    main["front"] = pts
    main["snapshots"], main["history"] = qubit_replay(d, bal)
    main["evals"], main["seconds"] = 24000, 9.6
    storm = d["storm"]
    keep = json.loads(json.dumps(bal))
    affected = set(storm["routes"])
    for v in keep["vessels"]:
        if v["route"] in affected:
            v["wtw_kt"] = round(v["wtw_kt"] * 1.14, 3)
            v["fuel_t_per_day"] = round(v["fuel_t_per_day"] * 1.14, 1)
    keep["objectives"]["wtw_kt"] = round(sum(v["wtw_kt"] for v in keep["vessels"] if v["route"]), 1)
    keep["objectives"]["cost_musd"] = round(bal["objectives"]["cost_musd"] * 1.06, 1)
    replan = json.loads(json.dumps(bal))
    for v in replan["vessels"]:
        if v["route"] in affected:
            v["speed_kn"] = round(v["speed_kn"] * 0.93, 1)
            v["speed_pct"] = int(v["speed_pct"] * 0.93)
            v["wtw_kt"] = round(v["wtw_kt"] * 1.035, 3)
    replan["objectives"]["wtw_kt"] = round(sum(v["wtw_kt"] for v in replan["vessels"] if v["route"]), 1)
    replan["objectives"]["cost_musd"] = round(bal["objectives"]["cost_musd"] * 1.015, 1)
    storm.update(keep=keep, replan=replan, seconds=1.9, extra_fuel_pct=14,
                 ships_affected=sum(1 for v in bal["vessels"] if v["route"] in affected))
    d["simulated"] = True
    PATH.write_text(json.dumps(d, separators=(",", ":")))
    for y in MIX:
        o, b = d["years"][str(y)]["opt"]["objectives"], d["years"][str(y)]["bau"]["objectives"]
        print(y, f"CO2 {o['wtw_kt']:.0f} vs {b['wtw_kt']:.0f} ({(o['wtw_kt'] / b['wtw_kt'] - 1) * 100:+.0f}%)",
              f"cost {o['cost_musd']:.0f} vs {b['cost_musd']:.0f} ({(o['cost_musd'] / b['cost_musd'] - 1) * 100:+.0f}%)",
              d["years"][str(y)]["opt"]["cii_counts"])
    print("storm keep", keep["objectives"]["wtw_kt"], "replan", replan["objectives"]["wtw_kt"], "affected", storm["ships_affected"])
    print("front", c0, e0, c1, e1, "balanced", bal["objectives"])


if __name__ == "__main__":
    main()
