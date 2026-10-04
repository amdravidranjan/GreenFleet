"""Quantum fidelity kernel (ZZ feature map, Havlicek et al. 2019) simulated exactly with a
state-vector simulator, plus Nystrom kernel ridge regression on top of it.

State preparation for n qubits and `reps` layers:  |psi(x)> = (U_phi(x) H^n)^reps |0>
with U_phi(x) = exp(i * [sum_i x_i Z_i + sum_(i,j) in E (pi - x_i)(pi - x_j) Z_i Z_j]).
U_phi is diagonal in the computational basis, so each layer is a Walsh-Hadamard transform
followed by an element-wise phase -> the whole batch is simulated with dense numpy ops.

Kernel: k(x, x') = |<psi(x)|psi(x')>|^2. Bandwidth scaling (Shaydulin & Wild 2022) avoids the
exponential kernel concentration that makes naive quantum kernels useless.
"""
from __future__ import annotations

import numpy as np


class ZZFeatureMap:
    def __init__(self, n_qubits: int, reps: int = 2, bandwidth: float = 1.0, entangle: bool = True):
        self.n, self.reps, self.bandwidth, self.entangle = n_qubits, reps, bandwidth, entangle
        d = 2 ** n_qubits
        z = np.arange(d)[:, None]
        self.S = 1.0 - 2.0 * ((z >> np.arange(n_qubits)) & 1)             # (d, n) spins +-1
        self.edges = [(i, (i + 1) % n_qubits) for i in range(n_qubits)] if entangle else []
        self.SS = (np.stack([self.S[:, i] * self.S[:, j] for i, j in self.edges], axis=1)
                   if self.edges else np.zeros((d, 0)))

    def _wht(self, psi: np.ndarray) -> np.ndarray:
        m, d = psi.shape
        h = psi
        for q in range(self.n):
            h = h.reshape(m, -1, 2, 2 ** q)
            a, b = h[:, :, 0, :], h[:, :, 1, :]
            h = np.stack([a + b, a - b], axis=2)
        return h.reshape(m, d) / np.sqrt(d)

    def states(self, x01: np.ndarray, chunk: int = 4096) -> np.ndarray:
        """x01: features scaled to [0, 1]. Returns complex state vectors (m, 2^n)."""
        out = []
        for s in range(0, len(x01), chunk):
            x = np.pi * self.bandwidth * x01[s:s + chunk]
            phase = x @ self.S.T
            if self.edges:
                pair = np.stack([(np.pi - x[:, i]) * (np.pi - x[:, j]) for i, j in self.edges], axis=1)
                phase = phase + pair @ self.SS.T
            diag = np.exp(1j * phase)
            psi = np.zeros((len(x), 2 ** self.n), dtype=complex)
            psi[:, 0] = 1.0
            for _ in range(self.reps):
                psi = diag * self._wht(psi)
            out.append(psi)
        return np.concatenate(out)

    def kernel(self, A: np.ndarray, B: np.ndarray) -> np.ndarray:
        return np.abs(A @ B.conj().T) ** 2


class RBFMap:
    """Classical RBF kernel with the same interface (ablation baseline)."""
    def __init__(self, gamma: float = 1.0):
        self.gamma = gamma

    def states(self, x01):
        return np.asarray(x01, dtype=float)

    def kernel(self, A, B):
        d2 = (A ** 2).sum(1)[:, None] + (B ** 2).sum(1)[None, :] - 2 * A @ B.T
        return np.exp(-self.gamma * np.maximum(d2, 0))


class NystromKRR:
    """Kernel ridge regression with a Nystrom low-rank approximation (m landmarks)."""
    def __init__(self, fmap, n_landmarks: int = 500, alpha: float = 1e-2, seed: int = 0):
        self.fmap, self.m, self.alpha, self.seed = fmap, n_landmarks, alpha, seed

    def _features(self, S):
        return self.fmap.kernel(S, self.L) @ self.proj

    def fit(self, x01, y):
        rng = np.random.default_rng(self.seed)
        idx = rng.choice(len(x01), min(self.m, len(x01)), replace=False)
        S = self.fmap.states(x01)
        self.L = S[idx]
        Kmm = self.fmap.kernel(self.L, self.L)
        w, U = np.linalg.eigh(Kmm)
        keep = w > 1e-8 * w.max()
        self.proj = U[:, keep] / np.sqrt(w[keep])
        Phi = self._features(S)
        self.mu = y.mean()
        A = Phi.T @ Phi + self.alpha * len(y) * np.eye(Phi.shape[1])
        self.coef = np.linalg.solve(A, Phi.T @ (y - self.mu))
        return self

    def predict(self, x01):
        return self._features(self.fmap.states(x01)) @ self.coef + self.mu
