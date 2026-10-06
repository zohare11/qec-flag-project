"""Independent small dense-vector checks (no binary-Pauli propagation)."""
from __future__ import annotations
import numpy as np
from .physics import FLAG, N, SYN, labels, local_pauli

# Four active data qubits and the two ancillary qubits fit in 64 amplitudes.
INDICES = np.arange(64)


def cx(state: np.ndarray, control: int, target: int) -> np.ndarray:
    permutation = INDICES ^ (((INDICES >> control) & 1) << target)
    return state[permutation]


def pauli(state: np.ndarray, x: int, z: int) -> np.ndarray:
    permutation = INDICES ^ x
    signs = np.array([(-1) ** ((int(i) & z).bit_count()) for i in permutation])
    shape = (64,) + (1,) * (state.ndim - 1)
    return state[permutation] * signs.reshape(shape)


def compact_frame(p: int) -> tuple[int, int]:
    x, z = p & ((1 << N) - 1), p >> N
    def compact(v: int) -> int:
        return (v & 15) | (((v >> SYN) & 1) << 4) | (((v >> FLAG) & 1) << 5)
    return compact(x), compact(z)


def equivalent_up_to_phase(a: np.ndarray, b: np.ndarray, tolerance: float = 1e-11) -> bool:
    a, b = a.ravel(), b.ravel()
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if max(norm_a, norm_b) < tolerance:
        return True
    if min(norm_a, norm_b) < tolerance or abs(norm_a - norm_b) > tolerance:
        return False
    overlap = np.vdot(a, b)
    if abs(overlap) < tolerance:
        return False
    return bool(np.max(np.abs(b - a * overlap / abs(overlap))) < tolerance)


def kraus_operators(schedule: tuple[int, ...]) -> np.ndarray:
    """Return K[syndrome_bit, flag_bit] on all 16 data basis inputs."""
    states = np.zeros((64, 16), dtype=np.complex128)
    for data in range(16):
        states[data, data] = 1 / np.sqrt(2)
        states[data | 32, data] = 1 / np.sqrt(2)
    for control in schedule:
        states = cx(states, 5 if control == FLAG else control, 4)
    # H on the flag immediately before computational-basis readout.
    lo = states[:32].copy()
    hi = states[32:].copy()
    states[:32] = (lo + hi) / np.sqrt(2)
    states[32:] = (lo - hi) / np.sqrt(2)
    result = np.empty((2, 2, 16, 16), dtype=np.complex128)
    for syndrome in range(2):
        for flag in range(2):
            result[syndrome, flag] = states[np.arange(16) | (syndrome << 4) | (flag << 5)]
    return result


def ideal_measurement_valid(schedule: tuple[int, ...]) -> bool:
    actual = kraus_operators(schedule)
    for syndrome in range(2):
        expected = np.diag([int(i.bit_count() % 2 == syndrome) for i in range(16)])
        if not np.allclose(actual[syndrome, 0], expected, atol=1e-12, rtol=0):
            return False
        if not np.allclose(actual[syndrome, 1], 0, atol=1e-12, rtol=0):
            return False
    return True


def crosscheck_records(schedule: tuple[int, ...], records) -> int:
    """Check E_after U = U_suffix E_insert U_prefix up to a global phase.

    Check two independent complex input vectors for every enumerated fault.
    A separate unit test checks CNOT conjugation for all local Pauli operators.
    """
    rng = np.random.default_rng(481)
    state = rng.normal(size=(64, 2)) + 1j * rng.normal(size=(64, 2))
    state /= np.linalg.norm(state, axis=0)
    prefixes = [state]
    for control in schedule:
        prefixes.append(cx(prefixes[-1], 5 if control == FLAG else control, 4))
    for k, (start, injection, final) in enumerate(zip(records.suffix_start, records.injection, records.full)):
        x, z = compact_frame(int(injection))
        direct = pauli(prefixes[int(start)], x, z)
        for control in schedule[int(start):]:
            direct = cx(direct, 5 if control == FLAG else control, 4)
        x, z = compact_frame(int(final))
        predicted = pauli(prefixes[-1], x, z)
        if not equivalent_up_to_phase(direct, predicted):
            raise AssertionError(f'Dense cross-check failed for {labels(schedule)}, fault {k}')
    return len(records.data)
