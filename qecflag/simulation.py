"""Noisy Pauli sampling plus a hypothetical perfect final syndrome/recovery.

This is a COMPONENT diagnostic, not a full noisy QEC-cycle logical error rate.
All physical locations are independent. Pauli alternatives at the same CNOT
are mutually exclusive. Flags select a correction; they are NOT postselected.
"""
from __future__ import annotations
import numpy as np
from .physics import code_tables, fault_records
from .noise import validate_context


def failure_mask(data: np.ndarray, flags: np.ndarray, decoder: np.ndarray) -> np.ndarray:
    canon, _, syndromes, _ = code_tables()
    corrected = data ^ decoder[64 * flags + syndromes[data]]
    return canon[corrected] != 0


def wilson_interval(failures: int, shots: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if shots <= 0 or not 0 <= failures <= shots:
        raise ValueError('Expected 0 <= failures <= positive shots')
    rate = failures / shots
    denom = 1 + z * z / shots
    center = (rate + z * z / (2 * shots)) / denom
    radius = z * np.sqrt(rate * (1 - rate) / shots + z * z / (4 * shots * shots)) / denom
    return max(0.0, float(center - radius)), min(1.0, float(center + radius))


def simulate(schedule, decoder, weights, p: float, shots: int, seed: int, batch_size: int = 20000) -> dict:
    validate_context(weights, p)
    if shots < 1 or batch_size < 1:
        raise ValueError('shots and batch_size must be positive')
    rec = fault_records(schedule)
    rng = np.random.default_rng(seed)
    failures = flags_count = 0
    for start in range(0, shots, batch_size):
        batch = min(batch_size, shots - start)
        data = np.zeros(batch, dtype=np.int32)
        flag = np.zeros(batch, dtype=np.int8)
        for location in np.unique(rec.location):
            indices = np.flatnonzero(rec.location == location)
            cumulative = np.cumsum(p * weights[rec.category[indices]])
            selection = np.searchsorted(cumulative, rng.random(batch), side='right')
            # Last entry means no fault at this physical location.
            data ^= np.append(rec.data[indices], 0)[selection]
            flag ^= np.append(rec.flag[indices], 0).astype(np.int8)[selection]
        failures += int(np.count_nonzero(failure_mask(data, flag, decoder)))
        flags_count += int(np.count_nonzero(flag))
    lo, hi = wilson_interval(failures, shots)
    return {'shots': shots, 'seed': seed, 'p': p, 'logical_failures': failures,
            'logical_failure_rate_with_perfect_final_recovery': failures / shots,
            'wilson95_low': lo, 'wilson95_high': hi, 'flag_rate': flags_count / shots,
            'scope': 'ONE Z-check gadget, independent Pauli location faults, perfect final syndrome and correction; NOT full noisy QEC'}


def low_order_bounds(schedule, decoder, weights, p: float) -> dict:
    """Exact probability contribution from <=2 faulty locations and a rigorous
    residual probability bound for >=3 faulty locations under this noise model.
    Unlike C2*p^2, the <=2 contribution includes no-fault factors elsewhere.
    """
    validate_context(weights, p)
    rec = fault_records(schedule)
    locations = np.unique(rec.location)
    rates = np.array([weights[rec.category[rec.location == loc]].sum() for loc in locations])
    # Exact Poisson-binomial distribution of the number of faulty locations.
    probabilities = np.array([1.0])
    for rate in rates:
        q = p * rate
        probabilities = np.convolve(probabilities, [1 - q, q])
    contribution = 0.0
    single_bad = failure_mask(rec.data, rec.flag, decoder)
    for i in np.flatnonzero(single_bad):
        other = locations != rec.location[i]
        contribution += p * weights[rec.category[i]] * np.prod(1 - p * rates[other])
    i, j = np.triu_indices(len(rec.data), 1)
    different = rec.location[i] != rec.location[j]
    i, j = i[different], j[different]
    bad = failure_mask(rec.data[i] ^ rec.data[j], rec.flag[i] ^ rec.flag[j], decoder)
    i, j = i[bad], j[bad]
    pair_probability = p * p * weights[rec.category[i]] * weights[rec.category[j]]
    for loc, rate in zip(locations, rates):
        pair_probability *= np.where((rec.location[i] != loc) & (rec.location[j] != loc), 1 - p * rate, 1)
    contribution += float(pair_probability.sum())
    remainder = float(probabilities[3:].sum())
    return {'exact_failure_contribution_up_to_two_locations': float(contribution),
            'probability_three_or_more_faulty_locations': remainder,
            'rigorous_model_lower_bound': float(contribution),
            'rigorous_model_upper_bound': min(1.0, float(contribution + remainder))}
