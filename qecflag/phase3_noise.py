"""Synthetic Phase-3 calibration families over two available flag ancillas.

These are controlled stress-test distributions, not measurements from hardware.
"""
from __future__ import annotations
import numpy as np
from .phase3_physics import F3

FAMILIES = (
    'single_narrow',
    'single_shift',
    'synthesis_train',
    'synthesis_id',
    'ood_flagA_bad',
    'ood_flagB_bad',
    'ood_both_flags_clean',
    'ood_data_hotspot',
    'ood_readout_hotspot',
    'ood_pauli_sparse',
)


def _assemble(rng: np.random.Generator, rates: np.ndarray, alpha: np.ndarray | float) -> np.ndarray:
    n = rates.shape[0]
    out = np.empty((n, F3), dtype=np.float64)
    out[:, :3] = rates[:, :3]  # prep S/A/B
    alphas = np.full(n, float(alpha)) if np.isscalar(alpha) else np.asarray(alpha, dtype=np.float64)
    for edge in range(6):
        for row in range(n):
            composition = rng.dirichlet(np.full(15, alphas[row]))
            out[row, 3 + 15 * edge:3 + 15 * (edge + 1)] = rates[row, 3 + edge] * composition
    out[:, 93:] = rates[:, 9:12]
    return out


def _base(rng: np.random.Generator, n: int, sigma: float) -> np.ndarray:
    return np.exp(rng.normal(0.0, sigma, size=(n, 12))).clip(0.03, 80.0)


def _generic_domain_randomization(rng: np.random.Generator, n: int) -> np.ndarray:
    sigmas = rng.uniform(0.25, 1.05, size=n)
    rates = np.vstack([np.exp(rng.normal(0.0, s, size=12)) for s in sigmas]).clip(0.03, 80.0)
    # Encourage contexts where choosing A, choosing B, or occasionally using both can matter.
    for row in range(n):
        scenario = int(rng.integers(5))
        if scenario == 0:  # A is poor; B is cleaner.
            rates[row, [1, 7, 10]] *= rng.uniform(4.0, 12.0)
            rates[row, [2, 8, 11]] *= rng.uniform(0.25, 0.7)
        elif scenario == 1:  # B is poor; A is cleaner.
            rates[row, [2, 8, 11]] *= rng.uniform(4.0, 12.0)
            rates[row, [1, 7, 10]] *= rng.uniform(0.25, 0.7)
        elif scenario == 2:  # both flags unusually clean.
            rates[row, [1, 2, 7, 8, 10, 11]] *= rng.uniform(0.08, 0.35)
        elif scenario == 3:  # one data edge hot spot.
            edge = int(rng.integers(4))
            rates[row, 3 + edge] *= rng.uniform(5.0, 14.0)
        else:
            rates[row, 9] *= rng.uniform(1.0, 4.0)  # syndrome readout variability
    alpha = np.exp(rng.uniform(np.log(0.10), np.log(1.5), size=n))
    return _assemble(rng, rates.clip(0.02, 100.0), alpha)


def sample_contexts(n: int, seed: int, family: str) -> np.ndarray:
    if n < 1:
        raise ValueError('n must be positive')
    if family not in FAMILIES:
        raise ValueError(f'Unknown Phase-3 family {family!r}')
    rng = np.random.default_rng(seed)

    if family == 'single_narrow':
        return _assemble(rng, _base(rng, n, 0.50), 0.60)
    if family == 'single_shift':
        return _assemble(rng, _base(rng, n, 0.90), 0.25)
    if family in ('synthesis_train', 'synthesis_id'):
        return _generic_domain_randomization(rng, n)

    rates = _base(rng, n, 0.35 if family != 'ood_pauli_sparse' else 0.65)
    if family == 'ood_flagA_bad':
        rates[:, [1, 7, 10]] *= rng.uniform(15.0, 30.0, size=(n, 1))
        rates[:, [2, 8, 11]] *= rng.uniform(0.2, 0.6, size=(n, 1))
        return _assemble(rng, rates.clip(0.02, 120.0), 0.40)
    if family == 'ood_flagB_bad':
        rates[:, [2, 8, 11]] *= rng.uniform(15.0, 30.0, size=(n, 1))
        rates[:, [1, 7, 10]] *= rng.uniform(0.2, 0.6, size=(n, 1))
        return _assemble(rng, rates.clip(0.02, 120.0), 0.40)
    if family == 'ood_both_flags_clean':
        rates[:, [1, 2, 7, 8, 10, 11]] *= rng.uniform(0.03, 0.15, size=(n, 1))
        return _assemble(rng, rates.clip(0.005, 120.0), 0.35)
    if family == 'ood_data_hotspot':
        for row in range(n):
            rates[row, 3 + int(rng.integers(4))] *= rng.uniform(12.0, 25.0)
        return _assemble(rng, rates.clip(0.02, 120.0), 0.40)
    if family == 'ood_readout_hotspot':
        rates[:, 9:12] *= rng.uniform(12.0, 25.0, size=(n, 1))
        return _assemble(rng, rates.clip(0.02, 120.0), 0.40)
    if family == 'ood_pauli_sparse':
        return _assemble(rng, rates, 0.025)
    raise AssertionError('unreachable')


def validate_batch(contexts: np.ndarray) -> np.ndarray:
    x = np.asarray(contexts, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != F3:
        raise ValueError(f'Expected shape (n,{F3})')
    if not np.isfinite(x).all() or np.any(x < 0):
        raise ValueError('Context weights must be finite and nonnegative')
    return x
