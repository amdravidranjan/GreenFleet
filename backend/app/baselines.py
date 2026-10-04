"""Conventional optimisers on the identical encoding, repair and evaluation budget."""
from __future__ import annotations

import time
import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import Problem
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.repair.rounding import RoundingRepair
from pymoo.operators.sampling.rnd import IntegerRandomSampling
from pymoo.optimize import minimize
from pymoo.termination import get_termination

from .qiea import constrained_nondominated


class FleetProblem(Problem):
    def __init__(self, model):
        self.model = model
        xu = np.tile([7, 7, 7, 1], model.N)
        super().__init__(n_var=4 * model.N, n_obj=3, n_ieq_constr=1, xl=0, xu=xu, vtype=int)
        self.history = []
        self.evals = 0

    def _evaluate(self, X, out, *args, **kwargs):
        genes = np.round(X).astype(int).reshape(len(X), self.model.N, 4)
        F, V = self.model.evaluate(genes)
        out["F"], out["G"] = F, V[:, None]
        self.evals += len(X)
        self.history.append((self.evals, F.copy(), V.copy()))


def run_nsga2(model, evals: int, pop: int = 100, seed: int = 0) -> dict:
    prob = FleetProblem(model)
    alg = NSGA2(pop_size=pop, sampling=IntegerRandomSampling(),
                crossover=SBX(prob=0.9, eta=15, vtype=float, repair=RoundingRepair()),
                mutation=PM(eta=20, vtype=float, repair=RoundingRepair()), eliminate_duplicates=True)
    t0 = time.perf_counter()
    minimize(prob, alg, get_termination("n_eval", evals), seed=seed, verbose=False)
    return _collect(prob.history, time.perf_counter() - t0)


def run_random(model, evals: int, batch: int = 120, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    hist, n = [], 0
    t0 = time.perf_counter()
    while n < evals:
        g = rng.integers(0, 8, (batch, model.N, 4))
        g[..., 3] %= 2
        F, V = model.evaluate(g)
        n += batch
        hist.append((n, F, V))
    return _collect(hist, time.perf_counter() - t0)


def _collect(hist, seconds):
    """Turn a stream of (evals, F, V) batches into a running non-dominated archive trace."""
    arch_F, arch_V, trace = np.zeros((0, 3)), np.zeros(0), []
    for n, F, V in hist:
        aF, aV = np.concatenate([arch_F, F]), np.concatenate([arch_V, V])
        nd = constrained_nondominated(aF, aV)
        arch_F, arch_V = aF[nd], aV[nd]
        trace.append((n, arch_F[arch_V <= 1e-9]))
    return {"F": arch_F, "V": arch_V, "trace": trace, "seconds": seconds}
