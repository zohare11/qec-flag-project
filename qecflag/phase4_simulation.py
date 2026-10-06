"""Finite-p logical-memory diagnostics for the Phase-4 full-round model."""
from __future__ import annotations
import numpy as np

from .phase4_physics import (
    LOCAL_FEATURES, N_CHECKS, fault_records, build_decoder, failure_mask,
    logical_class, validate_round_labels,
)


def wilson_interval(failures: int, shots: int, z: float = 1.959963984540054) -> tuple[float, float]:
    rate = failures / shots
    denom = 1 + z * z / shots
    center = (rate + z * z / (2 * shots)) / denom
    radius = z * np.sqrt(rate * (1 - rate) / shots + z * z / (4 * shots * shots)) / denom
    return max(0.0, float(center - radius)), min(1.0, float(center + radius))


def _location_rates(records, context: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    w = np.asarray(context, dtype=np.float64)
    if w.shape == (N_CHECKS, LOCAL_FEATURES):
        w = w.reshape(-1)
    locations = np.unique(records.location)
    rates = np.asarray([w[records.category[records.location == loc]].sum() for loc in locations])
    return locations, rates


def validate_context_for_p(labels, context: np.ndarray, p: float) -> None:
    records = fault_records(labels)
    _locations, rates = _location_rates(records, context)
    if p < 0 or p * float(rates.max(initial=0.0)) > 1:
        raise ValueError('p makes at least one circuit-location fault probability exceed 1')


def simulate(labels, context: np.ndarray, p: float, shots: int, seed: int,
             batch_size: int = 20000) -> dict:
    labels = validate_round_labels(labels)
    context = np.asarray(context, dtype=np.float64)
    records = fault_records(labels)
    decoder = build_decoder(labels, records)
    validate_context_for_p(labels, context, p)
    flat = context.reshape(-1)
    rng = np.random.default_rng(seed)
    failures = 0
    logical_counts = {'X': 0, 'Z': 0, 'Y': 0, 'UNKNOWN': 0}

    for start in range(0, shots, batch_size):
        batch = min(batch_size, shots - start)
        data = np.zeros(batch, dtype=np.int32)
        obs = np.zeros(batch, dtype=np.int64)
        for location in np.unique(records.location):
            idx = np.flatnonzero(records.location == location)
            probabilities = p * flat[records.category[idx]]
            cumulative = np.cumsum(probabilities)
            draw = np.searchsorted(cumulative, rng.random(batch), side='right')
            # sentinel at the end = no fault at this physical location
            data ^= np.append(records.data[idx], 0)[draw]
            obs ^= np.append(records.observation[idx], 0)[draw]

        correction = decoder.corrections_for(obs)
        residual = data ^ correction
        fail = failure_mask(data, obs, decoder)
        failures += int(np.count_nonzero(fail))
        if np.any(fail):
            for value in residual[fail]:
                cls = logical_class(int(value))
                if cls in logical_counts:
                    logical_counts[cls] += 1

    lo, hi = wilson_interval(failures, shots)
    return {
        'p': float(p), 'shots': int(shots), 'seed': int(seed), 'failures': int(failures),
        'logical_failure_rate': failures / shots,
        'wilson95_low': lo, 'wilson95_high': hi,
        'logical_class_counts': logical_counts,
        'scope': 'one noisy six-check Steane extraction round; explicit flag-aware lookup decoder; ideal initial/final boundaries; independent Pauli location faults',
    }
