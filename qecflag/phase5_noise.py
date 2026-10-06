"""Synthetic hardware + logical calibration families for Phase 5."""
from __future__ import annotations
import numpy as np

from .phase4_noise import sample_round_contexts
from .phase5_hardware import (
    HardwareBatch, N_EDGES, N_PHYSICAL, EDGES, HUB_NODES, DATA_NODES,
)

FAMILIES = (
    'hw_train', 'hw_id', 'ood_hub0_bad', 'ood_hub1_bad', 'ood_edge_hotspot',
    'ood_slow_link', 'ood_idle_hotspot', 'ood_logical_shift', 'ood_mixed',
)


def _incident_edges(node: int) -> list[int]:
    return [i for i, (u, v) in enumerate(EDGES) if u == node or v == node]


def sample_hardware_contexts(n: int, seed: int, family: str) -> HardwareBatch:
    if n < 1:
        raise ValueError('n must be positive')
    if family not in FAMILIES:
        raise ValueError(f'Unknown Phase-5 family {family!r}')
    rng = np.random.default_rng(seed)
    logical_family = 'round_train' if family == 'hw_train' else ('ood_pauli_sparse' if family == 'ood_logical_shift' else 'round_id')
    logical = sample_round_contexts(n, seed + 11, logical_family)

    edge_error = np.exp(rng.normal(0.0, 0.28, size=(n, N_EDGES)))
    edge_duration = 250.0 * np.exp(rng.normal(0.0, 0.12, size=(n, N_EDGES)))
    prep_scale = np.exp(rng.normal(0.0, 0.22, size=(n, N_PHYSICAL)))
    meas_scale = np.exp(rng.normal(0.0, 0.24, size=(n, N_PHYSICAL)))
    idle_rate = 2.0e-5 * np.exp(rng.normal(0.0, 0.35, size=(n, N_PHYSICAL)))

    if family == 'ood_hub0_bad':
        idx = _incident_edges(HUB_NODES[0])
        edge_error[:, idx] *= rng.uniform(7.0, 12.0, size=(n, 1))
        edge_duration[:, idx] *= rng.uniform(1.4, 2.2, size=(n, 1))
        prep_scale[:, HUB_NODES[0]] *= 5.0
        meas_scale[:, HUB_NODES[0]] *= 5.0
    elif family == 'ood_hub1_bad':
        idx = _incident_edges(HUB_NODES[1])
        edge_error[:, idx] *= rng.uniform(7.0, 12.0, size=(n, 1))
        edge_duration[:, idx] *= rng.uniform(1.4, 2.2, size=(n, 1))
        prep_scale[:, HUB_NODES[1]] *= 5.0
        meas_scale[:, HUB_NODES[1]] *= 5.0
    elif family == 'ood_edge_hotspot':
        for row in range(n):
            e = int(rng.integers(N_EDGES))
            edge_error[row, e] *= rng.uniform(12.0, 25.0)
            edge_duration[row, e] *= rng.uniform(1.2, 1.8)
    elif family == 'ood_slow_link':
        for row in range(n):
            e = int(rng.integers(N_EDGES))
            edge_duration[row, e] *= rng.uniform(6.0, 12.0)
    elif family == 'ood_idle_hotspot':
        for row in range(n):
            node = DATA_NODES[int(rng.integers(len(DATA_NODES)))]
            idle_rate[row, node] *= rng.uniform(15.0, 30.0)
    elif family == 'ood_mixed':
        for row in range(n):
            bad_hub = HUB_NODES[int(rng.integers(2))]
            idx = _incident_edges(bad_hub)
            edge_error[row, idx] *= rng.uniform(3.0, 7.0)
            edge_duration[row, idx] *= rng.uniform(1.2, 2.0)
            node = DATA_NODES[int(rng.integers(len(DATA_NODES)))]
            idle_rate[row, node] *= rng.uniform(5.0, 12.0)
            e = int(rng.integers(N_EDGES))
            edge_error[row, e] *= rng.uniform(4.0, 10.0)

    return HardwareBatch(
        logical=np.clip(logical, 1e-8, 500.0),
        edge_error=np.clip(edge_error, 1e-5, 100.0),
        edge_duration=np.clip(edge_duration, 10.0, 10000.0),
        prep_scale=np.clip(prep_scale, 1e-4, 100.0),
        meas_scale=np.clip(meas_scale, 1e-4, 100.0),
        idle_rate=np.clip(idle_rate, 0.0, 0.02),
    )


def validate_batch(batch: HardwareBatch) -> HardwareBatch:
    n = len(batch)
    if batch.logical.shape != (n, 6, 96):
        raise ValueError('logical shape mismatch')
    for i in range(n):
        batch.context(i).validate()
    return batch
