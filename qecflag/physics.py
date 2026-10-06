"""Exact binary-Pauli model of one flagged Steane Z check.

Qubits 0..6: data; 7: syndrome; 8: flag. Paulis are encoded as
x | (z << n), with qubit 0 the least-significant bit. Global Pauli phases
are deliberately ignored for fault propagation, NOT for ideal-state tests.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations, permutations
import numpy as np

N_DATA = 7
N = 9
SYN = 7
FLAG = 8
SUPPORTS = (0b0001111, 0b0110011, 0b1010101)
GENERATORS = tuple(SUPPORTS) + tuple(v << 7 for v in SUPPORTS)
MEASURED = SUPPORTS[0] << 7
FULL_MASK = (1 << N) - 1
DATA_MASK = (1 << N_DATA) - 1
# Categories: two preparation errors, five directed CNOT edges x 15 Paulis,
# and two measurement-bit errors. An outcome labeled II is never a fault.
F = 79


def weight(p: int, n: int = 7) -> int:
    return ((int(p) & ((1 << n) - 1)) | (int(p) >> n)).bit_count()


def commutes(a: int, b: int, n: int = 7) -> bool:
    mask = (1 << n) - 1
    return ((((a & mask) & (b >> n)) ^ ((a >> n) & (b & mask))).bit_count() % 2) == 0


@lru_cache(maxsize=1)
def code_tables() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    stabs = np.array([0], dtype=np.int32)
    for generator in GENERATORS:
        stabs = np.concatenate([stabs, stabs ^ generator])
    all_p = np.arange(1 << 14, dtype=np.int32)
    canon = np.min(all_p[:, None] ^ stabs[None, :], axis=1)
    weights = np.array([weight(p) for p in all_p], dtype=np.int8)
    minweights = np.min(weights[all_p[:, None] ^ stabs[None, :]], axis=1)
    syndromes = np.array([
        sum((not commutes(int(p), s)) << j for j, s in enumerate(GENERATORS))
        for p in all_p
    ], dtype=np.int16)
    # Deterministic minimum-weight decoder; ties broken by Pauli integer.
    fallback = np.zeros(64, dtype=np.int32)
    for syndrome in range(64):
        candidates = all_p[syndromes == syndrome]
        fallback[syndrome] = min(candidates, key=lambda p: (int(weights[p]), int(p)))
    return canon, minweights, syndromes, fallback


def cx_frame(p: int, control: int, target: int, n: int = N) -> int:
    x = p & ((1 << n) - 1)
    z = p >> n
    if (x >> control) & 1:
        x ^= 1 << target
    if (z >> target) & 1:
        z ^= 1 << control
    return x | (z << n)


def local_pauli(code: int, qubit: int, n: int = N) -> int:
    """Local codes 0=I, 1=X, 2=Z, 3=Y."""
    return ((code & 1) << qubit) | (((code >> 1) & 1) << (n + qubit))


def data_part(p: int) -> int:
    return (p & DATA_MASK) | (((p >> N) & DATA_MASK) << N_DATA)


def labels(schedule: tuple[int, ...]) -> str:
    return ''.join('F' if q == FLAG else str(q) for q in schedule)


def schedule_from_label(label: str) -> tuple[int, ...]:
    try:
        result = tuple(FLAG if c == 'F' else int(c) for c in label)
    except ValueError as exc:
        raise ValueError('Schedule must contain 0,1,2,3 and optionally two F characters.') from exc
    if sorted(q for q in result if q != FLAG) != [0, 1, 2, 3] or result.count(FLAG) not in (0, 2):
        raise ValueError('Schedule must contain each data label once and zero or two Fs.')
    return result


def candidate_schedules() -> list[tuple[int, ...]]:
    schedules = []
    for data_order in permutations(range(4)):
        for pos in combinations(range(6), 2):
            it = iter(data_order)
            schedules.append(tuple(FLAG if i in pos else next(it) for i in range(6)))
    return sorted(schedules, key=labels)


@dataclass
class FaultRecords:
    data: np.ndarray
    flag: np.ndarray
    category: np.ndarray
    location: np.ndarray
    full: np.ndarray
    suffix_start: np.ndarray
    injection: np.ndarray


def propagate(schedule: tuple[int, ...], p: int, start: int = 0) -> int:
    for control in schedule[start:]:
        p = cx_frame(p, control, SYN)
    return p


def fault_records(schedule: tuple[int, ...]) -> FaultRecords:
    entries = []
    # Faults immediately after ideal |0> and |+> preparation.
    for category, p in ((0, local_pauli(1, SYN)), (1, local_pauli(2, FLAG))):
        entries.append((category, category, 0, p))
    for gate_index, control in enumerate(schedule):
        edge = 4 if control == FLAG else control
        for a in range(4):
            for b in range(4):
                if a == b == 0:
                    continue
                local_index = 4 * a + b - 1
                category = 2 + 15 * edge + local_index
                p = local_pauli(a, control) ^ local_pauli(b, SYN)
                entries.append((category, 2 + gate_index, gate_index + 1, p))
    entries.extend(((77, 2 + len(schedule), len(schedule), local_pauli(1, SYN)),
                    (78, 3 + len(schedule), len(schedule), local_pauli(2, FLAG))))
    category, location, start, injections = (np.array(v, dtype=np.int32) for v in zip(*entries))
    full = np.array([propagate(schedule, int(p), int(s)) for p, s in zip(injections, start)], dtype=np.int32)
    data = np.array([data_part(int(p)) for p in full], dtype=np.int32)
    flag = ((full >> (N + FLAG)) & 1).astype(np.int8)
    return FaultRecords(data, flag, category, location, full, start, injections)


def decoder_and_certificate(schedule: tuple[int, ...]) -> tuple[np.ndarray, dict]:
    """Check one-fault flagging AND correctability given a perfect final syndrome.

    This is NOT a complete noisy syndrome-extraction protocol. The decoder gets
    a hypothetical noiseless six-bit syndrome after this single measurement.
    """
    canon, minweights, syndromes, fallback = code_tables()
    rec = fault_records(schedule)
    decoder = np.tile(fallback, 2)
    observations: dict[int, int] = {}
    conflicts = []
    incoming = [0] + [local_pauli(p, q, n=7) for q in range(7) for p in (1, 2, 3)]
    inputs = [(p, 0, 'incoming') for p in incoming]
    inputs.extend((int(p), int(f), f'fault:{i}') for i, (p, f) in enumerate(zip(rec.data, rec.flag)))
    for error, flag, origin in inputs:
        key = 64 * flag + int(syndromes[error])
        if key in observations and canon[observations[key]] != canon[error]:
            conflicts.append({'observation': key, 'origin': origin, 'error': error})
        else:
            observations[key] = error
    for key, error in observations.items():
        decoder[key] = error
    missed = [i for i, (p, f) in enumerate(zip(rec.data, rec.flag))
              if f == 0 and min(weight(int(p)), weight(int(p) ^ MEASURED)) > 1]
    failed = int(np.count_nonzero(canon[rec.data ^ decoder[64 * rec.flag + syndromes[rec.data]]]))
    # All single incoming errors must be corrected with no circuit fault.
    incoming_failed = sum(int(canon[p ^ decoder[int(syndromes[p])]] != 0) for p in incoming)
    report = {'schedule': labels(schedule), 'cnot_count': len(schedule),
              'single_faults': len(rec.data), 'unflagged_hook_faults': len(missed),
              'decoder_conflicts': len(conflicts), 'single_fault_recovery_failures': failed,
              'incoming_error_recovery_failures': incoming_failed,
              'certified': not (missed or conflicts or failed or incoming_failed),
              'example_missed_fault_indices': missed[:3]}
    return decoder, report


def quadratic_risk_matrix(schedule: tuple[int, ...], decoder: np.ndarray) -> np.ndarray:
    """C2(w) = sum_{different-location malignant pairs i<j} w_i*w_j.

    p_L(p,w) = C2(w)*p**2 + O(p**3) only for certified schedules, independent
    stochastic Pauli faults, and the documented perfect-final-recovery experiment.
    A same-location pair is impossible and MUST be excluded.
    """
    canon, _, syndromes, _ = code_tables()
    rec = fault_records(schedule)
    i, j = np.triu_indices(len(rec.data), 1)
    keep = rec.location[i] != rec.location[j]
    i, j = i[keep], j[keep]
    error = rec.data[i] ^ rec.data[j]
    flag = rec.flag[i] ^ rec.flag[j]
    corrected = error ^ decoder[64 * flag + syndromes[error]]
    malignant = canon[corrected] != 0
    matrix = np.zeros((F, F), dtype=np.float64)
    np.add.at(matrix, (rec.category[i[malignant]], rec.category[j[malignant]]), 1.0)
    # Symmetric form is more convenient for deterministic optimization.
    return (matrix + matrix.T) / 2
