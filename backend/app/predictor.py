"""Fuel-consumption predictor: physics prior x exp(quantum-kernel residual), with split
conformal prediction intervals, exact Shapley explanations and a benchmark against
conventional models."""
from __future__ import annotations

import itertools
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_percentage_error, r2_score, mean_squared_error

from .physics import FEATURES, FEATURE_LABELS, feature_frame, prior_fuel_per_day, generate_noon_reports
from .quantum_kernel import NystromKRR, RBFMap, ZZFeatureMap

RAW_COLS = ["dwt", "design_speed", "mcr", "aux_kw", "speed", "draft_ratio", "hs", "wind", "wind_angle",
            "days_dd", "age"]


class GreyBoxModel:
    """fuel = prior(x) * exp(f(x)), f learned by a kernel machine on scaled features."""
    def __init__(self, fmap, n_landmarks=500, alpha=1e-3):
        self.fmap, self.n_landmarks, self.alpha = fmap, n_landmarks, alpha

    def _scale(self, X):
        return np.clip((X[FEATURES].to_numpy() - self.lo) / (self.hi - self.lo), 0, 1)

    def fit(self, df):
        self.lo = df[FEATURES].quantile(0.001).to_numpy()
        self.hi = df[FEATURES].quantile(0.999).to_numpy()
        y = np.log(df["fuel"].to_numpy() / df["prior"].to_numpy())
        self.krr = NystromKRR(self.fmap, self.n_landmarks, self.alpha).fit(self._scale(df), y)
        return self

    def predict(self, df):
        return df["prior"].to_numpy() * np.exp(self.krr.predict(self._scale(df)))


class Predictor:
    def __init__(self, seed: int = 11):
        self.seed = seed
        self.metrics: list[dict] = []

    # ------------------------------------------------------------------ training
    def train(self, n: int = 24000, tune: bool = True):
        df = generate_noon_reports(n, self.seed)
        rng = np.random.default_rng(0)
        idx = rng.permutation(len(df))
        n_tr, n_cal = int(0.7 * len(df)), int(0.1 * len(df))
        tr, cal, te = df.iloc[idx[:n_tr]], df.iloc[idx[n_tr:n_tr + n_cal]], df.iloc[idx[n_tr + n_cal:]]
        self.data_summary = {"n_reports": len(df), "train": len(tr), "calibration": len(cal), "test": len(te)}

        # bandwidth / ridge tuning on a validation split carved from train
        best = (1.0, 1e-3)
        if tune:
            sub_tr, sub_va = tr.iloc[:6000], tr.iloc[6000:9000]
            scores = {}
            for bw in (0.03, 0.05, 0.08, 0.12):
                for a in (1e-5, 1e-4):
                    m = GreyBoxModel(ZZFeatureMap(len(FEATURES), 2, bw), 400, a).fit(sub_tr)
                    scores[(bw, a)] = mean_absolute_percentage_error(sub_va["fuel"], m.predict(sub_va))
            best = min(scores, key=scores.get)
        self.bandwidth, self.alpha = best

        t0 = time.perf_counter()
        self.model = GreyBoxModel(ZZFeatureMap(len(FEATURES), 2, self.bandwidth), 600, self.alpha).fit(tr)
        train_s = time.perf_counter() - t0

        # split conformal interval on log residuals (90 %)
        r = np.abs(np.log(cal["fuel"].to_numpy() / self.model.predict(cal)))
        self.q90 = float(np.quantile(r, np.ceil(0.9 * (len(r) + 1)) / len(r)))

        self.metrics = [self._score("Quantum-kernel grey-box (ours)", self.model.predict, te, train_s, interval=True)]
        self.metrics += self._baselines(tr, te)
        self.test_sample = te.sample(400, random_state=1)
        self.test_pred = self.model.predict(self.test_sample)
        return self

    def _score(self, name, fn, te, train_s, interval=False):
        t0 = time.perf_counter()
        p = fn(te)
        inf_ms = (time.perf_counter() - t0) * 1000 / len(te) * 1000
        y = te["fuel"].to_numpy()
        out = {"model": name, "r2": float(r2_score(y, p)), "mape": float(mean_absolute_percentage_error(y, p) * 100),
               "rmse": float(np.sqrt(mean_squared_error(y, p))), "train_s": round(train_s, 2),
               "infer_ms_per_1k": round(inf_ms, 2)}
        if interval:
            lo, hi = p * np.exp(-self.q90), p * np.exp(self.q90)
            out["coverage90"] = float(((y >= lo) & (y <= hi)).mean() * 100)
        return out

    def _tune_rbf(self, tr):
        sub_tr, sub_va = tr.iloc[:6000], tr.iloc[6000:9000]
        scores = {}
        for g in (0.5, 1.0, 2.0, 4.0, 8.0):
            m = GreyBoxModel(RBFMap(g), 400, self.alpha).fit(sub_tr)
            scores[g] = mean_absolute_percentage_error(sub_va["fuel"], m.predict(sub_va))
        return min(scores, key=scores.get)

    def _baselines(self, tr, te):
        res = []
        res.append(self._score("Physics only (Admiralty law)", lambda d: d["prior"].to_numpy(), te, 0.0))
        gam = self._tune_rbf(tr)
        for name, fmap in [("Classical RBF-kernel grey-box", RBFMap(gamma=gam)),
                           ("Quantum kernel, no entanglement", ZZFeatureMap(len(FEATURES), 2, self.bandwidth, False))]:
            t0 = time.perf_counter()
            m = GreyBoxModel(fmap, 600, self.alpha).fit(tr)
            res.append(self._score(name, m.predict, te, time.perf_counter() - t0))
        X, y = tr[RAW_COLS], tr["fuel"]
        for name, est, logt in [("Linear regression", Ridge(1.0), True),
                                ("Random forest", RandomForestRegressor(200, min_samples_leaf=3, n_jobs=-1, random_state=0), False),
                                ("Gradient boosting", HistGradientBoostingRegressor(max_iter=400, random_state=0), False)]:
            t0 = time.perf_counter()
            est.fit(X, np.log(y) if logt else y)
            tt = time.perf_counter() - t0
            f = (lambda d, e=est: np.exp(e.predict(d[RAW_COLS]))) if logt else (lambda d, e=est: e.predict(d[RAW_COLS]))
            res.append(self._score(name, f, te, tt))
        return res

    # ------------------------------------------------------------------ inference
    @staticmethod
    def frame(mcr, design_speed, speed, draft_ratio, hs, wind, wind_angle, days_dd, age, aux_kw):
        df = feature_frame(mcr, design_speed, speed, draft_ratio, hs, wind, wind_angle, days_dd, age)
        df["prior"] = prior_fuel_per_day(np.asarray(mcr), np.asarray(design_speed), np.asarray(speed),
                                         np.asarray(draft_ratio), np.asarray(aux_kw))
        return df

    def predict(self, **kw) -> np.ndarray:
        return self.model.predict(self.frame(**kw))

    def explain(self, vessel: dict, cond: dict) -> dict:
        """Exact interventional Shapley values over 7 operating factors vs. a calm reference voyage."""
        ref = {"speed": vessel["design_speed"] * 0.8, "draft_ratio": 0.8, "hs": 0.5, "wind": 4.0,
               "wind_angle": 90.0, "days_dd": 0.0, "age": 0.0}
        keys = list(ref)
        combos = list(itertools.product([0, 1], repeat=len(keys)))
        rows = {k: np.array([cond[k] if c[j] else ref[k] for c in combos], float) for j, k in enumerate(keys)}
        n = len(combos)
        preds = self.predict(mcr=np.full(n, vessel["mcr_kw"]), design_speed=np.full(n, vessel["design_speed"]),
                             aux_kw=np.full(n, vessel["aux_sea_kw"]), **rows)
        lookup = {c: p for c, p in zip(combos, preds)}
        k = len(keys)
        fact = [1, 1, 2, 6, 24, 120, 720, 5040, 40320]
        phi = {}
        for j, key in enumerate(keys):
            s = 0.0
            for c in combos:
                if c[j]:
                    continue
                size = sum(c)
                w = fact[size] * fact[k - size - 1] / fact[k]
                with_j = tuple(1 if i == j else c[i] for i in range(k))
                s += w * (lookup[with_j] - lookup[c])
            phi[key] = float(s)
        base = float(lookup[tuple([0] * k)])
        pred = float(lookup[tuple([1] * k)])
        labels = {"speed": "Speed", "draft_ratio": "Loading / draft", "hs": "Wave height", "wind": "Wind speed",
                  "wind_angle": "Wind direction", "days_dd": "Hull fouling", "age": "Engine age"}
        return {"base": base, "prediction": pred, "lo": pred * np.exp(-self.q90), "hi": pred * np.exp(self.q90),
                "contributions": [{"feature": labels[k_], "value": cond[k_], "delta_t": v, "delta_pct": v / base * 100}
                                  for k_, v in sorted(phi.items(), key=lambda kv: -abs(kv[1]))]}

    def summary(self) -> dict:
        s = self.test_sample
        return {"metrics": self.metrics, "bandwidth": self.bandwidth, "alpha": self.alpha, "q90_log": self.q90,
                "data": self.data_summary, "features": [FEATURE_LABELS[f] for f in FEATURES],
                "qubits": len(FEATURES), "circuit": "ZZ feature map, 8 qubits, 2 reps, ring entanglement",
                "parity": [{"actual": float(a), "pred": float(p), "type": t}
                           for a, p, t in zip(s["fuel"], self.test_pred, s["vessel_type"])]}
