"""Phase 6: explicit native routed-CNOT fault validation.

Phase 5 converted routing/timing into effective logical fault weights.  Phase 6
constructs the routed native CNOT sequence itself and inserts independent Pauli
fault locations on every native CNOT.  Preparation/readout faults remain the
same representative Pauli model as Phase 4/5.  Data-memory idle faults are
represented explicitly once per routed logical interaction (mapping is restored
between logical interactions), rather than smeared into logical CNOT categories.

The model is still intentionally controlled: one serialized six-check Steane
round, a synthetic 12-node graph, ideal initial/final memory boundaries, and a
schedule-specific lookup decoder.  It is not a device-calibrated or repeated-
round QEC simulation.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable
import numpy as np

from .physics import code_tables
from .phase3_physics import FLAG_A, FLAG_B, schedule_from_label
from .phase4_physics import (
    CHECKS, N_CHECKS, OBS_FINAL_SHIFT, RoundDecoder,
)
from .phase5_hardware import (
    HardwareContext, DATA_NODES, HUB_NODES, FLAG_NODES, EDGE_INDEX,
    route_stats,
)

N_PHYSICAL = 12
A = FLAG_A
B = FLAG_B


def _pauli(code: int, qubit: int, n: int = N_PHYSICAL) -> int:
    """Symplectic Pauli frame; code 0=I, 1=X, 2=Z, 3=Y."""
    return ((code & 1) << qubit) | (((code >> 1) & 1) << (n + qubit))


def _cx_frame(frame: int, control: int, target: int, n: int = N_PHYSICAL) -> int:
    x = frame & ((1 << n) - 1)
    z = frame >> n
    if (x >> control) & 1:
        x ^= 1 << target
    if (z >> target) & 1:
        z ^= 1 << control
    return int(x | (z << n))


def _clear_qubit(frame: int, qubit: int, n: int = N_PHYSICAL) -> int:
    frame &= ~(1 << qubit)
    frame &= ~(1 << (n + qubit))
    return int(frame)


def _measurement_flip(frame: int, qubit: int, basis: str) -> int:
    if basis == 'Z':
        return int((frame >> qubit) & 1)
    if basis == 'X':
        return int((frame >> (N_PHYSICAL + qubit)) & 1)
    raise ValueError('basis must be X or Z')


def _data_frame_to_physical(data: int) -> int:
    frame = 0
    for q, node in enumerate(DATA_NODES):
        x = (data >> q) & 1
        z = (data >> (7 + q)) & 1
        if x:
            frame ^= 1 << node
        if z:
            frame ^= 1 << (N_PHYSICAL + node)
    return int(frame)


def _physical_to_data(frame: int) -> int:
    data = 0
    for q, node in enumerate(DATA_NODES):
        if (frame >> node) & 1:
            data ^= 1 << q
        if (frame >> (N_PHYSICAL + node)) & 1:
            data ^= 1 << (7 + q)
    return int(data)


def _prep_code(check_type: str, is_flag: bool) -> int:
    # Same representatives used by Phase 4: Z check syndrome |0>, flag |+>;
    # X check is the Hadamard dual.
    if check_type == 'Z':
        return 2 if is_flag else 1
    return 1 if is_flag else 2


def _measurement_basis(check_type: str, is_flag: bool) -> str:
    if check_type == 'Z':
        return 'X' if is_flag else 'Z'
    return 'Z' if is_flag else 'X'


def _edge_id(u: int, v: int) -> int:
    a, b = (u, v) if u < v else (v, u)
    return EDGE_INDEX[(a, b)]


@dataclass(frozen=True)
class NativeCX:
    control: int
    target: int
    edge_id: int
    duration_ns: float
    check: int
    token: int
    route_index: int
    gate_index: int


@dataclass(frozen=True)
class NativeRoute:
    token: int
    active_data: int  # logical data index 0..6, or -1 for a flag interaction
    path: tuple[int, ...]
    cxs: tuple[NativeCX, ...]
    duration_ns: float


@dataclass(frozen=True)
class NativeCheckPlan:
    check: int
    check_type: str
    support: tuple[int, ...]
    label: str
    hub: int
    hub_node: int
    used_a: bool
    used_b: bool
    routes: tuple[NativeRoute, ...]


@dataclass(frozen=True)
class NativeRoundPlan:
    labels: tuple[str, ...]
    hubs: tuple[int, ...]
    checks: tuple[NativeCheckPlan, ...]
    native_cx: int
    duration_ns: float


@dataclass(frozen=True)
class NativeFaultDescriptor:
    kind: str  # prep, cx, idle, meas
    check: int
    location: int
    route: int = -1
    gate: int = -1
    qubit: int = -1
    pauli_a: int = 0
    pauli_b: int = 0


@dataclass
class NativeFaultRecords:
    data: np.ndarray
    observation: np.ndarray
    location: np.ndarray
    weight: np.ndarray
    descriptors: tuple[NativeFaultDescriptor, ...]


@dataclass
class NativeRisk:
    plan: NativeRoundPlan
    records: NativeFaultRecords
    decoder: RoundDecoder
    c1: float
    c2: float
    single_fault_failure_count: int
    malignant_pair_count: int

    @property
    def fault_tolerant_single_fault(self) -> bool:
        return bool(
            self.decoder.single_fault_conflicts == 0
            and self.decoder.single_fault_failures == 0
            and self.decoder.incoming_failures == 0
        )

    def small_p(self, p: float) -> float:
        return float(p * self.c1 + p * p * self.c2)


def _expand_route(path: tuple[int, ...], context: HardwareContext,
                  check: int, token: int, route_index: int) -> tuple[NativeCX, ...]:
    """Explicit SWAP-forward / CNOT / SWAP-back native CX sequence."""
    if len(path) < 2:
        raise ValueError('route path must contain distinct endpoints')
    ops: list[tuple[int, int]] = []
    # Move the logical control along the path until adjacent to target.
    for i in range(len(path) - 2):
        u, v = path[i], path[i + 1]
        ops.extend([(u, v), (v, u), (u, v)])
    # Desired logical CNOT in the requested orientation.
    ops.append((path[-2], path[-1]))
    # Restore the mapping.
    for i in reversed(range(len(path) - 2)):
        u, v = path[i], path[i + 1]
        ops.extend([(u, v), (v, u), (u, v)])
    result = []
    for gi, (c, t) in enumerate(ops):
        eid = _edge_id(c, t)
        result.append(NativeCX(
            c, t, eid, float(context.edge_duration[eid]),
            check, token, route_index, gi,
        ))
    return tuple(result)


def build_native_plan(labels: Iterable[str], hubs: Iterable[int],
                      context: HardwareContext) -> NativeRoundPlan:
    labels = tuple(str(x) for x in labels)
    hubs = tuple(int(x) for x in hubs)
    if len(labels) != N_CHECKS or len(hubs) != N_CHECKS:
        raise ValueError('Expected six labels and six hubs')
    if any(h not in (0, 1) for h in hubs):
        raise ValueError('hub choices must be 0 or 1')
    context.validate()
    checks: list[NativeCheckPlan] = []
    total_cx = 0
    total_duration = 0.0
    for ci, ((check_type, support), label, hub) in enumerate(zip(CHECKS, labels, hubs)):
        template = schedule_from_label(label)
        hub_node = HUB_NODES[hub]
        routes: list[NativeRoute] = []
        for ri, token in enumerate(template):
            if 0 <= token < 4:
                endpoint = DATA_NODES[support[token]]
                active_data = support[token]
            elif token == A:
                endpoint = FLAG_NODES[A]
                active_data = -1
            elif token == B:
                endpoint = FLAG_NODES[B]
                active_data = -1
            else:
                raise ValueError(f'unknown token {token}')
            source, target = (hub_node, endpoint) if check_type == 'X' else (endpoint, hub_node)
            stats = route_stats(source, target, context)
            cxs = _expand_route(stats.path, context, ci, token, ri)
            # This equality is an important cross-check against Phase 5.
            if len(cxs) != stats.native_cx:
                raise AssertionError('native route expansion count disagrees with Phase 5 route model')
            duration = float(sum(x.duration_ns for x in cxs))
            routes.append(NativeRoute(token, active_data, stats.path, cxs, duration))
            total_cx += len(cxs)
            total_duration += duration
        checks.append(NativeCheckPlan(
            ci, check_type, tuple(support), label, hub, hub_node,
            A in template, B in template, tuple(routes),
        ))
    return NativeRoundPlan(labels, hubs, tuple(checks), int(total_cx), float(total_duration))


def _logical_gate_weights(context: HardwareContext, check: int, token: int) -> np.ndarray:
    slot = token if 0 <= token < 4 else (4 if token == A else 5)
    start = 3 + 15 * slot
    return np.asarray(context.logical[check, start:start + 15], dtype=np.float64)


def _fault_catalog(plan: NativeRoundPlan, context: HardwareContext) -> tuple[list[NativeFaultDescriptor], list[float]]:
    """Enumerate explicit native fault outcomes and their p-independent weights."""
    descriptors: list[NativeFaultDescriptor] = []
    weights: list[float] = []
    location = 0
    for cp in plan.checks:
        # Ideal prepare/reset of syndrome and used flags; one representative prep fault each.
        prep_items = [(cp.hub_node, False, 0)]
        if cp.used_a:
            prep_items.append((FLAG_NODES[A], True, 1))
        if cp.used_b:
            prep_items.append((FLAG_NODES[B], True, 2))
        for q, is_flag, logical_index in prep_items:
            descriptors.append(NativeFaultDescriptor('prep', cp.check, location, qubit=q,
                                                     pauli_a=_prep_code(cp.check_type, is_flag)))
            weights.append(float(context.logical[cp.check, logical_index] * context.prep_scale[q]))
            location += 1

        for ri, route in enumerate(cp.routes):
            base = _logical_gate_weights(context, cp.check, route.token)
            for gi, cx in enumerate(route.cxs):
                edge_scale = float(context.edge_error[cx.edge_id])
                k = 0
                for pa in range(4):
                    for pb in range(4):
                        if pa == pb == 0:
                            continue
                        descriptors.append(NativeFaultDescriptor(
                            'cx', cp.check, location, route=ri, gate=gi,
                            qubit=-1, pauli_a=pa, pauli_b=pb,
                        ))
                        weights.append(float(base[k] * edge_scale))
                        k += 1
                location += 1

            # Mapping is restored at this boundary.  Persistent data qubits not
            # participating in this logical interaction accumulate an explicit
            # single-qubit idle Pauli location for the route duration.
            for q, node in enumerate(DATA_NODES):
                if q == route.active_data:
                    continue
                total = float(context.idle_rate[node] * route.duration_ns)
                for code in (1, 2, 3):
                    descriptors.append(NativeFaultDescriptor(
                        'idle', cp.check, location, route=ri, qubit=node, pauli_a=code,
                    ))
                    weights.append(total / 3.0)
                location += 1

        meas_items = [(cp.hub_node, False, 93)]
        if cp.used_a:
            meas_items.append((FLAG_NODES[A], True, 94))
        if cp.used_b:
            meas_items.append((FLAG_NODES[B], True, 95))
        for q, is_flag, logical_index in meas_items:
            descriptors.append(NativeFaultDescriptor('meas', cp.check, location, qubit=q,
                                                     pauli_a=_prep_code(cp.check_type, is_flag)))
            weights.append(float(context.logical[cp.check, logical_index] * context.meas_scale[q]))
            location += 1
    return descriptors, weights


def simulate_native(plan: NativeRoundPlan, fault: NativeFaultDescriptor | None = None,
                    incoming_data: int = 0) -> tuple[int, int]:
    frame = _data_frame_to_physical(int(incoming_data))
    observation = 0
    bitpos = 0

    for cp in plan.checks:
        # Fresh preparation overwrites any prior Pauli frame on the ancilla.
        prep_qubits = [cp.hub_node]
        if cp.used_a:
            prep_qubits.append(FLAG_NODES[A])
        if cp.used_b:
            prep_qubits.append(FLAG_NODES[B])
        for q in prep_qubits:
            frame = _clear_qubit(frame, q)
            if fault is not None and fault.kind == 'prep' and fault.check == cp.check and fault.qubit == q:
                frame ^= _pauli(fault.pauli_a, q)

        for ri, route in enumerate(cp.routes):
            for gi, cx in enumerate(route.cxs):
                frame = _cx_frame(frame, cx.control, cx.target)
                if (fault is not None and fault.kind == 'cx' and fault.check == cp.check
                        and fault.route == ri and fault.gate == gi):
                    frame ^= _pauli(fault.pauli_a, cx.control)
                    frame ^= _pauli(fault.pauli_b, cx.target)
            if (fault is not None and fault.kind == 'idle' and fault.check == cp.check
                    and fault.route == ri):
                frame ^= _pauli(fault.pauli_a, fault.qubit)

        # Representative readout fault immediately before ideal measurement.
        meas_qubits = [cp.hub_node]
        if cp.used_a:
            meas_qubits.append(FLAG_NODES[A])
        if cp.used_b:
            meas_qubits.append(FLAG_NODES[B])
        if fault is not None and fault.kind == 'meas' and fault.check == cp.check:
            frame ^= _pauli(fault.pauli_a, fault.qubit)

        observation |= _measurement_flip(frame, cp.hub_node, _measurement_basis(cp.check_type, False)) << bitpos
        bitpos += 1
        observation |= (_measurement_flip(frame, FLAG_NODES[A], _measurement_basis(cp.check_type, True)) if cp.used_a else 0) << bitpos
        bitpos += 1
        observation |= (_measurement_flip(frame, FLAG_NODES[B], _measurement_basis(cp.check_type, True)) if cp.used_b else 0) << bitpos
        bitpos += 1

        for q in meas_qubits:
            frame = _clear_qubit(frame, q)

    data = _physical_to_data(frame)
    _, _, syndromes, _ = code_tables()
    observation |= int(syndromes[data]) << OBS_FINAL_SHIFT
    return int(data), int(observation)


def native_fault_records(plan: NativeRoundPlan, context: HardwareContext) -> NativeFaultRecords:
    desc, weights = _fault_catalog(plan, context)
    signatures = [simulate_native(plan, fault=d) for d in desc]
    return NativeFaultRecords(
        data=np.asarray([x[0] for x in signatures], dtype=np.int32),
        observation=np.asarray([x[1] for x in signatures], dtype=np.int64),
        location=np.asarray([d.location for d in desc], dtype=np.int32),
        weight=np.asarray(weights, dtype=np.float64),
        descriptors=tuple(desc),
    )


def _incoming_single_errors() -> list[int]:
    result = [0]
    for q in range(7):
        for code in (1, 2, 3):
            result.append(((code & 1) << q) | (((code >> 1) & 1) << (7 + q)))
    return result


def build_native_decoder(plan: NativeRoundPlan, records: NativeFaultRecords) -> RoundDecoder:
    canon, minweights, _, _ = code_tables()
    groups: dict[int, list[int]] = {}
    for error in _incoming_single_errors():
        data, obs = simulate_native(plan, incoming_data=error)
        groups.setdefault(obs, []).append(data)
    for data, obs in zip(records.data, records.observation):
        groups.setdefault(int(obs), []).append(int(data))

    keys: list[int] = []
    corrections: list[int] = []
    conflicts = 0
    for obs in sorted(groups):
        errors = groups[obs]
        if len({int(canon[e]) for e in errors}) > 1:
            conflicts += 1
        correction = min(errors, key=lambda e: (int(minweights[e]), int(e)))
        keys.append(int(obs)); corrections.append(int(correction))
    decoder = RoundDecoder(
        np.asarray(keys, dtype=np.int64), np.asarray(corrections, dtype=np.int32),
        int(conflicts), 0, 0,
    )
    corr = decoder.corrections_for(records.observation)
    decoder.single_fault_failures = int(np.count_nonzero(canon[records.data ^ corr]))
    incoming_data, incoming_obs = [], []
    for error in _incoming_single_errors():
        d, o = simulate_native(plan, incoming_data=error)
        incoming_data.append(d); incoming_obs.append(o)
    corr = decoder.corrections_for(np.asarray(incoming_obs, dtype=np.int64))
    decoder.incoming_failures = int(np.count_nonzero(canon[np.asarray(incoming_data, dtype=np.int32) ^ corr]))
    return decoder


def explicit_native_risk(labels: Iterable[str], hubs: Iterable[int], context: HardwareContext,
                         pair_block: int = 96) -> NativeRisk:
    plan = build_native_plan(labels, hubs, context)
    records = native_fault_records(plan, context)
    decoder = build_native_decoder(plan, records)
    canon, _, _, _ = code_tables()
    single_corr = decoder.corrections_for(records.observation)
    single_fail = canon[records.data ^ single_corr] != 0
    c1 = float(records.weight[single_fail].sum())
    single_count = int(np.count_nonzero(single_fail))

    n = len(records.data)
    c2 = 0.0
    malignant_count = 0
    all_j = np.arange(n, dtype=np.int32)[None, :]
    data_all = records.data[None, :]
    obs_all = records.observation[None, :]
    loc_all = records.location[None, :]
    weight_all = records.weight[None, :]
    for start in range(0, n, pair_block):
        stop = min(n, start + pair_block)
        ii = np.arange(start, stop, dtype=np.int32)[:, None]
        valid = (all_j > ii) & (loc_all != records.location[start:stop, None])
        if not np.any(valid):
            continue
        data = records.data[start:stop, None] ^ data_all
        obs = records.observation[start:stop, None] ^ obs_all
        corr = decoder.corrections_for(obs)
        fail = (canon[data ^ corr] != 0) & valid
        malignant_count += int(np.count_nonzero(fail))
        if np.any(fail):
            prod = records.weight[start:stop, None] * weight_all
            c2 += float(prod[fail].sum())
    return NativeRisk(plan, records, decoder, c1, c2, single_count, malignant_count)


def validate_p(risk: NativeRisk, p: float) -> None:
    if p < 0:
        raise ValueError('p must be nonnegative')
    if len(risk.records.location) == 0:
        return
    max_rate = 0.0
    for loc in np.unique(risk.records.location):
        max_rate = max(max_rate, float(risk.records.weight[risk.records.location == loc].sum()))
    if p * max_rate > 1:
        raise ValueError('p makes at least one native physical-location fault probability exceed 1')


def _wilson(failures: int, shots: int, z: float = 1.959963984540054) -> tuple[float, float]:
    rate = failures / shots
    denom = 1 + z * z / shots
    center = (rate + z * z / (2 * shots)) / denom
    radius = z * np.sqrt(rate * (1 - rate) / shots + z * z / (4 * shots * shots)) / denom
    return max(0.0, float(center - radius)), min(1.0, float(center + radius))


def simulate_native_finite_p(risk: NativeRisk, p: float, shots: int, seed: int,
                             batch_size: int = 10000) -> dict:
    validate_p(risk, p)
    records = risk.records
    decoder = risk.decoder
    canon, _, _, _ = code_tables()
    locations = np.unique(records.location)
    groups = [np.flatnonzero(records.location == loc) for loc in locations]
    rng = np.random.default_rng(seed)
    failures = 0
    for start in range(0, shots, batch_size):
        batch = min(batch_size, shots - start)
        data = np.zeros(batch, dtype=np.int32)
        obs = np.zeros(batch, dtype=np.int64)
        for idx in groups:
            probs = p * records.weight[idx]
            cumulative = np.cumsum(probs)
            draw = np.searchsorted(cumulative, rng.random(batch), side='right')
            data ^= np.append(records.data[idx], 0)[draw]
            obs ^= np.append(records.observation[idx], 0)[draw]
        corr = decoder.corrections_for(obs)
        failures += int(np.count_nonzero(canon[data ^ corr]))
    lo, hi = _wilson(failures, shots)
    return {
        'p': float(p), 'shots': int(shots), 'seed': int(seed), 'failures': int(failures),
        'logical_failure_rate': failures / shots,
        'wilson95_low': lo, 'wilson95_high': hi,
        'native_cx': risk.plan.native_cx, 'duration_ns': risk.plan.duration_ns,
        'c1': risk.c1, 'c2': risk.c2,
        'single_fault_conflicts': risk.decoder.single_fault_conflicts,
        'single_fault_failures': risk.decoder.single_fault_failures,
        'incoming_failures': risk.decoder.incoming_failures,
        'scope': 'explicit routed-native-CX Pauli faults; route-boundary data-idle Pauli locations; one serialized Steane round; ideal memory boundaries',
    }
