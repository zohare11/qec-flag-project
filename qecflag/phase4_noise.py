"""Synthetic full-round calibration families for Phase 4.

Each sample is a (6,96) tensor: one Phase-3-style local Pauli calibration per
Steane check.  The distributions deliberately introduce check-to-check and
flag-channel heterogeneity so a calibration-conditioned proposal policy has a
nontrivial task.  These are controlled synthetic stress tests, not device data.
"""
from __future__ import annotations
import numpy as np
from .phase3_noise import sample_contexts as sample_local

FAMILIES = (
    'round_train', 'round_id', 'ood_flagA_bad', 'ood_flagB_bad',
    'ood_both_flags_clean', 'ood_check_hotspot', 'ood_data_hotspot',
    'ood_readout_hotspot', 'ood_pauli_sparse',
)


def _shared_flag_scaling(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Add sample-level correlation between the six uses of flag A/B."""
    n = len(x)
    # x: n,6,96.  prep A/B, flag-edge A/B blocks, meas A/B.
    for row in range(n):
        a_scale = float(np.exp(rng.normal(0, 0.30)))
        b_scale = float(np.exp(rng.normal(0, 0.30)))
        x[row, :, 1] *= a_scale
        x[row, :, 2] *= b_scale
        x[row, :, 3 + 15 * 4:3 + 15 * 5] *= a_scale
        x[row, :, 3 + 15 * 5:3 + 15 * 6] *= b_scale
        x[row, :, 94] *= a_scale
        x[row, :, 95] *= b_scale
    return x


def sample_round_contexts(n: int, seed: int, family: str) -> np.ndarray:
    if n < 1:
        raise ValueError('n must be positive')
    if family not in FAMILIES:
        raise ValueError(f'Unknown Phase-4 family {family!r}')
    rng = np.random.default_rng(seed)

    local_family = {
        'round_train': 'synthesis_train',
        'round_id': 'synthesis_id',
        'ood_flagA_bad': 'ood_flagA_bad',
        'ood_flagB_bad': 'ood_flagB_bad',
        'ood_both_flags_clean': 'ood_both_flags_clean',
        'ood_data_hotspot': 'ood_data_hotspot',
        'ood_readout_hotspot': 'ood_readout_hotspot',
        'ood_pauli_sparse': 'ood_pauli_sparse',
        'ood_check_hotspot': 'synthesis_id',
    }[family]

    x = sample_local(n * 6, seed + 17, local_family).reshape(n, 6, 96)
    x = _shared_flag_scaling(x, rng)

    if family == 'ood_check_hotspot':
        for row in range(n):
            check = int(rng.integers(6))
            x[row, check] *= rng.uniform(8.0, 18.0)
    # Mild global scale variation makes the contexts less tied to a single p.
    global_scale = np.exp(rng.normal(0.0, 0.18, size=(n, 1, 1)))
    return np.clip(x * global_scale, 1e-8, 200.0)


def validate_round_contexts(contexts: np.ndarray) -> np.ndarray:
    x = np.asarray(contexts, dtype=np.float64)
    if x.ndim != 3 or x.shape[1:] != (6, 96):
        raise ValueError('Expected Phase-4 contexts with shape (n,6,96)')
    if not np.isfinite(x).all() or np.any(x < 0):
        raise ValueError('Contexts must be finite and nonnegative')
    return x
