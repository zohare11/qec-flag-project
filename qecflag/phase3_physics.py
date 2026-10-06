"""Exact Pauli-frame model for Phase 3 sequential flag-schedule synthesis.

This extends the Phase-1 one-flag Steane Z-check model to two *available* flag
ancillas. A synthesized circuit still has a fixed grammar: the four data-to-
syndrome CNOTs occur once each, and flag ancilla A and/or B may each interact
with the syndrome exactly twice. The order is synthesized sequentially.

The model remains a single flagged stabilizer-check component with an ideal
final six-bit syndrome and perfect recovery oracle. It is not a full noisy QEC
cycle and it is not unrestricted quantum-circuit synthesis.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from collections import Counter
from typing import Iterable
import numpy as np

from .physics import code_tables, weight, MEASURED

N_DATA = 7
N = 10
SYN = 7
FLAG_A = 8
FLAG_B = 9
DATA_MASK = (1 << N_DATA) - 1

# Phase-3 event-weight features:
#   0..2: syndrome / flag-A / flag-B preparation faults
#   3..92: six directed CNOT edge types x 15 non-identity Pauli faults
#           (data0..data3, flagA, flagB -> syndrome)
#   93..95: syndrome / flag-A / flag-B measurement faults
F3 = 96

PREP_SYN = 0
PREP_A = 1
PREP_B = 2
EDGE_START = 3
MEAS_SYN = 93
MEAS_A = 94
MEAS_B = 95

TOKENS = (0, 1, 2, 3, FLAG_A, FLAG_B)
ACTION_NAMES = ('D0', 'D1', 'D2', 'D3', 'A', 'B', 'STOP')
STOP_ACTION = 6


def local_pauli(code: int, qubit: int, n: int = N) -> int:
    """Local Pauli encoding: 0=I, 1=X, 2=Z, 3=Y."""
    return ((code & 1) << qubit) | (((code >> 1) & 1) << (n + qubit))


def cx_frame(p: int, control: int, target: int = SYN, n: int = N) -> int:
    x = p & ((1 << n) - 1)
    z = p >> n
    if (x >> control) & 1:
        x ^= 1 << target
    if (z >> target) & 1:
        z ^= 1 << control
    return x | (z << n)


def data_part(p: int) -> int:
    return (p & DATA_MASK) | (((p >> N) & DATA_MASK) << N_DATA)


def propagate(schedule: tuple[int, ...], p: int, start: int = 0) -> int:
    for control in schedule[start:]:
        p = cx_frame(p, control, SYN)
    return p


def schedule_label(schedule: Iterable[int]) -> str:
    return ''.join('A' if q == FLAG_A else 'B' if q == FLAG_B else str(int(q)) for q in schedule)


def schedule_from_label(label: str) -> tuple[int, ...]:
    mapping = {'A': FLAG_A, 'B': FLAG_B, '0': 0, '1': 1, '2': 2, '3': 3}
    try:
        schedule = tuple(mapping[c] for c in label)
    except KeyError as exc:
        raise ValueError('Phase-3 labels use only 0,1,2,3,A,B.') from exc
    if sorted(q for q in schedule if q < 4) != [0, 1, 2, 3]:
        raise ValueError('Each data coupling 0,1,2,3 must occur exactly once.')
    if schedule.count(FLAG_A) not in (0, 2) or schedule.count(FLAG_B) not in (0, 2):
        raise ValueError('Each used flag must appear exactly twice.')
    if schedule.count(FLAG_A) + schedule.count(FLAG_B) == 0:
        raise ValueError('At least one flag pair is required in Phase 3.')
    return schedule


def schedule_kind(schedule: tuple[int, ...]) -> str:
    a, b = schedule.count(FLAG_A), schedule.count(FLAG_B)
    if (a, b) == (2, 0):
        return 'A_only'
    if (a, b) == (0, 2):
        return 'B_only'
    if (a, b) == (2, 2):
        return 'A_and_B'
    return 'invalid'


def _multiset_permutations(items: tuple[int, ...]):
    counter = Counter(items)
    keys = sorted(counter)
    n = len(items)

    def rec(prefix: list[int]):
        if len(prefix) == n:
            yield tuple(prefix)
            return
        for key in keys:
            if counter[key]:
                counter[key] -= 1
                prefix.append(key)
                yield from rec(prefix)
                prefix.pop()
                counter[key] += 1

    yield from rec([])


def candidate_schedules(mode: str = 'expanded'):
    """Enumerate the finite grammar used for verification/oracle comparisons.

    single_A: 360 six-CNOT schedules using only flag A.
    expanded: A-only + B-only + both-flags schedules = 10,800 candidates.
    """
    if mode == 'single_A':
        yield from _multiset_permutations((0, 1, 2, 3, FLAG_A, FLAG_A))
        return
    if mode != 'expanded':
        raise ValueError("mode must be 'single_A' or 'expanded'")
    yield from _multiset_permutations((0, 1, 2, 3, FLAG_A, FLAG_A))
    yield from _multiset_permutations((0, 1, 2, 3, FLAG_B, FLAG_B))
    yield from _multiset_permutations((0, 1, 2, 3, FLAG_A, FLAG_A, FLAG_B, FLAG_B))


@dataclass
class FaultRecords:
    data: np.ndarray
    flags: np.ndarray
    category: np.ndarray
    location: np.ndarray
    full: np.ndarray
    suffix_start: np.ndarray
    injection: np.ndarray


def _edge_index(control: int) -> int:
    if 0 <= control <= 3:
        return control
    if control == FLAG_A:
        return 4
    if control == FLAG_B:
        return 5
    raise ValueError(f'Unknown control {control}')


def fault_records(schedule: tuple[int, ...]) -> FaultRecords:
    used_a = FLAG_A in schedule
    used_b = FLAG_B in schedule
    entries: list[tuple[int, int, int, int]] = []

    # Independent preparation locations.
    entries.append((PREP_SYN, 0, 0, local_pauli(1, SYN)))
    if used_a:
        entries.append((PREP_A, 1, 0, local_pauli(2, FLAG_A)))
    if used_b:
        entries.append((PREP_B, 2, 0, local_pauli(2, FLAG_B)))

    # A two-qubit Pauli occurs after an otherwise ideal CNOT.
    for gate_index, control in enumerate(schedule):
        edge = _edge_index(control)
        for a in range(4):
            for b in range(4):
                if a == b == 0:
                    continue
                local_index = 4 * a + b - 1
                category = EDGE_START + 15 * edge + local_index
                injection = local_pauli(a, control) ^ local_pauli(b, SYN)
                entries.append((category, 3 + gate_index, gate_index + 1, injection))

    # Measurement-bit faults as Paulis immediately before ideal measurements.
    base = 3 + len(schedule)
    entries.append((MEAS_SYN, base, len(schedule), local_pauli(1, SYN)))
    if used_a:
        entries.append((MEAS_A, base + 1, len(schedule), local_pauli(2, FLAG_A)))
    if used_b:
        entries.append((MEAS_B, base + 2, len(schedule), local_pauli(2, FLAG_B)))

    category, location, start, injections = (np.asarray(v, dtype=np.int32) for v in zip(*entries))
    full = np.asarray([propagate(schedule, int(p), int(s)) for p, s in zip(injections, start)], dtype=np.int64)
    data = np.asarray([data_part(int(p)) for p in full], dtype=np.int32)
    flags = np.zeros(len(full), dtype=np.int8)
    flags |= (((full >> (N + FLAG_A)) & 1).astype(np.int8) << 0)
    flags |= (((full >> (N + FLAG_B)) & 1).astype(np.int8) << 1)
    return FaultRecords(data, flags, category, location, full, start, injections)


def decoder_and_certificate(schedule: tuple[int, ...]) -> tuple[np.ndarray, dict]:
    """Certify the schedule under the same perfect-final-recovery experiment.

    The decoder observes a hypothetical noiseless six-bit Steane syndrome plus
    the two possible flag measurement bits. This checks all single component
    faults and all single incoming data Paulis; it does not certify a complete
    repeated noisy syndrome-extraction protocol.
    """
    canon, minweights, syndromes, fallback = code_tables()
    rec = fault_records(schedule)
    decoder = np.tile(fallback, 4)
    observations: dict[int, int] = {}
    conflicts = []

    incoming = [0] + [local_pauli(p, q, n=7) for q in range(7) for p in (1, 2, 3)]
    inputs = [(p, 0, 'incoming') for p in incoming]
    inputs.extend((int(p), int(f), f'fault:{i}') for i, (p, f) in enumerate(zip(rec.data, rec.flags)))
    for error, flag_bits, origin in inputs:
        key = 64 * flag_bits + int(syndromes[error])
        if key in observations and canon[observations[key]] != canon[error]:
            conflicts.append({'observation': key, 'origin': origin, 'error': int(error)})
        else:
            observations[key] = int(error)
    for key, error in observations.items():
        decoder[key] = error

    missed = [i for i, (p, f) in enumerate(zip(rec.data, rec.flags))
              if f == 0 and min(weight(int(p)), weight(int(p) ^ MEASURED)) > 1]
    corrected = rec.data ^ decoder[64 * rec.flags + syndromes[rec.data]]
    failed = int(np.count_nonzero(canon[corrected]))
    incoming_failed = sum(int(canon[p ^ decoder[int(syndromes[p])]] != 0) for p in incoming)
    report = {
        'schedule': schedule_label(schedule),
        'kind': schedule_kind(schedule),
        'cnot_count': len(schedule),
        'single_faults': int(len(rec.data)),
        'unflagged_hook_faults': int(len(missed)),
        'decoder_conflicts': int(len(conflicts)),
        'single_fault_recovery_failures': int(failed),
        'incoming_error_recovery_failures': int(incoming_failed),
        'certified': not (missed or conflicts or failed or incoming_failed),
        'example_missed_fault_indices': missed[:3],
    }
    return decoder, report


@lru_cache(maxsize=1)
def upper_pairs() -> tuple[np.ndarray, np.ndarray]:
    return np.triu_indices(F3)


def quadratic_risk_upper_counts(schedule: tuple[int, ...], decoder: np.ndarray) -> np.ndarray:
    """Integer coefficients c_ij such that C2(w)=sum_{i<=j} c_ij*w_i*w_j."""
    canon, _, syndromes, _ = code_tables()
    rec = fault_records(schedule)
    i, j = np.triu_indices(len(rec.data), 1)
    keep = rec.location[i] != rec.location[j]
    i, j = i[keep], j[keep]
    error = rec.data[i] ^ rec.data[j]
    flags = rec.flags[i] ^ rec.flags[j]
    corrected = error ^ decoder[64 * flags + syndromes[error]]
    malignant = canon[corrected] != 0
    ci = rec.category[i[malignant]]
    cj = rec.category[j[malignant]]
    lo = np.minimum(ci, cj)
    hi = np.maximum(ci, cj)

    # Compact map from unordered feature pair to triangular vector position.
    tri_i, tri_j = upper_pairs()
    pair_index = np.full((F3, F3), -1, dtype=np.int32)
    pair_index[tri_i, tri_j] = np.arange(len(tri_i), dtype=np.int32)
    index = pair_index[lo, hi]
    counts = np.zeros(len(tri_i), dtype=np.uint16)
    np.add.at(counts, index, 1)
    return counts


def quadratic_features(contexts: np.ndarray, dtype=np.float32) -> np.ndarray:
    contexts = np.atleast_2d(np.asarray(contexts, dtype=dtype))
    if contexts.shape[1] != F3:
        raise ValueError(f'Expected contexts with {F3} features')
    i, j = upper_pairs()
    return contexts[:, i] * contexts[:, j]


def ideal_dense_error(schedule: tuple[int, ...]) -> float:
    """Independent ideal-state check on the four support bits + S/A/B ancillas.

    Used flags start in |+>, syndrome in |0>. The expected final state has the
    syndrome equal to data parity, flags restored to |+>, and data unchanged.
    This check is independent of the binary-Pauli fault propagator above.
    """
    # Local qubits: data0..3=0..3, syndrome=4, flagA=5, flagB=6.
    nq = 7
    dim = 1 << nq
    used_a = FLAG_A in schedule
    used_b = FLAG_B in schedule
    worst = 0.0
    local_control = {0: 0, 1: 1, 2: 2, 3: 3, FLAG_A: 5, FLAG_B: 6}

    for data_bits in range(16):
        state = np.zeros(dim, dtype=np.complex128)
        # Build |data>|S=0> with used flag(s) in |+>.
        flag_values = [(0,)]
        if used_a and used_b:
            flag_values = [(a, b) for a in (0, 1) for b in (0, 1)]
        elif used_a:
            flag_values = [(a,) for a in (0, 1)]
        elif used_b:
            flag_values = [(b,) for b in (0, 1)]
        amp = 1 / np.sqrt(len(flag_values))
        for vals in flag_values:
            idx = data_bits
            if used_a:
                a = vals[0]
                idx |= a << 5
            if used_b:
                b = vals[-1]
                idx |= b << 6
            state[idx] = amp

        # Apply CNOTs by basis permutation.
        for control in schedule:
            c = local_control[control]
            new = np.zeros_like(state)
            for idx, amplitude in enumerate(state):
                if amplitude == 0:
                    continue
                out = idx ^ ((1 << 4) if ((idx >> c) & 1) else 0)
                new[out] += amplitude
            state = new

        target = np.zeros_like(state)
        parity = data_bits.bit_count() & 1
        for vals in flag_values:
            idx = data_bits | (parity << 4)
            if used_a:
                idx |= vals[0] << 5
            if used_b:
                idx |= vals[-1] << 6
            target[idx] = amp
        worst = max(worst, float(np.max(np.abs(state - target))))
    return worst
