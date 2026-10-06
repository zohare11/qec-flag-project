"""Phase 9: low-order repeated-round fault analysis and detector-hypergraph decoding.

This phase does two things that Phase 8 deliberately left open:

1. It estimates the asymptotic low-p expansion of the three-round memory
   experiment without trying to infer an exponent from a handful of Monte Carlo
   failures.  C1 and C2 are evaluated exactly for the primary history decoder;
   the raw three-fault malignant weight is importance-sampled and converted to
   a third-order Taylor-coefficient estimate.

2. It replaces the exponentially sized history-key lookup as the only serious
   decoder baseline with a detector-event decoder.  Single physical faults are
   converted into sparse syndrome-difference + flag hyperedges.  The decoder
   precomputes the minimum-cost explanation using zero, one, or two such
   hyperedges.  For fixed Steane checks this grows polynomially with the number
   of rounds, rather than as the number of possible complete histories.

The detector decoder is NOT MWPM/PyMatching.  Flagged circuit faults can create
more than two detector events, so the natural object is a small hypergraph, not
an ordinary matching graph.  The order-2 decoder is intended as a scalable-in-
rounds baseline for this seven-qubit pilot, not as a decoder for large codes.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Iterable
import numpy as np

from .physics import code_tables
from .phase8_timing import (
    TimedRoundPlan, RepeatedFaultRecords, RepeatedHistoryDecoder,
    repeated_fault_records, build_repeated_history_decoder,
    standard_steane_history_correction,
)
from .phase5_hardware import HardwareContext


def syndrome_history_to_detectors(history: int, rounds: int) -> int:
    """Convert measured syndrome history + final boundary into detector events.

    The initial boundary syndrome is zero.  Detector t is s_t XOR s_(t-1),
    including the final ideal memory boundary at t=rounds.
    """
    prev = 0
    out = 0
    for t in range(rounds + 1):
        s = (int(history) >> (6 * t)) & 63
        out |= int(s ^ prev) << (6 * t)
        prev = s
    return int(out)


def detectors_to_syndrome_history(detectors: int, rounds: int) -> int:
    prev = 0
    out = 0
    for t in range(rounds + 1):
        d = (int(detectors) >> (6 * t)) & 63
        s = prev ^ d
        out |= int(s) << (6 * t)
        prev = s
    return int(out)


def _detectors_vec(history: np.ndarray, rounds: int) -> np.ndarray:
    h = np.asarray(history, dtype=np.int64)
    prev = np.zeros_like(h)
    out = np.zeros_like(h)
    for t in range(rounds + 1):
        s = (h >> (6 * t)) & 63
        out |= (s ^ prev) << (6 * t)
        prev = s
    return out


@dataclass(frozen=True)
class DetectorPrimitive:
    event_mask: int
    correction: int
    aggregate_weight: float
    support_locations: int


@dataclass
class DetectorPairDecoder:
    keys: np.ndarray
    corrections: np.ndarray
    costs: np.ndarray
    rounds: int
    reference_p: float
    primitive_count: int
    map_entries: int
    single_fault_conflicts: int = 0
    single_fault_failures: int = 0
    incoming_failures: int = 0

    @property
    def detector_bits(self) -> int:
        return 6 * (self.rounds + 1)

    def event_keys(self, syndrome_history: np.ndarray, flag_history: np.ndarray) -> np.ndarray:
        det = _detectors_vec(np.asarray(syndrome_history, dtype=np.int64), self.rounds)
        return det | (np.asarray(flag_history, dtype=np.int64) << self.detector_bits)

    def corrections_for(self, syndrome_history: np.ndarray, flag_history: np.ndarray) -> np.ndarray:
        sh = np.asarray(syndrome_history, dtype=np.int64)
        fh = np.asarray(flag_history, dtype=np.int64)
        k = self.event_keys(sh, fh)
        pos = np.searchsorted(self.keys, k)
        safe = np.minimum(pos, len(self.keys) - 1)
        hit = (pos < len(self.keys)) & (self.keys[safe] == k)
        out = np.empty(k.shape, dtype=np.int32)
        out[hit] = self.corrections[safe[hit]]
        if np.any(~hit):
            _, _, _, fallback = code_tables()
            final = (sh[~hit] >> (6 * self.rounds)) & 63
            out[~hit] = np.asarray(fallback, dtype=np.int32)[final]
        return out

    def correction_for(self, syndrome_history: int, flag_history: int = 0) -> int:
        return int(self.corrections_for(
            np.asarray([syndrome_history], dtype=np.int64),
            np.asarray([flag_history], dtype=np.int64),
        )[0])


def _history_corrections_for(decoder: RepeatedHistoryDecoder,
                             syndrome_history: np.ndarray,
                             flag_history: np.ndarray) -> np.ndarray:
    sh = np.asarray(syndrome_history, dtype=np.int64)
    fh = np.asarray(flag_history, dtype=np.int64)
    shift = 6 * (decoder.rounds + 1)
    key = sh | (fh << shift)
    pos = np.searchsorted(decoder.keys, key)
    safe = np.minimum(pos, len(decoder.keys) - 1)
    hit = (pos < len(decoder.keys)) & (decoder.keys[safe] == key)
    out = np.empty(key.shape, dtype=np.int32)
    out[hit] = decoder.corrections[safe[hit]]
    if np.any(~hit):
        _, _, _, fallback = code_tables()
        final = (sh[~hit] >> (6 * decoder.rounds)) & 63
        out[~hit] = np.asarray(fallback, dtype=np.int32)[final]
    return out


def _decoder_corrections(decoder, sh: np.ndarray, fh: np.ndarray) -> np.ndarray:
    if isinstance(decoder, DetectorPairDecoder):
        return decoder.corrections_for(sh, fh)
    if isinstance(decoder, RepeatedHistoryDecoder):
        return _history_corrections_for(decoder, sh, fh)
    raise TypeError(type(decoder))


def build_detector_pair_decoder(plan: TimedRoundPlan, context: HardwareContext, rounds: int,
                                reference_p: float = 2e-4,
                                records: RepeatedFaultRecords | None = None) -> DetectorPairDecoder:
    """Build an order-2 detector-hypergraph decoder from single-fault signatures.

    The event key consists of syndrome-difference detector bits followed by all
    flag bits.  Single-fault outcomes with the same event key and stabilizer
    coset are aggregated.  The decoder then stores the minimum negative-log-
    likelihood correction for every event pattern reachable by zero, one, or
    two aggregate hyperedges.
    """
    if rounds < 1:
        raise ValueError('rounds must be >=1')
    if reference_p <= 0:
        raise ValueError('reference_p must be positive')
    rec = repeated_fault_records(plan, context, rounds) if records is None else records
    canon, minweights, _, fallback = code_tables()
    det_bits = 6 * (rounds + 1)

    aggregate: dict[tuple[int, int], dict] = {}
    for d, sh, fh, loc, w in zip(rec.data, rec.syndrome_history, rec.flag_history, rec.location, rec.weight):
        event = syndrome_history_to_detectors(int(sh), rounds) | (int(fh) << det_bits)
        coset = int(canon[int(d)])
        key = (event, coset)
        a = aggregate.setdefault(key, {'weight': 0.0, 'locations': set(), 'rep': int(d)})
        a['weight'] += float(w)
        a['locations'].add(int(loc))
        if (int(minweights[int(d)]), int(d)) < (int(minweights[a['rep']]), int(a['rep'])):
            a['rep'] = int(d)

    primitives: list[DetectorPrimitive] = []
    supports: list[frozenset[int]] = []
    for (event, _), a in aggregate.items():
        if a['weight'] <= 0:
            continue
        primitives.append(DetectorPrimitive(int(event), int(a['rep']), float(a['weight']), len(a['locations'])))
        supports.append(frozenset(a['locations']))

    # mask -> (fault_order, cost, correction), with deterministic ties.
    # Fault order is lexicographically primary. This guarantees that an event
    # pattern known to arise from one physical fault is never reinterpreted as
    # a more likely-looking two-fault explanation, preserving the certified
    # single-fault correction property under calibration shifts.
    best: dict[int, tuple[int, float, int]] = {0: (0, 0.0, 0)}

    def offer(mask: int, order: int, cost: float, corr: int):
        old = best.get(int(mask))
        candidate = (int(order), float(cost), int(corr))
        if old is None or candidate < old:
            best[int(mask)] = candidate

    costs = np.asarray([-log(max(reference_p * p.aggregate_weight, 1e-300)) for p in primitives], dtype=np.float64)
    for i, p in enumerate(primitives):
        offer(p.event_mask, 1, float(costs[i]), p.correction)

    # Order-2 hypergraph explanations.  Pair candidates must be physically
    # realizable at distinct stochastic locations.
    for i, a in enumerate(primitives):
        for j in range(i, len(primitives)):
            b = primitives[j]
            if i == j:
                if a.support_locations < 2:
                    continue
            elif len(supports[i] | supports[j]) < 2:
                continue
            offer(a.event_mask ^ b.event_mask, 2, float(costs[i] + costs[j]), a.correction ^ b.correction)

    keys = np.asarray(sorted(best), dtype=np.int64)
    corrections = np.asarray([best[int(k)][2] for k in keys], dtype=np.int32)
    out_costs = np.asarray([best[int(k)][1] for k in keys], dtype=np.float64)
    dec = DetectorPairDecoder(keys, corrections, out_costs, rounds, float(reference_p), len(primitives), len(keys))

    # Diagnostics: this decoder should preserve all single-fault guarantees.
    sf_corr = dec.corrections_for(rec.syndrome_history, rec.flag_history)
    dec.single_fault_failures = int(np.count_nonzero(canon[rec.data ^ sf_corr]))
    # Incoming single errors are handled by the final-boundary fallback.  Build
    # them directly through the existing exact simulator via the primary decoder
    # behavior: a final syndrome is sufficient to correct any one data Pauli.
    incoming_fail = 0
    for q in range(7):
        for code in (1, 2, 3):
            err = ((code & 1) << q) | (((code >> 1) & 1) << (7 + q))
            # No noisy syndrome history, only final ideal boundary syndrome.
            _, _, syndromes, _ = code_tables()
            sh = int(syndromes[err]) << (6 * rounds)
            corr = dec.correction_for(sh, 0)
            incoming_fail += int(canon[err ^ corr] != 0)
    dec.incoming_failures = int(incoming_fail)

    # Conflicts at the single-hyperedge level: same event mapped to different
    # stabilizer cosets.  These would make exact single-fault correction impossible.
    by_event: dict[int, set[int]] = {}
    for (event, coset) in aggregate:
        by_event.setdefault(int(event), set()).add(int(coset))
    dec.single_fault_conflicts = int(sum(len(v) > 1 for v in by_event.values()))
    return dec


@dataclass(frozen=True)
class LowOrderExpansion:
    c1: float
    c2: float
    malignant_single_outcomes: int
    malignant_pair_outcomes: int
    pair_no_fault_correction: float
    raw_t3_estimate: float
    raw_t3_se: float
    c3_taylor_estimate: float
    c3_taylor_se: float
    triple_samples: int
    triple_failure_fraction: float
    total_location_rate: float

    def predict(self, p: float) -> float:
        return float(self.c1 * p + self.c2 * p * p + self.c3_taylor_estimate * p * p * p)


def _location_rates(rec: RepeatedFaultRecords) -> tuple[np.ndarray, np.ndarray]:
    locations = np.unique(rec.location)
    rates = np.asarray([float(rec.weight[rec.location == loc].sum()) for loc in locations], dtype=np.float64)
    return locations, rates


def exact_c1_c2(records: RepeatedFaultRecords, decoder, pair_block: int = 48):
    """Exact C1/C2 and the cubic no-fault subtraction from malignant pairs."""
    canon, _, _, _ = code_tables()
    single_corr = _decoder_corrections(decoder, records.syndrome_history, records.flag_history)
    single_fail = canon[records.data ^ single_corr] != 0
    c1 = float(records.weight[single_fail].sum())
    single_count = int(np.count_nonzero(single_fail))

    _, loc_rates = _location_rates(records)
    total_rate = float(loc_rates.sum())
    # map dense location ids to their total rates; repeated_fault_records ids are dense.
    max_loc = int(records.location.max(initial=-1))
    rate_by_loc = np.zeros(max_loc + 1, dtype=np.float64)
    for loc in np.unique(records.location):
        rate_by_loc[int(loc)] = float(records.weight[records.location == loc].sum())

    n = len(records.data)
    c2 = 0.0
    pair_count = 0
    pair_sub = 0.0
    all_j = np.arange(n, dtype=np.int32)[None, :]
    data_all = records.data[None, :]
    sh_all = records.syndrome_history[None, :]
    fh_all = records.flag_history[None, :]
    loc_all = records.location[None, :]
    w_all = records.weight[None, :]
    for start in range(0, n, pair_block):
        stop = min(n, start + pair_block)
        ii = np.arange(start, stop, dtype=np.int32)[:, None]
        valid = (all_j > ii) & (loc_all != records.location[start:stop, None])
        data = records.data[start:stop, None] ^ data_all
        sh = records.syndrome_history[start:stop, None] ^ sh_all
        fh = records.flag_history[start:stop, None] ^ fh_all
        corr = _decoder_corrections(decoder, sh, fh)
        fail = (canon[data ^ corr] != 0) & valid
        pair_count += int(np.count_nonzero(fail))
        if np.any(fail):
            prod = records.weight[start:stop, None] * w_all
            c2 += float(prod[fail].sum())
            li = records.location[start:stop, None]
            remaining = total_rate - rate_by_loc[li] - rate_by_loc[loc_all]
            pair_sub += float((prod * remaining)[fail].sum())
    return c1, c2, single_count, pair_count, pair_sub, total_rate


def _draw_weighted_distinct_triples(records: RepeatedFaultRecords, samples: int, rng: np.random.Generator):
    probs = np.asarray(records.weight, dtype=np.float64)
    probs = probs / probs.sum()
    out = np.empty((samples, 3), dtype=np.int32)
    filled = 0
    # Draw in moderately oversized batches and reject triples sharing a location.
    while filled < samples:
        need = samples - filled
        batch = max(1024, int(need * 1.35))
        draw = rng.choice(len(probs), size=(batch, 3), replace=True, p=probs)
        loc = records.location[draw]
        ok = (loc[:, 0] != loc[:, 1]) & (loc[:, 0] != loc[:, 2]) & (loc[:, 1] != loc[:, 2])
        good = draw[ok]
        take = min(need, len(good))
        if take:
            out[filled:filled + take] = good[:take]
            filled += take
    return out


def estimate_raw_t3(records: RepeatedFaultRecords, decoder, samples: int, seed: int,
                    batch_size: int = 20000) -> tuple[float, float, float]:
    """Importance-sample the raw malignant three-fault weight.

    Ordered fault outcomes are sampled with probability proportional to their
    weights and conditioned on belonging to three distinct locations.  Under
    this proposal the failure fraction multiplied by the exact normalization
    gives an unbiased estimate of the unordered three-fault malignant weight.
    """
    if samples <= 0:
        raise ValueError('samples must be positive')
    _, rates = _location_rates(records)
    total = float(rates.sum())
    s2 = float(np.square(rates).sum())
    s3 = float(np.power(rates, 3).sum())
    z_ordered = total ** 3 - 3.0 * total * s2 + 2.0 * s3
    normalization = z_ordered / 6.0
    canon, _, _, _ = code_tables()
    rng = np.random.default_rng(seed)
    fail_count = 0
    done = 0
    while done < samples:
        b = min(batch_size, samples - done)
        idx = _draw_weighted_distinct_triples(records, b, rng)
        data = records.data[idx[:, 0]] ^ records.data[idx[:, 1]] ^ records.data[idx[:, 2]]
        sh = records.syndrome_history[idx[:, 0]] ^ records.syndrome_history[idx[:, 1]] ^ records.syndrome_history[idx[:, 2]]
        fh = records.flag_history[idx[:, 0]] ^ records.flag_history[idx[:, 1]] ^ records.flag_history[idx[:, 2]]
        corr = _decoder_corrections(decoder, sh, fh)
        fail_count += int(np.count_nonzero(canon[data ^ corr]))
        done += b
    frac = fail_count / samples
    raw = float(normalization * frac)
    se = float(normalization * np.sqrt(max(frac * (1.0 - frac), 0.0) / samples))
    return raw, se, float(frac)


def low_order_expansion(plan: TimedRoundPlan, context: HardwareContext, rounds: int,
                        decoder_kind: str = 'history', reference_p: float = 2e-4,
                        triple_samples: int = 30000, seed: int = 0,
                        pair_block: int = 48) -> tuple[LowOrderExpansion, object]:
    rec = repeated_fault_records(plan, context, rounds)
    if decoder_kind == 'history':
        dec = build_repeated_history_decoder(plan, context, rounds, records=rec)
    elif decoder_kind == 'detector_pair':
        dec = build_detector_pair_decoder(plan, context, rounds, reference_p, records=rec)
    else:
        raise ValueError(decoder_kind)
    c1, c2, n1, n2, pair_sub, total = exact_c1_c2(rec, dec, pair_block=pair_block)
    raw_t3, raw_se, frac = estimate_raw_t3(rec, dec, triple_samples, seed)
    # For independent categorical locations and C1=0, the p^3 Taylor term is
    # raw three-fault failures minus the no-fault expansion of malignant pairs.
    # If C1 is nonzero this truncated formula is intentionally not advertised as
    # a complete third-order coefficient.
    c3 = float(raw_t3 - pair_sub) if c1 == 0.0 else float('nan')
    c3_se = float(raw_se) if c1 == 0.0 else float('nan')
    return LowOrderExpansion(
        c1=float(c1), c2=float(c2), malignant_single_outcomes=int(n1),
        malignant_pair_outcomes=int(n2), pair_no_fault_correction=float(pair_sub),
        raw_t3_estimate=float(raw_t3), raw_t3_se=float(raw_se),
        c3_taylor_estimate=c3, c3_taylor_se=c3_se,
        triple_samples=int(triple_samples), triple_failure_fraction=float(frac),
        total_location_rate=float(total),
    ), dec


def compare_decoders_finite_p(plan: TimedRoundPlan, context: HardwareContext, rounds: int,
                              p: float, shots: int, seed: int,
                              detector_reference_p: float | None = None,
                              batch_size: int = 5000) -> dict:
    """Paired Monte Carlo comparison of three decoders on identical fault shots."""
    if p < 0 or shots <= 0:
        raise ValueError('invalid p/shots')
    rec = repeated_fault_records(plan, context, rounds)
    hist = build_repeated_history_decoder(plan, context, rounds, records=rec)
    det = build_detector_pair_decoder(plan, context, rounds,
                                      reference_p=float(detector_reference_p or max(p, 1e-12)),
                                      records=rec)
    locations = np.unique(rec.location)
    groups = [np.flatnonzero(rec.location == loc) for loc in locations]
    max_rate = max((float(rec.weight[idx].sum()) for idx in groups), default=0.0)
    if p * max_rate > 1:
        raise ValueError('p makes a physical-location probability exceed 1')
    canon, _, _, _ = code_tables()
    rng = np.random.default_rng(seed)
    failures = {'history_lookup': 0, 'detector_pair': 0, 'temporal_majority': 0}
    for start in range(0, shots, batch_size):
        b = min(batch_size, shots - start)
        data = np.zeros(b, dtype=np.int32)
        sh = np.zeros(b, dtype=np.int64)
        fh = np.zeros(b, dtype=np.int64)
        for idx in groups:
            probs = p * rec.weight[idx]
            cum = np.cumsum(probs)
            draw = np.searchsorted(cum, rng.random(b), side='right')
            data ^= np.append(rec.data[idx], 0)[draw]
            sh ^= np.append(rec.syndrome_history[idx], 0)[draw]
            fh ^= np.append(rec.flag_history[idx], 0)[draw]
        ch = _history_corrections_for(hist, sh, fh)
        cd = det.corrections_for(sh, fh)
        uniq, inv = np.unique(sh, return_inverse=True)
        cm_u = np.asarray([standard_steane_history_correction(int(h), rounds) for h in uniq], dtype=np.int32)
        cm = cm_u[inv]
        failures['history_lookup'] += int(np.count_nonzero(canon[data ^ ch]))
        failures['detector_pair'] += int(np.count_nonzero(canon[data ^ cd]))
        failures['temporal_majority'] += int(np.count_nonzero(canon[data ^ cm]))
    out = {
        'p': float(p), 'shots': int(shots), 'seed': int(seed), 'rounds': int(rounds),
        'native_cx_per_round': int(plan.native.native_cx),
        'duration_us_per_round': float(plan.duration_ns / 1000.0),
        'detector_primitive_count': int(det.primitive_count),
        'detector_map_entries': int(det.map_entries),
        'detector_single_fault_conflicts': int(det.single_fault_conflicts),
        'detector_single_fault_failures': int(det.single_fault_failures),
        'detector_incoming_failures': int(det.incoming_failures),
        'history_single_fault_conflicts': int(hist.single_fault_conflicts),
        'history_single_fault_failures': int(hist.single_fault_failures),
        'history_incoming_failures': int(hist.incoming_failures),
    }
    for name, f in failures.items():
        out[name] = {'failures': int(f), 'logical_failure_rate': float(f / shots)}
    return out



def compare_decoders_sweep(plan: TimedRoundPlan, context: HardwareContext, rounds: int,
                           ps: Iterable[float], shots: int, seeds: Iterable[int],
                           batch_size: int = 5000) -> list[dict]:
    """Multi-p decoder comparison reusing one repeated-fault catalog.

    This is equivalent to repeated calls to compare_decoders_finite_p but avoids
    rebuilding the several-thousand-location repeated fault model at every p.
    """
    ps = [float(x) for x in ps]
    seeds = [int(x) for x in seeds]
    if len(ps) != len(seeds):
        raise ValueError('ps and seeds must have the same length')
    rec = repeated_fault_records(plan, context, rounds)
    hist = build_repeated_history_decoder(plan, context, rounds, records=rec)
    locations = np.unique(rec.location)
    groups = [np.flatnonzero(rec.location == loc) for loc in locations]
    max_rate = max((float(rec.weight[idx].sum()) for idx in groups), default=0.0)
    canon, _, _, _ = code_tables()
    results = []
    for p, seed in zip(ps, seeds):
        if p < 0 or shots <= 0:
            raise ValueError('invalid p/shots')
        if p * max_rate > 1:
            raise ValueError('p makes a physical-location probability exceed 1')
        det = build_detector_pair_decoder(plan, context, rounds, reference_p=max(p, 1e-12), records=rec)
        rng = np.random.default_rng(seed)
        failures = {'history_lookup': 0, 'detector_pair': 0, 'temporal_majority': 0}
        for start in range(0, shots, batch_size):
            b = min(batch_size, shots - start)
            data = np.zeros(b, dtype=np.int32)
            sh = np.zeros(b, dtype=np.int64)
            fh = np.zeros(b, dtype=np.int64)
            for idx in groups:
                probs = p * rec.weight[idx]
                cum = np.cumsum(probs)
                draw = np.searchsorted(cum, rng.random(b), side='right')
                data ^= np.append(rec.data[idx], 0)[draw]
                sh ^= np.append(rec.syndrome_history[idx], 0)[draw]
                fh ^= np.append(rec.flag_history[idx], 0)[draw]
            ch = _history_corrections_for(hist, sh, fh)
            cd = det.corrections_for(sh, fh)
            uniq, inv = np.unique(sh, return_inverse=True)
            cm_u = np.asarray([standard_steane_history_correction(int(h), rounds) for h in uniq], dtype=np.int32)
            cm = cm_u[inv]
            failures['history_lookup'] += int(np.count_nonzero(canon[data ^ ch]))
            failures['detector_pair'] += int(np.count_nonzero(canon[data ^ cd]))
            failures['temporal_majority'] += int(np.count_nonzero(canon[data ^ cm]))
        out = {
            'p': float(p), 'shots': int(shots), 'seed': int(seed), 'rounds': int(rounds),
            'native_cx_per_round': int(plan.native.native_cx),
            'duration_us_per_round': float(plan.duration_ns / 1000.0),
            'detector_primitive_count': int(det.primitive_count),
            'detector_map_entries': int(det.map_entries),
            'detector_single_fault_conflicts': int(det.single_fault_conflicts),
            'detector_single_fault_failures': int(det.single_fault_failures),
            'detector_incoming_failures': int(det.incoming_failures),
            'history_single_fault_conflicts': int(hist.single_fault_conflicts),
            'history_single_fault_failures': int(hist.single_fault_failures),
            'history_incoming_failures': int(hist.incoming_failures),
        }
        for name, f in failures.items():
            out[name] = {'failures': int(f), 'logical_failure_rate': float(f / shots)}
        results.append(out)
    return results

def fit_loglog_slope(points: Iterable[tuple[float, float]]) -> float:
    vals = [(float(p), float(r)) for p, r in points if p > 0 and r > 0]
    if len(vals) < 2:
        return float('nan')
    x = np.log([x[0] for x in vals])
    y = np.log([x[1] for x in vals])
    return float(np.polyfit(x, y, 1)[0])
