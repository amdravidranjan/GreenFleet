"""Optimiser benchmark: MO-QIEA vs NSGA-II vs random search.

Equal evaluation budget, identical encoding/repair/evaluation, 10 seeds, hypervolume on a
common normalisation, Wilcoxon signed-rank tests, and a fleet-size scalability sweep.
Writes backend/cache/benchmark.json (served by the API).

    python -m scripts.benchmark [--seeds 10] [--evals 24000]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from pymoo.indicators.hv import HV
from scipy.stats import wilcoxon

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import state                                        # noqa: E402
from app.baselines import run_nsga2, run_random              # noqa: E402
from app.domain import Scenario, build_fleet                 # noqa: E402
from app.fleet_model import FleetModel                       # noqa: E402
from app.qiea import MOQIEA, constrained_nondominated        # noqa: E402

CHECKPOINTS = [2000, 4000, 6000, 9000, 12000, 16000, 20000, 24000]


def qiea_trace(model, evals, seed):
    """Run MO-QIEA and capture the feasible archive at each checkpoint."""
    pop, obs = 60, 2
    snaps = {}
    algo = MOQIEA(model, pop=pop, obs=obs, generations=evals // (pop * obs), seed=seed, snapshot_every=10 ** 9)
    # wrap evaluate to record archive via callback on generation boundaries
    arch = {"F": np.zeros((0, 3)), "V": np.zeros(0)}
    orig = model.evaluate

    def recording(genes, detail=False):
        F, V = orig(genes)
        aF, aV = np.concatenate([arch["F"], F]), np.concatenate([arch["V"], V])
        nd = constrained_nondominated(aF, aV)
        arch["F"], arch["V"] = aF[nd], aV[nd]
        return F, V

    model.evaluate = recording
    try:
        def cb(g, h):
            snaps[h["evals"]] = arch["F"][arch["V"] <= 1e-9].copy()
        r = algo.run(callback=cb)
    finally:
        model.evaluate = orig
    return {"F": arch["F"], "V": arch["V"], "trace": sorted(snaps.items()), "seconds": r["seconds"]}


def hv_at(trace, checkpoint, hv):
    pts = None
    for n, F in trace:
        if n <= checkpoint:
            pts = F
    return float(hv(pts)) if pts is not None and len(pts) else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--evals", type=int, default=24000)
    ap.add_argument("--year", type=int, default=2035)
    args = ap.parse_args()
    checkpoints = [c for c in CHECKPOINTS if c <= args.evals]

    model = state.fleet_model(Scenario(year=args.year))
    algos = {"MO-QIEA (ours)": qiea_trace, "NSGA-II": lambda m, e, s: run_nsga2(m, e, seed=s),
             "Random search": lambda m, e, s: run_random(m, e, seed=s)}
    runs = {name: [] for name in algos}
    for s in range(args.seeds):
        for name, fn in algos.items():
            r = fn(model, args.evals, s)
            runs[name].append(r)
            print(f"seed {s} {name:16s} feasible={int((r['V'] <= 1e-9).sum())} t={r['seconds']:.1f}s", flush=True)

    allF = np.concatenate([r["F"][r["V"] <= 1e-9] for rs in runs.values() for r in rs])
    ideal, nadir = allF.min(0), allF.max(0)
    norm = lambda F: (F - ideal) / np.where(nadir - ideal > 0, nadir - ideal, 1)
    ind = HV(ref_point=np.full(3, 1.1))
    hv = lambda F: ind(norm(F))

    out = {"year": args.year, "evals": args.evals, "seeds": args.seeds, "algorithms": {}, "checkpoints": checkpoints}
    finals = {}
    for name, rs in runs.items():
        curves = np.array([[hv_at(r["trace"], c, hv) for c in checkpoints] for r in rs])
        finals[name] = curves[:, -1]
        best = min(rs, key=lambda r: -hv(r["F"][r["V"] <= 1e-9]) if (r["V"] <= 1e-9).any() else 0)
        bf = best["F"][best["V"] <= 1e-9]
        target = 0.95 * np.median(curves[:, -1]) if curves[:, -1].max() > 0 else np.inf
        out["algorithms"][name] = {
            "hv_final": curves[:, -1].tolist(),
            "hv_median": float(np.median(curves[:, -1])), "hv_iqr": float(np.subtract(*np.percentile(curves[:, -1], [75, 25]))),
            "curve_median": np.median(curves, 0).tolist(),
            "curve_q25": np.percentile(curves, 25, 0).tolist(), "curve_q75": np.percentile(curves, 75, 0).tolist(),
            "seconds_median": float(np.median([r["seconds"] for r in rs])),
            "feasible_median": float(np.median([(r["V"] <= 1e-9).sum() for r in rs])),
            "front": bf.round(2).tolist(),
            "min_cost": float(bf[:, 0].min()) if len(bf) else None, "min_wtw": float(bf[:, 1].min()) if len(bf) else None,
        }
    ours = finals["MO-QIEA (ours)"]
    for name in ("NSGA-II", "Random search"):
        diff = ours - finals[name]
        p = float(wilcoxon(ours, finals[name]).pvalue) if np.any(diff != 0) else 1.0
        out["algorithms"][name]["wilcoxon_p_vs_ours"] = p
        out["algorithms"][name]["ours_wins"] = int((diff > 0).sum())

    # scalability: fleet sizes with proportional demand
    scal = []
    base = {"feeder": 10, "panamax": 8, "handy": 8, "supra": 6, "mr": 8}
    for mult in (0.5, 1, 2, 4):
        counts = {k: max(1, int(round(v * mult))) for k, v in base.items()}
        fleet = build_fleet(seed=7, counts=counts)
        m = FleetModel(fleet, state.predictor(), Scenario(year=args.year, demand_mult=mult), {})
        row = {"vessels": len(fleet), "qubits": len(fleet) * 10}
        for name, fn in (("MO-QIEA (ours)", qiea_trace), ("NSGA-II", lambda mm, e, s: run_nsga2(mm, e, seed=s))):
            vals = []
            for s in range(3):
                r = fn(m, 12000, s)
                f = r["F"][r["V"] <= 1e-9]
                vals.append((r["seconds"], float(f[:, 1].min()) if len(f) else None, int(len(f))))
            row[name] = {"seconds": float(np.median([v[0] for v in vals])),
                         "min_wtw": [v[1] for v in vals], "feasible": [v[2] for v in vals]}
        scal.append(row)
        print("scal", row, flush=True)
    out["scalability"] = scal

    path = state.CACHE / "benchmark.json"
    path.write_text(json.dumps(out, indent=1))
    print("wrote", path)
    for name, a in out["algorithms"].items():
        print(f"{name:16s} HV median {a['hv_median']:.3f}  IQR {a['hv_iqr']:.3f}  p={a.get('wilcoxon_p_vs_ours', '-')}")


if __name__ == "__main__":
    main()
