"""Phase-2 synthetic calibration families for robustness experiments.

These are deliberately synthetic distributions over the same 79 event-weight
features used by Phase 1. They are not calibrated hardware noise models.
"""
from __future__ import annotations
import math
import numpy as np
from .physics import F
from .noise import sample_contexts, validate_context

FAMILIES = (
    'narrow',
    'broad_shift',
    'domain_randomized',
    'ood_edge_hotspot',
    'ood_flag_hotspot',
    'ood_readout_hotspot',
    'ood_pauli_sparse',
)


def _assemble_from_rates(rng: np.random.Generator, rates: np.ndarray, alpha: np.ndarray | float) -> np.ndarray:
    """Convert nine location rates into 79 nonnegative event weights."""
    n = rates.shape[0]
    out = np.empty((n, F), dtype=np.float64)
    out[:, :2] = rates[:, :2]
    if np.isscalar(alpha):
        alphas = np.full(n, float(alpha), dtype=np.float64)
    else:
        alphas = np.asarray(alpha, dtype=np.float64)
        if alphas.shape != (n,):
            raise ValueError('alpha must be scalar or length n')
    for edge in range(5):
        for row in range(n):
            composition = rng.dirichlet(np.full(15, alphas[row]))
            out[row, 2 + 15 * edge: 2 + 15 * (edge + 1)] = rates[row, 2 + edge] * composition
    out[:, 77:] = rates[:, 7:]
    return out


def _base_rates(rng: np.random.Generator, n: int, sigma: float) -> np.ndarray:
    return np.exp(rng.normal(0.0, sigma, size=(n, 9))).clip(0.05, 30.0)


def sample_family(n: int, seed: int, family: str) -> np.ndarray:
    """Sample one named context family deterministically from ``seed``.

    Overall scaling is intentionally not used as a family distinction because
    C2 is homogeneous of degree two and a common scale does not change the
    argmin schedule. The families instead alter relative location rates and/or
    Pauli composition.
    """
    if n < 1:
        raise ValueError('n must be positive')
    if family not in FAMILIES:
        raise ValueError(f'Unknown family {family!r}; choose from {FAMILIES}')
    if family == 'narrow':
        return sample_contexts(n, seed, 'train')
    if family == 'broad_shift':
        return sample_contexts(n, seed, 'shift')

    rng = np.random.default_rng(seed)

    if family == 'domain_randomized':
        # A broad *training* mixture. Hyperparameters vary by context, and a
        # subset receives generic hot spots. None of the held-out OOD families
        # below is reproduced exactly.
        sigmas = rng.uniform(0.25, 1.05, size=n)
        rates = np.vstack([np.exp(rng.normal(0.0, s, size=9)) for s in sigmas]).clip(0.05, 30.0)
        alphas = np.exp(rng.uniform(np.log(0.12), np.log(1.4), size=n))
        for row in range(n):
            if rng.random() < 0.40:
                rates[row, 2 + int(rng.integers(5))] *= rng.uniform(1.5, 6.0)
            if rng.random() < 0.25:
                group = rng.choice(('prep', 'readout'))
                sl = slice(0, 2) if group == 'prep' else slice(7, 9)
                rates[row, sl] *= rng.uniform(1.3, 5.0)
        rates = rates.clip(0.03, 60.0)
        return _assemble_from_rates(rng, rates, alphas)

    if family == 'ood_edge_hotspot':
        rates = _base_rates(rng, n, 0.35)
        for row in range(n):
            # Data-edge hot spot only (edges 0..3), deliberately stronger than
            # the generic hot spots used during domain-randomized training.
            rates[row, 2 + int(rng.integers(4))] *= rng.uniform(8.0, 16.0)
        return _assemble_from_rates(rng, rates.clip(0.03, 60.0), 0.45)

    if family == 'ood_flag_hotspot':
        rates = _base_rates(rng, n, 0.35)
        rates[:, 6] *= rng.uniform(10.0, 20.0, size=n)  # edge index 4 => location-rate index 6
        return _assemble_from_rates(rng, rates.clip(0.03, 60.0), 0.45)

    if family == 'ood_readout_hotspot':
        rates = _base_rates(rng, n, 0.35)
        rates[:, 7:9] *= rng.uniform(10.0, 20.0, size=(n, 1))
        return _assemble_from_rates(rng, rates.clip(0.03, 60.0), 0.45)

    if family == 'ood_pauli_sparse':
        rates = _base_rates(rng, n, 0.65)
        # Much sparser Pauli composition than either ordinary train or domain randomization.
        return _assemble_from_rates(rng, rates, 0.03)

    raise AssertionError('unreachable')


def validate_batch(batch: np.ndarray) -> np.ndarray:
    batch = np.asarray(batch, dtype=np.float64)
    if batch.ndim != 2 or batch.shape[1] != F:
        raise ValueError(f'Expected shape (n, {F})')
    if not np.isfinite(batch).all() or np.any(batch < 0):
        raise ValueError('Contexts must be finite and nonnegative')
    # Exercise the original single-context validator on the boundary rows.
    validate_context(batch[0])
    validate_context(batch[-1])
    return batch
