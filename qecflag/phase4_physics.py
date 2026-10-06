"""Phase 4: one noisy *full* Steane syndrome-extraction round.

The round measures the three X stabilizers followed by the three Z stabilizers.
Each check uses a Phase-3-certified local flagged interaction template.  The
round is evaluated as a memory-style experiment with ideal initial/final
boundaries: the noisy extraction record (six syndrome bits + up to two flag
bits per check) and a final ideal six-bit syndrome are supplied to an explicit
flag-aware lookup decoder.

This is materially stronger than the Phase-3 perfect-recovery component model,
but it is still a controlled simulator rather than a hardware-level QEC stack:
there is one noisy extraction round, serial checks, synthetic Pauli noise, and
ideal boundaries.  No claim of unrestricted circuit synthesis is implied.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable
import numpy as np

from .physics import SUPPORTS, code_tables, commutes
from .phase3_physics import (
    FLAG_A, FLAG_B, schedule_from_label, schedule_kind,
)

N_DATA = 7
N_LOCAL = 10
SYN = 7
A = FLAG_A
B = FLAG_B
LOCAL_FEATURES = 96
N_CHECKS = 6
ROUND_FEATURES = LOCAL_FEATURES * N_CHECKS
OBS_ROUND_BITS = 18  # syndrome,A,B for each of six checks
OBS_FINAL_SHIFT = OBS_ROUND_BITS

# X checks first, then Z checks.  This fixed block ordering preserves the joint
# ideal measurement without needing a separate global timing scheduler.
_SUPPORT_LIST = tuple(tuple(q for q in range(7) if (mask >> q) & 1) for mask in SUPPORTS)
CHECKS = tuple([('X', s) for s in _SUPPORT_LIST] + [('Z', s) for s in _SUPPORT_LIST])
CHECK_NAMES = ('X0', 'X1', 'X2', 'Z0', 'Z1', 'Z2')

# Standard Steane logical representatives.
LOGICAL_X = (1 << 7) - 1
LOGICAL_Z = ((1 << 7) - 1) << 7


def _local_pauli(code: int, qubit: int, n: int = N_LOCAL) -> int:
    """Local Pauli code: 0=I, 1=X, 2=Z, 3=Y."""
    return ((code & 1) << qubit) | (((code >> 1) & 1) << (n + qubit))


def _cx_frame(p: int, control: int, target: int, n: int = N_LOCAL) -> int:
    x = p & ((1 << n) - 1)
    z = p >> n
    if (x >> control) & 1:
        x ^= 1 << target
    if (z >> target) & 1:
        z ^= 1 << control
    return x | (z << n)


def _data_to_local(p: int) -> int:
    mask = (1 << 7) - 1
    return (p & mask) | (((p >> 7) & mask) << N_LOCAL)


def _local_to_data(p: int) -> int:
    mask = (1 << 7) - 1
    return (p & mask) | (((p >> N_LOCAL) & mask) << 7)


def _measurement_flip(frame: int, qubit: int, basis: str) -> int:
    if basis == 'Z':
        return (frame >> qubit) & 1
    if basis == 'X':
        return (frame >> (N_LOCAL + qubit)) & 1
    raise ValueError("basis must be 'X' or 'Z'")


def _mapped_tokens(label: str, support: tuple[int, ...]) -> tuple[int, ...]:
    template = schedule_from_label(label)
    return tuple(support[token] if token < 4 else token for token in template)


def _operations(check_type: str, support: tuple[int, ...], label: str) -> tuple[tuple[int, int, int], ...]:
    """Return (control,target,template-token) for a local check.

    Z check: data/flag -> syndrome target.
    X check: Hadamard-dual orientation, syndrome control -> data/flag.
    The third field deliberately preserves the *local template token* (0..3,A,B)
    so noise-category indexing does not depend on the physical support labels.
    """
    ops = []
    template = schedule_from_label(label)
    for local_token in template:
        physical = support[local_token] if local_token < 4 else local_token
        if check_type == 'Z':
            ops.append((physical, SYN, local_token))
        elif check_type == 'X':
            ops.append((SYN, physical, local_token))
        else:
            raise ValueError(f'Unknown check type {check_type!r}')
    return tuple(ops)


def _edge_slot(template_token: int) -> int:
    if 0 <= template_token <= 3:
        return template_token
    if template_token == A:
        return 4
    if template_token == B:
        return 5
    raise ValueError(f'Unknown template token {template_token}')


def _prep_codes(check_type: str) -> tuple[int, int]:
    # Z check: syndrome |0>, flags |+>; X check is the H-dual.
    return (1, 2) if check_type == 'Z' else (2, 1)


def _measurement_codes(check_type: str) -> tuple[int, int]:
    # Same Pauli representatives as preparation faults immediately before the
    # corresponding ideal measurement.
    return (1, 2) if check_type == 'Z' else (2, 1)


def _measurement_bases(check_type: str) -> tuple[str, str]:
    return ('Z', 'X') if check_type == 'Z' else ('X', 'Z')


def validate_round_labels(labels: Iterable[str]) -> tuple[str, ...]:
    result = tuple(str(x) for x in labels)
    if len(result) != N_CHECKS:
        raise ValueError(f'Expected {N_CHECKS} local schedules')
    for label in result:
        schedule = schedule_from_label(label)
        if schedule_kind(schedule) not in ('A_only', 'B_only', 'A_and_B'):
            raise ValueError(f'Invalid Phase-4 local template {label!r}')
    return result


@dataclass(frozen=True)
class FaultDescriptor:
    kind: str
    check: int
    index: int
    pauli_a: int = 0
    pauli_b: int = 0
    qubit: int = -1


@dataclass
class RoundFaultRecords:
    data: np.ndarray
    observation: np.ndarray
    category: np.ndarray
    location: np.ndarray
    descriptors: tuple[FaultDescriptor, ...]


@dataclass
class RoundDecoder:
    keys: np.ndarray
    corrections: np.ndarray
    single_fault_conflicts: int
    single_fault_failures: int
    incoming_failures: int

    def corrections_for(self, observations: np.ndarray) -> np.ndarray:
        """Vectorized lookup with final-boundary minimum-weight fallback."""
        _, _, _, fallback = code_tables()
        obs = np.asarray(observations, dtype=np.int64)
        result = fallback[((obs >> OBS_FINAL_SHIFT) & 63)].astype(np.int32).copy()
        if len(self.keys) == 0:
            return result
        pos = np.searchsorted(self.keys, obs)
        safe = np.minimum(pos, len(self.keys) - 1)
        seen = (pos < len(self.keys)) & (self.keys[safe] == obs)
        if np.any(seen):
            result[seen] = self.corrections[pos[seen]]
        return result


@dataclass
class RoundRisk:
    labels: tuple[str, ...]
    pair_i: np.ndarray
    pair_j: np.ndarray
    pair_count: np.ndarray
    fault_count: int
    malignant_pair_count: int
    decoder: RoundDecoder

    def c2(self, context: np.ndarray) -> float:
        w = np.asarray(context, dtype=np.float64)
        if w.shape == (N_CHECKS, LOCAL_FEATURES):
            w = w.reshape(-1)
        if w.shape != (ROUND_FEATURES,):
            raise ValueError(f'Expected context shape (6,96) or ({ROUND_FEATURES},)')
        return float(np.sum(self.pair_count * w[self.pair_i] * w[self.pair_j]))


def simulate_round(labels: Iterable[str], fault: FaultDescriptor | None = None,
                   incoming_data: int = 0) -> tuple[int, int]:
    """Propagate one Pauli-frame fault through the full six-check round.

    The returned observation packs 18 noisy extraction bits followed by the
    final *ideal boundary* six-bit Steane syndrome.  The boundary is used only
    for the memory-style decoder/evaluation and is not a noisy seventh check.
    """
    labels = validate_round_labels(labels)
    frame = _data_to_local(int(incoming_data))
    observation = 0
    bitpos = 0

    for ci, ((check_type, support), label) in enumerate(zip(CHECKS, labels)):
        template = schedule_from_label(label)
        used_a = A in template
        used_b = B in template
        prep_syn, prep_flag = _prep_codes(check_type)
        meas_syn, meas_flag = _measurement_codes(check_type)

        if fault is not None and fault.kind == 'prep' and fault.check == ci:
            frame ^= _local_pauli(fault.pauli_a, fault.qubit)

        for gi, (control, target, _token) in enumerate(_operations(check_type, support, label)):
            frame = _cx_frame(frame, control, target)
            if fault is not None and fault.kind == 'gate' and fault.check == ci and fault.index == gi:
                frame ^= _local_pauli(fault.pauli_a, control)
                frame ^= _local_pauli(fault.pauli_b, target)

        if fault is not None and fault.kind == 'meas' and fault.check == ci:
            frame ^= _local_pauli(fault.pauli_a, fault.qubit)

        syn_basis, flag_basis = _measurement_bases(check_type)
        observation |= int(_measurement_flip(frame, SYN, syn_basis)) << bitpos
        bitpos += 1
        observation |= (int(_measurement_flip(frame, A, flag_basis)) if used_a else 0) << bitpos
        bitpos += 1
        observation |= (int(_measurement_flip(frame, B, flag_basis)) if used_b else 0) << bitpos
        bitpos += 1

        # Ideal measurement + reset discards each check's ancillas.  Their
        # propagated effect on data and classical outcomes has already been kept.
        for qubit in (SYN, A, B):
            frame &= ~(1 << qubit)
            frame &= ~(1 << (N_LOCAL + qubit))

    data = _local_to_data(frame)
    _, _, syndromes, _ = code_tables()
    observation |= int(syndromes[data]) << OBS_FINAL_SHIFT
    return int(data), int(observation)


def fault_records(labels: Iterable[str]) -> RoundFaultRecords:
    labels = validate_round_labels(labels)
    descriptors: list[FaultDescriptor] = []
    categories: list[int] = []
    locations: list[int] = []

    for ci, ((check_type, support), label) in enumerate(zip(CHECKS, labels)):
        template = schedule_from_label(label)
        used_a = A in template
        used_b = B in template
        base = ci * LOCAL_FEATURES
        prep_syn, prep_flag = _prep_codes(check_type)
        meas_syn, meas_flag = _measurement_codes(check_type)

        # Preparation locations.
        descriptors.append(FaultDescriptor('prep', ci, 0, prep_syn, qubit=SYN))
        categories.append(base + 0)
        locations.append(ci * 32 + 0)
        if used_a:
            descriptors.append(FaultDescriptor('prep', ci, 1, prep_flag, qubit=A))
            categories.append(base + 1)
            locations.append(ci * 32 + 1)
        if used_b:
            descriptors.append(FaultDescriptor('prep', ci, 2, prep_flag, qubit=B))
            categories.append(base + 2)
            locations.append(ci * 32 + 2)

        # CNOT locations.  One of 15 non-identity two-qubit Pauli outcomes is
        # selected when the location faults.
        for gi, (_control, _target, token) in enumerate(_operations(check_type, support, label)):
            edge = _edge_slot(token)
            for pa in range(4):
                for pb in range(4):
                    if pa == pb == 0:
                        continue
                    local_index = 4 * pa + pb - 1
                    descriptors.append(FaultDescriptor('gate', ci, gi, pa, pb))
                    categories.append(base + 3 + 15 * edge + local_index)
                    locations.append(ci * 32 + 3 + gi)

        # Measurement-bit fault representatives.
        descriptors.append(FaultDescriptor('meas', ci, 0, meas_syn, qubit=SYN))
        categories.append(base + 93)
        locations.append(ci * 32 + 20)
        if used_a:
            descriptors.append(FaultDescriptor('meas', ci, 1, meas_flag, qubit=A))
            categories.append(base + 94)
            locations.append(ci * 32 + 21)
        if used_b:
            descriptors.append(FaultDescriptor('meas', ci, 2, meas_flag, qubit=B))
            categories.append(base + 95)
            locations.append(ci * 32 + 22)

    signatures = [simulate_round(labels, fault=d) for d in descriptors]
    return RoundFaultRecords(
        data=np.asarray([d for d, _ in signatures], dtype=np.int32),
        observation=np.asarray([o for _, o in signatures], dtype=np.int64),
        category=np.asarray(categories, dtype=np.int32),
        location=np.asarray(locations, dtype=np.int32),
        descriptors=tuple(descriptors),
    )


def _incoming_single_errors() -> list[int]:
    result = [0]
    for qubit in range(7):
        for code in (1, 2, 3):
            result.append(((code & 1) << qubit) | (((code >> 1) & 1) << (7 + qubit)))
    return result


def build_decoder(labels: Iterable[str], records: RoundFaultRecords | None = None) -> RoundDecoder:
    """Build a deterministic flag-aware lookup decoder from all single faults.

    The decoder is circuit-specific but *not* test-context-specific.  It gets the
    noisy round record and ideal final boundary syndrome.  Every observation seen
    under the no-fault case, a single incoming data Pauli, or one circuit fault is
    assigned the corresponding data-error equivalence class.  Unseen multi-fault
    observations fall back to the Steane minimum-weight correction for the final
    boundary syndrome.
    """
    labels = validate_round_labels(labels)
    records = fault_records(labels) if records is None else records
    canon, minweights, _, _ = code_tables()

    groups: dict[int, list[int]] = {}
    for error in _incoming_single_errors():
        data, obs = simulate_round(labels, incoming_data=error)
        groups.setdefault(obs, []).append(data)
    for data, obs in zip(records.data, records.observation):
        groups.setdefault(int(obs), []).append(int(data))

    keys, corrections = [], []
    conflicts = 0
    single_failures = 0
    incoming_failures = 0

    for obs in sorted(groups):
        errors = groups[obs]
        # For the certified local templates used in Phase 4, the ideal final
        # boundary plus flags should make all single-fault classes compatible.
        classes = {int(canon[e]) for e in errors}
        if len(classes) > 1:
            conflicts += 1
        # Deterministic representative: lowest stabilizer-coset minimum weight,
        # then integer Pauli label.
        correction = min(errors, key=lambda e: (int(minweights[e]), int(e)))
        keys.append(obs)
        corrections.append(correction)

    decoder = RoundDecoder(np.asarray(keys, dtype=np.int64), np.asarray(corrections, dtype=np.int32),
                           conflicts, 0, 0)
    single_corr = decoder.corrections_for(records.observation)
    single_failures = int(np.count_nonzero(canon[records.data ^ single_corr]))

    incoming_obs, incoming_data = [], []
    for error in _incoming_single_errors():
        data, obs = simulate_round(labels, incoming_data=error)
        incoming_obs.append(obs)
        incoming_data.append(data)
    incoming_corr = decoder.corrections_for(np.asarray(incoming_obs, dtype=np.int64))
    incoming_failures = int(np.count_nonzero(canon[np.asarray(incoming_data, dtype=np.int32) ^ incoming_corr]))
    decoder.single_fault_failures = single_failures
    decoder.incoming_failures = incoming_failures
    return decoder


def logical_class(residual: int) -> str:
    """Classify a zero-syndrome residual Pauli modulo the Steane stabilizer."""
    canon, _, syndromes, _ = code_tables()
    residual = int(residual)
    if int(canon[residual]) == 0:
        return 'I'
    if int(syndromes[residual]) != 0:
        return 'DETECTABLE'
    anti_z = not commutes(residual, LOGICAL_Z)
    anti_x = not commutes(residual, LOGICAL_X)
    if anti_z and anti_x:
        return 'Y'
    if anti_z:
        return 'X'
    if anti_x:
        return 'Z'
    # A zero-syndrome, non-stabilizer element must be logical for [[7,1,3]].
    return 'UNKNOWN'


def failure_mask(data: np.ndarray, observation: np.ndarray, decoder: RoundDecoder) -> np.ndarray:
    canon, _, _, _ = code_tables()
    correction = decoder.corrections_for(observation)
    return canon[np.asarray(data, dtype=np.int32) ^ correction] != 0


def _malignant_pair_categories(labels: tuple[str, ...], records: RoundFaultRecords,
                               decoder: RoundDecoder) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    canon, _, _, _ = code_tables()
    i, j = np.triu_indices(len(records.data), 1)
    keep = records.location[i] != records.location[j]
    i, j = i[keep], j[keep]
    data = records.data[i] ^ records.data[j]
    observation = records.observation[i] ^ records.observation[j]
    correction = decoder.corrections_for(observation)
    malignant = canon[data ^ correction] != 0

    ci = records.category[i[malignant]]
    cj = records.category[j[malignant]]
    lo = np.minimum(ci, cj).astype(np.int32)
    hi = np.maximum(ci, cj).astype(np.int32)
    packed = lo.astype(np.int64) * ROUND_FEATURES + hi
    unique, counts = np.unique(packed, return_counts=True)
    return (unique // ROUND_FEATURES).astype(np.int32), (unique % ROUND_FEATURES).astype(np.int32), \
        counts.astype(np.int32), int(np.count_nonzero(malignant))


@lru_cache(maxsize=96)
def round_risk(labels: tuple[str, ...]) -> RoundRisk:
    labels = validate_round_labels(labels)
    records = fault_records(labels)
    decoder = build_decoder(labels, records)
    if decoder.single_fault_conflicts or decoder.single_fault_failures or decoder.incoming_failures:
        raise ValueError(
            'Round schedule failed single-fault/incoming-error decoder checks: '
            f'conflicts={decoder.single_fault_conflicts}, '
            f'single_failures={decoder.single_fault_failures}, '
            f'incoming_failures={decoder.incoming_failures}'
        )
    pi, pj, pc, malignant = _malignant_pair_categories(labels, records, decoder)
    return RoundRisk(labels, pi, pj, pc, len(records.data), malignant, decoder)


def round_c2(labels: Iterable[str], context: np.ndarray) -> float:
    return round_risk(validate_round_labels(labels)).c2(context)


def verification_summary(labels: Iterable[str]) -> dict:
    labels = validate_round_labels(labels)
    risk = round_risk(labels)
    return {
        'labels': list(labels),
        'checks': list(CHECK_NAMES),
        'fault_count': risk.fault_count,
        'single_fault_conflicts': risk.decoder.single_fault_conflicts,
        'single_fault_logical_failures': risk.decoder.single_fault_failures,
        'single_incoming_error_failures': risk.decoder.incoming_failures,
        'malignant_pair_count': risk.malignant_pair_count,
        'sparse_category_pairs': int(len(risk.pair_count)),
        'ideal_boundaries': True,
        'decoder': 'schedule-specific single-fault lookup with minimum-weight final-syndrome fallback',
    }
