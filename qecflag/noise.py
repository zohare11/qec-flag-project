"""Synthetic calibration distributions; never represent real device data."""
from __future__ import annotations
import numpy as np
from .physics import F


def sample_contexts(n: int, seed: int, distribution: str = 'train') -> np.ndarray:
    if n < 1:
        raise ValueError('n must be positive')
    if distribution not in ('train', 'shift'):
        raise ValueError('distribution must be train or shift')
    rng = np.random.default_rng(seed)
    weights = np.empty((n, F), dtype=np.float64)
    sigma = 0.5 if distribution == 'train' else 0.9
    rates = np.exp(rng.normal(0, sigma, size=(n, 9))).clip(0.15, 5.0)
    weights[:, :2] = rates[:, :2]
    for edge in range(5):
        concentrations = np.full(15, 0.6 if distribution == 'train' else 0.25)
        pauli = rng.dirichlet(concentrations, size=n)
        weights[:, 2 + 15 * edge:2 + 15 * (edge + 1)] = rates[:, 2 + edge, None] * pauli
    weights[:, 77:] = rates[:, 7:]
    return weights


def validate_context(weights: np.ndarray, p: float | None = None) -> np.ndarray:
    result = np.asarray(weights, dtype=np.float64)
    if result.shape != (F,) or not np.isfinite(result).all() or np.any(result < 0):
        raise ValueError(f'Expected {F} finite, nonnegative event weights')
    rates = list(result[:2]) + [result[2 + 15 * e:2 + 15 * (e + 1)].sum() for e in range(5)] + list(result[77:])
    if p is not None and (not np.isfinite(p) or p < 0 or p * max(rates) > 1):
        raise ValueError('p must be nonnegative and each physical location error probability <= 1')
    return result
