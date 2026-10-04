"""Multi-objective Quantum-Inspired Evolutionary Algorithm (MO-QIEA).

Each Q-individual is a register of qubits |q> = cos(theta)|0> + sin(theta)|1>, one qubit per
decision bit (10 per vessel). A generation:
  1. observe  - collapse each register into classical bitstrings (P(1) = sin^2 theta)
  2. repair / evaluate with the fleet model (constraint-domination)
  3. select   - QMEA reference population B(t): best P of B(t-1) U observations by constrained
                 non-dominated sorting + crowding (Kim, Kim & Han 2006); plus an external archive
  4. rotate   - quantum rotation gate turns register j toward reference solution j on the bits
                 where they differ, with an adaptive angle (large early, small late)
  5. H-epsilon gate keeps theta inside [eps, pi/2 - eps] so no qubit fully collapses
  6. quantum NOT-gate mutation and periodic migration between sub-populations
The qubit angles are recorded as snapshots so the UI can replay the "superposition collapsing".
"""
from __future__ import annotations

import time
import numpy as np

from .fleet_model import N_BITS


def constrained_nondominated(F: np.ndarray, V: np.ndarray) -> np.ndarray:
    """Boolean mask of solutions not constraint-dominated (Deb's rules)."""
    n = len(F)
    feas = V <= 1e-9
    keep = np.ones(n, bool)
    for i in range(n):
        if feas[i]:
            others = feas & np.all(F <= F[i], 1) & np.any(F < F[i], 1)
        else:
            others = feas | (V < V[i] - 1e-12)
        keep[i] = not others.any()
    return keep


def crowding(F: np.ndarray) -> np.ndarray:
    n, m = F.shape
    if n <= 2:
        return np.full(n, np.inf)
    d = np.zeros(n)
    for j in range(m):
        o = np.argsort(F[:, j])
        rng = F[o[-1], j] - F[o[0], j] or 1.0
        d[o[0]] = d[o[-1]] = np.inf
        d[o[1:-1]] += (F[o[2:], j] - F[o[:-2], j]) / rng
    return d


class MOQIEA:
    def __init__(self, model, pop: int = 60, obs: int = 2, generations: int = 200, archive: int = 200,
                 d_max: float = 0.06 * np.pi, d_min: float = 0.005 * np.pi, eps: float = 0.02,
                 p_not: float = 0.002, seed: int = 0, snapshot_every: int = 3, seed_genes=None):
        self.m, self.P, self.obs, self.G, self.A = model, pop, obs, generations, archive
        self.d_max, self.d_min, self.eps, self.p_not = d_max, d_min, eps, p_not
        self.rng = np.random.default_rng(seed)
        self.snap_every = snapshot_every
        self.seed_genes = seed_genes

    def _genes_to_bits(self, genes):
        g = np.asarray(genes)
        out = np.zeros(g.shape[:-1] + (N_BITS,), int)
        for k, (col, width, off) in enumerate([(0, 3, 0), (1, 3, 3), (2, 3, 6)]):
            for b in range(width):
                out[..., off + b] = (g[..., col] >> (width - 1 - b)) & 1
        out[..., 9] = g[..., 3] & 1
        return out

    def run(self, callback=None) -> dict:
        m, N, P = self.m, self.m.N, self.P
        theta = np.full((P, N, N_BITS), np.pi / 4)                         # uniform superposition
        ref_bits = None                                                     # QMEA reference population B(t)
        ref_F, ref_V = np.zeros((0, 3)), np.zeros(0)
        arch_bits = np.zeros((0, N, N_BITS), int)
        arch_F, arch_V = np.zeros((0, 3)), np.zeros(0)
        if self.seed_genes is not None:
            b = self._genes_to_bits(self.seed_genes)[None]
            F, V = m.evaluate(m.bits_to_int(b))
            arch_bits, arch_F, arch_V = b, F, V
        history, snaps, evals = [], [], 0
        t0 = time.perf_counter()
        for g in range(self.G):
            # 1. observe: collapse every register `obs` times
            prob = np.sin(theta) ** 2
            bits = (self.rng.random((self.obs,) + theta.shape) < prob[None]).astype(int).reshape(-1, N, N_BITS)
            # 2. evaluate (repair happens inside the decoder)
            F, V = m.evaluate(m.bits_to_int(bits))
            evals += len(bits)
            # 3a. reference population: best P of B(t-1) U P(t) by constrained non-dominated sort + crowding
            pool_b = bits if ref_bits is None else np.concatenate([ref_bits, bits])
            pool_F = F if ref_bits is None else np.concatenate([ref_F, F])
            pool_V = V if ref_bits is None else np.concatenate([ref_V, V])
            sel = survival(pool_F, pool_V, P)
            ref_bits, ref_F, ref_V = pool_b[sel], pool_F[sel], pool_V[sel]
            # 3b. external archive of all non-dominated solutions (bounded by crowding)
            allb = np.concatenate([arch_bits, bits])
            allF, allV = np.concatenate([arch_F, F]), np.concatenate([arch_V, V])
            nd = constrained_nondominated(allF, allV)
            allb, allF, allV = allb[nd], allF[nd], allV[nd]
            _, uniq = np.unique(allF.round(6), axis=0, return_index=True)
            allb, allF, allV = allb[uniq], allF[uniq], allV[uniq]
            if len(allF) > self.A:
                keep = np.argsort(-crowding(allF))[: self.A]
                allb, allF, allV = allb[keep], allF[keep], allV[keep]
            arch_bits, arch_F, arch_V = allb, allF, allV
            # 4. rotation gate: register j turns toward reference solution j on differing bits
            order = self.rng.permutation(P)
            guide = ref_bits[order]
            own = bits.reshape(self.obs, P, N, N_BITS)[0]
            delta = self.d_max - (self.d_max - self.d_min) * g / max(self.G - 1, 1)
            theta += delta * np.where(guide == 1, 1.0, -1.0) * (own != guide)
            # 6. quantum NOT gate (mutation) + periodic migration of an elite into a register
            flip = self.rng.random(theta.shape) < self.p_not
            theta = np.where(flip, np.pi / 2 - theta, theta)
            if g % 25 == 24 and len(arch_F):
                e = self.rng.integers(0, len(arch_F))
                theta[self.rng.integers(0, P)] = np.where(arch_bits[e] == 1, np.pi / 2 - 0.25, 0.25)
            # 5. H-epsilon gate
            theta = np.clip(theta, self.eps, np.pi / 2 - self.eps)

            feas = arch_V <= 1e-9
            history.append({"gen": g, "evals": evals, "archive": int(len(arch_F)), "feasible": int(feas.sum()),
                            "best_cost": float(arch_F[feas, 0].min()) if feas.any() else None,
                            "best_wtw": float(arch_F[feas, 1].min()) if feas.any() else None,
                            "min_violation": float(arch_V.min()),
                            "entropy": float(_entropy(np.sin(theta) ** 2))})
            if g % self.snap_every == 0 or g == self.G - 1:
                snaps.append({"gen": g, "theta": theta.mean(0).round(4).tolist()})
            if callback:
                callback(g, history[-1])
        return {"bits": arch_bits, "F": arch_F, "V": arch_V, "history": history, "snapshots": snaps,
                "evals": evals, "seconds": time.perf_counter() - t0}


def survival(F: np.ndarray, V: np.ndarray, k: int) -> np.ndarray:
    """Indices of the k best by Deb's constrained non-dominated sorting + crowding distance."""
    from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
    feas = np.where(V <= 1e-9)[0]
    infeas = np.where(V > 1e-9)[0]
    chosen: list[int] = []
    if len(feas):
        for front in NonDominatedSorting().do(F[feas]):
            idx = feas[front]
            if len(chosen) + len(idx) <= k:
                chosen.extend(idx.tolist())
            else:
                cd = crowding(F[idx])
                chosen.extend(idx[np.argsort(-cd)[: k - len(chosen)]].tolist())
                break
    if len(chosen) < k and len(infeas):
        chosen.extend(infeas[np.argsort(V[infeas])[: k - len(chosen)]].tolist())
    return np.array(chosen, int)


def _entropy(p: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float((-(p * np.log2(p) + (1 - p) * np.log2(1 - p))).mean())


def pick_knee(F: np.ndarray, V: np.ndarray, weights=(1.0, 1.0, 0.3)) -> int:
    feas = np.where(V <= 1e-9)[0]
    if len(feas) == 0:
        return int(np.argmin(V))
    f = F[feas]
    lo, hi = f.min(0), f.max(0)
    z = (f - lo) / np.where(hi - lo > 0, hi - lo, 1)
    return int(feas[np.argmin(np.sqrt(((z * np.array(weights)) ** 2).sum(1)))])
