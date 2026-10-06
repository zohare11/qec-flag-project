"""Finite-p component diagnostics for synthesized Phase-3 schedules."""
from __future__ import annotations
import numpy as np
from .physics import code_tables
from .phase3_physics import fault_records


def failure_mask(data: np.ndarray, flags: np.ndarray, decoder: np.ndarray) -> np.ndarray:
    canon, _, syndromes, _ = code_tables()
    corrected = data ^ decoder[64 * flags + syndromes[data]]
    return canon[corrected] != 0


def wilson_interval(failures: int, shots: int, z: float = 1.959963984540054) -> tuple[float, float]:
    rate = failures / shots
    denom = 1 + z * z / shots
    center = (rate + z * z / (2 * shots)) / denom
    radius = z * np.sqrt(rate * (1-rate) / shots + z*z/(4*shots*shots)) / denom
    return max(0.0, float(center-radius)), min(1.0, float(center+radius))


def validate_context_for_p(weights: np.ndarray, p: float) -> None:
    weights = np.asarray(weights, dtype=np.float64)
    if weights.shape != (96,) or np.any(weights < 0) or not np.isfinite(weights).all():
        raise ValueError('Expected 96 finite nonnegative event weights')
    rec_rates = [weights[0], weights[1], weights[2]]
    rec_rates += [weights[3+15*e:3+15*(e+1)].sum() for e in range(6)]
    rec_rates += [weights[93], weights[94], weights[95]]
    if p < 0 or p * max(rec_rates) > 1:
        raise ValueError('p makes at least one physical-location fault probability exceed 1')


def simulate(schedule, decoder, weights: np.ndarray, p: float, shots: int, seed: int,
             batch_size: int = 20000) -> dict:
    validate_context_for_p(weights, p)
    rec = fault_records(schedule)
    rng = np.random.default_rng(seed)
    failures = 0
    for start in range(0, shots, batch_size):
        batch = min(batch_size, shots-start)
        data = np.zeros(batch, dtype=np.int32)
        flags = np.zeros(batch, dtype=np.int8)
        for location in np.unique(rec.location):
            idx = np.flatnonzero(rec.location == location)
            cumulative = np.cumsum(p * weights[rec.category[idx]])
            selection = np.searchsorted(cumulative, rng.random(batch), side='right')
            data ^= np.append(rec.data[idx], 0)[selection]
            flags ^= np.append(rec.flags[idx], 0).astype(np.int8)[selection]
        failures += int(np.count_nonzero(failure_mask(data, flags, decoder)))
    lo, hi = wilson_interval(failures, shots)
    return {
        'p': p, 'shots': shots, 'seed': seed, 'failures': failures,
        'rate_with_perfect_final_recovery': failures/shots,
        'wilson95_low': lo, 'wilson95_high': hi,
        'scope': 'single Steane Z-check component; independent Pauli location faults; ideal final syndrome/recovery',
    }
