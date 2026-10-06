"""Phase 10: resource-constrained parallel scheduling of certified bridge circuits.

Phase 7 established a catalog of bridge-routed Steane extraction rounds that are
single-fault certified when executed serially. Phase 8/9 validated gate-resolved
idling and repeated-round decoding. Phase 10 keeps the logical circuit and
physical bridge routes fixed, but allows *operations from different stabilizer
checks* to overlap when they use disjoint physical resources.

The central rule is conservative: parallelism is never assumed fault tolerant.
Every selected parallel schedule is re-simulated in its actual event order and
must again satisfy C1=0, zero single-fault decoder conflicts/failures, and zero
incoming-single-error failures.

This is not a pulse scheduler. Operations are prep blocks, native CNOTs, and
measurement blocks. A physical qubit cannot participate in more than one active
operation at a time. Same-check program order is preserved exactly.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Iterable
import numpy as np

from .physics import code_tables
from .phase3_physics import FLAG_A, FLAG_B
from .phase4_physics import OBS_FINAL_SHIFT, RoundDecoder
from .phase5_hardware import HardwareContext, DATA_NODES, FLAG_NODES
from .phase6_native import (
    NativeRoundPlan, _pauli, _cx_frame, _clear_qubit, _measurement_flip,
    _data_frame_to_physical, _physical_to_data, _prep_code, _measurement_basis,
)
from .phase7_routing import build_bridge_plan
from .phase8_timing import DEFAULT_PREP_NS, DEFAULT_MEAS_NS, _logical_gate_weights

A = FLAG_A
B = FLAG_B


@dataclass(frozen=True)
class ProgramEvent:
    uid: int
    check: int
    seq: int
    kind: str  # prep, cx, meas
    duration_ns: float
    resources: tuple[int, ...]
    control: int = -1
    target: int = -1
    edge_id: int = -1
    route: int = -1
    gate: int = -1
    token: int = -1


@dataclass(frozen=True)
class ScheduledEvent:
    event: ProgramEvent
    start_ns: float

    @property
    def stop_ns(self) -> float:
        return float(self.start_ns + self.event.duration_ns)


@dataclass(frozen=True)
class IdleSlice:
    index: int
    start_ns: float
    stop_ns: float
    inactive_data_nodes: tuple[int, ...]

    @property
    def duration_ns(self) -> float:
        return float(self.stop_ns - self.start_ns)


@dataclass(frozen=True)
class ParallelSchedule:
    native: NativeRoundPlan
    events: tuple[ScheduledEvent, ...]
    idle_slices: tuple[IdleSlice, ...]
    method: str
    priority: tuple[int, ...]
    duration_ns: float
    data_idle_ns: tuple[float, ...]
    max_parallel_cx: int
    total_native_cx: int
    timing_proxy: float


@dataclass(frozen=True)
class ParallelFaultDescriptor:
    kind: str
    location: int
    event_uid: int = -1
    slice_index: int = -1
    qubit: int = -1
    pauli_a: int = 0
    pauli_b: int = 0


@dataclass
class ParallelFaultRecords:
    data: np.ndarray
    observation: np.ndarray
    location: np.ndarray
    weight: np.ndarray
    descriptors: tuple[ParallelFaultDescriptor, ...]


@dataclass(frozen=True)
class ParallelCertificate:
    passed: bool
    ideal_ok: bool
    c1: float
    conflicts: int
    single_fault_failures: int
    incoming_failures: int
    fault_outcomes: int
    physical_fault_locations: int
    duration_ns: float
    total_data_idle_ns: float
    max_parallel_cx: int
    native_cx: int


def _check_resources(cp) -> tuple[int, ...]:
    out = [int(cp.hub_node)]
    if cp.used_a:
        out.append(int(FLAG_NODES[A]))
    if cp.used_b:
        out.append(int(FLAG_NODES[B]))
    return tuple(sorted(set(out)))


def build_programs(labels: Iterable[str], hubs: Iterable[int], context: HardwareContext,
                   prep_ns: float = DEFAULT_PREP_NS,
                   meas_ns: float = DEFAULT_MEAS_NS) -> tuple[NativeRoundPlan, tuple[tuple[ProgramEvent, ...], ...]]:
    native = build_bridge_plan(labels, hubs, context)
    programs: list[tuple[ProgramEvent, ...]] = []
    uid = 0
    for cp in native.checks:
        seq = 0
        evs: list[ProgramEvent] = []
        res = _check_resources(cp)
        evs.append(ProgramEvent(uid, cp.check, seq, 'prep', float(prep_ns), res)); uid += 1; seq += 1
        for ri, route in enumerate(cp.routes):
            for gi, cx in enumerate(route.cxs):
                evs.append(ProgramEvent(
                    uid, cp.check, seq, 'cx', float(cx.duration_ns),
                    tuple(sorted((int(cx.control), int(cx.target)))),
                    control=int(cx.control), target=int(cx.target), edge_id=int(cx.edge_id),
                    route=int(ri), gate=int(gi), token=int(route.token),
                ))
                uid += 1; seq += 1
        evs.append(ProgramEvent(uid, cp.check, seq, 'meas', float(meas_ns), res)); uid += 1
        programs.append(tuple(evs))
    return native, tuple(programs)


def _remaining_duration(programs, check: int, seq: int) -> float:
    return float(sum(e.duration_ns for e in programs[check][seq:]))


def _priority_key(event: ProgramEvent, method: str, context: HardwareContext,
                  programs, check_priority: tuple[int, ...]):
    rank = {c: i for i, c in enumerate(check_priority)}
    if method in ('asap', 'priority', 'ancilla_overlap', 'type_overlap', 'css_block'):
        return (rank[event.check], event.seq, event.uid)
    if method == 'shortest_greedy':
        return (event.duration_ns, rank[event.check], event.seq, event.uid)
    if method == 'critical_greedy':
        rem = _remaining_duration(programs, event.check, event.seq)
        return (-rem, rank[event.check], event.seq, event.uid)
    if method == 'noise_greedy':
        # Favor operations that keep high-idle-rate data qubits active. Gate
        # error itself is schedule independent, so it is only a deterministic
        # tie breaker here.
        active_data = [q for q, node in enumerate(DATA_NODES) if node in event.resources]
        idle_saved = float(sum(context.idle_rate[DATA_NODES[q]] for q in active_data) * event.duration_ns)
        edge = float(context.edge_error[event.edge_id]) if event.edge_id >= 0 else 0.0
        return (-idle_saved, event.duration_ns, edge, rank[event.check], event.seq, event.uid)
    raise ValueError(f'unknown scheduling method {method!r}')


def _schedule_list(labels, hubs, context: HardwareContext, method: str,
                   check_priority: tuple[int, ...] | None = None,
                   prep_ns: float = DEFAULT_PREP_NS,
                   meas_ns: float = DEFAULT_MEAS_NS) -> ParallelSchedule:
    native, programs = build_programs(labels, hubs, context, prep_ns, meas_ns)
    if check_priority is None:
        check_priority = tuple(range(6))
    check_priority = tuple(int(x) for x in check_priority)
    if tuple(sorted(check_priority)) != tuple(range(6)):
        raise ValueError('check_priority must be a permutation of 0..5')

    if method == 'serialized':
        t = 0.0; scheduled = []
        for check in range(6):
            for ev in programs[check]:
                scheduled.append(ScheduledEvent(ev, t)); t += ev.duration_ns
        return _finalize_schedule(native, scheduled, context, method, check_priority)

    ptr = [0] * 6
    ready_at = [0.0] * 6
    running: list[ScheduledEvent] = []
    scheduled: list[ScheduledEvent] = []
    t = 0.0
    total = sum(len(p) for p in programs)
    eps = 1e-9
    while len(scheduled) < total:
        # Operations ending at t release resources before new operations start.
        running = [x for x in running if x.stop_ns > t + eps]
        busy = set()
        def sched_resources(ev):
            res = set(ev.resources)
            if method == 'ancilla_overlap' and ev.kind == 'cx':
                res.add(-1000)  # virtual global native-CX lane
            elif method == 'type_overlap' and ev.kind == 'cx':
                res.add(-1000 if ev.check < 3 else -1001)
            return res
        for x in running:
            busy.update(sched_resources(x.event))

        candidates = []
        css_first_done = all(ptr[c] >= len(programs[c]) for c in range(3))
        for c in range(6):
            if method == 'css_block':
                if not css_first_done and c >= 3:
                    continue
                if css_first_done and c < 3:
                    continue
            if ptr[c] < len(programs[c]) and ready_at[c] <= t + eps:
                candidates.append(programs[c][ptr[c]])
        candidates.sort(key=lambda e: _priority_key(e, method, context, programs, check_priority))

        launched = False
        for ev in candidates:
            evres = sched_resources(ev)
            if any(r in busy for r in evres):
                continue
            se = ScheduledEvent(ev, float(t))
            scheduled.append(se); running.append(se); launched = True
            busy.update(evres)
            ptr[ev.check] += 1
            ready_at[ev.check] = se.stop_ns

        if len(scheduled) >= total:
            break
        if running:
            next_t = min(x.stop_ns for x in running)
        else:
            future = [ready_at[c] for c in range(6) if ptr[c] < len(programs[c])]
            if not future:
                break
            next_t = min(future)
        if next_t <= t + eps:
            if not launched:
                raise RuntimeError('parallel scheduler made no progress')
            # A zero-duration event could land here, but Phase 10 uses positive durations.
            next_t = t + eps
        t = float(next_t)
    return _finalize_schedule(native, scheduled, context, method, check_priority)


def _idle_slices(events: tuple[ScheduledEvent, ...]) -> tuple[IdleSlice, ...]:
    bounds = sorted({0.0, *[float(e.start_ns) for e in events], *[float(e.stop_ns) for e in events]})
    out = []
    for i, (a, b) in enumerate(zip(bounds[:-1], bounds[1:])):
        if b <= a:
            continue
        active = set()
        for se in events:
            if se.event.kind != 'cx':
                continue
            if se.start_ns < b - 1e-9 and se.stop_ns > a + 1e-9:
                active.update(se.event.resources)
        inactive = tuple(int(node) for node in DATA_NODES if node not in active)
        out.append(IdleSlice(len(out), float(a), float(b), inactive))
    return tuple(out)


def _max_parallel_cx(events: tuple[ScheduledEvent, ...]) -> int:
    bounds = sorted({0.0, *[float(e.start_ns) for e in events], *[float(e.stop_ns) for e in events]})
    best = 0
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b <= a:
            continue
        n = sum(
            se.event.kind == 'cx' and se.start_ns < b - 1e-9 and se.stop_ns > a + 1e-9
            for se in events
        )
        best = max(best, int(n))
    return best


def _finalize_schedule(native, scheduled, context, method, priority) -> ParallelSchedule:
    events = tuple(sorted(scheduled, key=lambda x: (x.start_ns, x.stop_ns, x.event.check, x.event.seq, x.event.uid)))
    duration = max((x.stop_ns for x in events), default=0.0)
    slices = _idle_slices(events)
    idle = []
    for node in DATA_NODES:
        idle.append(float(sum(s.duration_ns for s in slices if node in s.inactive_data_nodes)))
    idle_risk = float(sum(context.idle_rate[node] * ns for node, ns in zip(DATA_NODES, idle)))
    # The proxy is dimensionless and used only to rank schedules of the *same*
    # physical circuit. Gate error terms are therefore constants and omitted.
    timing_proxy = idle_risk + 1e-6 * float(duration)
    return ParallelSchedule(
        native=native, events=events, idle_slices=slices, method=str(method), priority=tuple(priority),
        duration_ns=float(duration), data_idle_ns=tuple(idle), max_parallel_cx=_max_parallel_cx(events),
        total_native_cx=int(native.native_cx), timing_proxy=float(timing_proxy),
    )


def schedule_parallel(labels, hubs, context: HardwareContext, method: str,
                      check_priority: tuple[int, ...] | None = None) -> ParallelSchedule:
    return _schedule_list(labels, hubs, context, method, check_priority)


def validate_resource_schedule(schedule: ParallelSchedule) -> bool:
    by_check = {c: [] for c in range(6)}
    for se in schedule.events:
        by_check[se.event.check].append(se)
    for c, seq in by_check.items():
        seq.sort(key=lambda x: x.event.seq)
        if [x.event.seq for x in seq] != list(range(len(seq))):
            return False
        for a, b in zip(seq[:-1], seq[1:]):
            if a.stop_ns > b.start_ns + 1e-9:
                return False
    ev = schedule.events
    for i, a in enumerate(ev):
        for b in ev[i + 1:]:
            overlap = a.start_ns < b.stop_ns - 1e-9 and b.start_ns < a.stop_ns - 1e-9
            if overlap and set(a.event.resources) & set(b.event.resources):
                return False
    return True


def local_priority_search(labels, hubs, context: HardwareContext,
                          start_priority: tuple[int, ...] = tuple(range(6))) -> ParallelSchedule:
    current = tuple(start_priority)
    best = schedule_parallel(labels, hubs, context, 'priority', current)
    improved = True
    while improved:
        improved = False
        candidates = []
        for i in range(6):
            for j in range(i + 1, 6):
                p = list(current); p[i], p[j] = p[j], p[i]
                s = schedule_parallel(labels, hubs, context, 'priority', tuple(p))
                candidates.append((s.timing_proxy, s.duration_ns, tuple(p), s))
        candidate = min(candidates, key=lambda x: (x[0], x[1], x[2]))
        if (candidate[0], candidate[1]) < (best.timing_proxy - 1e-15, best.duration_ns - 1e-9):
            current = candidate[2]; best = candidate[3]; improved = True
        elif candidate[0] < best.timing_proxy - 1e-15:
            current = candidate[2]; best = candidate[3]; improved = True
    return ParallelSchedule(**{**best.__dict__, 'method': 'local_search'})


def beam_priority_search(labels, hubs, context: HardwareContext, width: int = 8) -> list[ParallelSchedule]:
    """Beam search over static check-priority permutations.

    This is intentionally a deterministic Phase-10 baseline, not learned search.
    Partial permutations are completed in natural order for proxy evaluation.
    """
    if width < 1:
        raise ValueError('width must be positive')
    beam = [tuple()]
    universe = tuple(range(6))
    for depth in range(6):
        expanded = []
        for prefix in beam:
            for c in universe:
                if c in prefix:
                    continue
                pfx = prefix + (c,)
                completion = pfx + tuple(x for x in universe if x not in pfx)
                s = schedule_parallel(labels, hubs, context, 'priority', completion)
                expanded.append((s.timing_proxy, s.duration_ns, pfx, completion, s))
        expanded.sort(key=lambda x: (x[0], x[1], x[2]))
        beam = [x[2] for x in expanded[:width]]
    finals = []
    for p in beam:
        s = schedule_parallel(labels, hubs, context, 'priority', p)
        finals.append(ParallelSchedule(**{**s.__dict__, 'method': 'beam_search'}))
    finals.sort(key=lambda s: (s.timing_proxy, s.duration_ns, s.priority))
    return finals


def exhaustive_priority_best(labels, hubs, context: HardwareContext) -> ParallelSchedule:
    best = None
    for p in permutations(range(6)):
        s = schedule_parallel(labels, hubs, context, 'priority', tuple(p))
        key = (s.timing_proxy, s.duration_ns, p)
        if best is None or key < best[0]:
            best = (key, s)
    s = best[1]
    return ParallelSchedule(**{**s.__dict__, 'method': 'priority_exhaustive'})


def _event_by_uid(schedule: ParallelSchedule) -> dict[int, ScheduledEvent]:
    return {se.event.uid: se for se in schedule.events}


def parallel_fault_catalog(schedule: ParallelSchedule, context: HardwareContext):
    desc: list[ParallelFaultDescriptor] = []
    weights: list[float] = []
    location = 0
    cp_by_check = {cp.check: cp for cp in schedule.native.checks}
    for se in schedule.events:
        ev = se.event; cp = cp_by_check[ev.check]
        if ev.kind == 'prep':
            items = [(cp.hub_node, False, 0)]
            if cp.used_a: items.append((FLAG_NODES[A], True, 1))
            if cp.used_b: items.append((FLAG_NODES[B], True, 2))
            for q, is_flag, logical_index in items:
                desc.append(ParallelFaultDescriptor('prep', location, event_uid=ev.uid, qubit=int(q),
                                                   pauli_a=_prep_code(cp.check_type, is_flag)))
                weights.append(float(context.logical[cp.check, logical_index] * context.prep_scale[q])); location += 1
        elif ev.kind == 'cx':
            base = _logical_gate_weights(context, cp.check, ev.token)
            scale = float(context.edge_error[ev.edge_id]); k = 0
            for pa in range(4):
                for pb in range(4):
                    if pa == pb == 0:
                        continue
                    desc.append(ParallelFaultDescriptor('cx', location, event_uid=ev.uid, pauli_a=pa, pauli_b=pb))
                    weights.append(float(base[k] * scale)); k += 1
                
            location += 1
        elif ev.kind == 'meas':
            items = [(cp.hub_node, False, 93)]
            if cp.used_a: items.append((FLAG_NODES[A], True, 94))
            if cp.used_b: items.append((FLAG_NODES[B], True, 95))
            for q, is_flag, logical_index in items:
                desc.append(ParallelFaultDescriptor('meas', location, event_uid=ev.uid, qubit=int(q),
                                                   pauli_a=_prep_code(cp.check_type, is_flag)))
                weights.append(float(context.logical[cp.check, logical_index] * context.meas_scale[q])); location += 1
        else:
            raise ValueError(ev.kind)
    for sl in schedule.idle_slices:
        if sl.duration_ns <= 0:
            continue
        for node in sl.inactive_data_nodes:
            total = float(context.idle_rate[node] * sl.duration_ns)
            for code in (1, 2, 3):
                desc.append(ParallelFaultDescriptor('idle_parallel', location, slice_index=sl.index,
                                                   qubit=int(node), pauli_a=code))
                weights.append(total / 3.0)
            location += 1
    return tuple(desc), np.asarray(weights, dtype=np.float64)


def _apply_parallel_round(schedule: ParallelSchedule, frame: int,
                          fault: ParallelFaultDescriptor | None = None) -> tuple[int, int, int]:
    cp_by_check = {cp.check: cp for cp in schedule.native.checks}
    actions: list[tuple[float, int, str, object]] = []
    # Event effects occur at operation completion. Idle Pauli locations occur at
    # the end of each disjoint timeline slice. Simultaneous disjoint actions
    # commute, and the deterministic tie break makes the simulator reproducible.
    for se in schedule.events:
        actions.append((se.stop_ns, 1, 'event', se))
    for sl in schedule.idle_slices:
        actions.append((sl.stop_ns, 0, 'idle_slice', sl))
    actions.sort(key=lambda x: (x[0], x[1], getattr(x[3], 'index', -1), getattr(getattr(x[3], 'event', None), 'uid', -1)))
    synd = 0; flags = 0
    for _t, _ord, kind, obj in actions:
        if kind == 'idle_slice':
            sl: IdleSlice = obj
            if fault is not None and fault.kind == 'idle_parallel' and fault.slice_index == sl.index:
                frame ^= _pauli(fault.pauli_a, fault.qubit)
            continue
        se: ScheduledEvent = obj; ev = se.event; cp = cp_by_check[ev.check]
        if ev.kind == 'prep':
            qs = [cp.hub_node]
            if cp.used_a: qs.append(FLAG_NODES[A])
            if cp.used_b: qs.append(FLAG_NODES[B])
            for q in qs:
                frame = _clear_qubit(frame, q)
                if fault is not None and fault.kind == 'prep' and fault.event_uid == ev.uid and fault.qubit == q:
                    frame ^= _pauli(fault.pauli_a, q)
        elif ev.kind == 'cx':
            frame = _cx_frame(frame, ev.control, ev.target)
            if fault is not None and fault.kind == 'cx' and fault.event_uid == ev.uid:
                frame ^= _pauli(fault.pauli_a, ev.control)
                frame ^= _pauli(fault.pauli_b, ev.target)
        elif ev.kind == 'meas':
            if fault is not None and fault.kind == 'meas' and fault.event_uid == ev.uid:
                frame ^= _pauli(fault.pauli_a, fault.qubit)
            sb = _measurement_flip(frame, cp.hub_node, _measurement_basis(cp.check_type, False))
            synd |= int(sb) << cp.check
            if cp.used_a:
                fb = _measurement_flip(frame, FLAG_NODES[A], _measurement_basis(cp.check_type, True))
                flags |= int(fb) << (2 * cp.check)
            if cp.used_b:
                fb = _measurement_flip(frame, FLAG_NODES[B], _measurement_basis(cp.check_type, True))
                flags |= int(fb) << (2 * cp.check + 1)
            qs = [cp.hub_node]
            if cp.used_a: qs.append(FLAG_NODES[A])
            if cp.used_b: qs.append(FLAG_NODES[B])
            for q in qs:
                frame = _clear_qubit(frame, q)
        else:
            raise ValueError(ev.kind)
    return int(frame), int(synd), int(flags)


def simulate_parallel_round(schedule: ParallelSchedule, fault: ParallelFaultDescriptor | None = None,
                            incoming_data: int = 0, include_final_boundary: bool = True) -> tuple[int, int]:
    frame = _data_frame_to_physical(int(incoming_data))
    frame, synd, flags = _apply_parallel_round(schedule, frame, fault=fault)
    data = _physical_to_data(frame)
    obs = 0
    for ci in range(6):
        obs |= ((synd >> ci) & 1) << (3 * ci)
        obs |= ((flags >> (2 * ci)) & 1) << (3 * ci + 1)
        obs |= ((flags >> (2 * ci + 1)) & 1) << (3 * ci + 2)
    if include_final_boundary:
        _, _, syndromes, _ = code_tables()
        obs |= int(syndromes[data]) << OBS_FINAL_SHIFT
    return int(data), int(obs)


def parallel_fault_records(schedule: ParallelSchedule, context: HardwareContext) -> ParallelFaultRecords:
    desc, weights = parallel_fault_catalog(schedule, context)
    sig = [simulate_parallel_round(schedule, fault=d) for d in desc]
    return ParallelFaultRecords(
        data=np.asarray([x[0] for x in sig], dtype=np.int32),
        observation=np.asarray([x[1] for x in sig], dtype=np.int64),
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


def build_parallel_decoder(schedule: ParallelSchedule, records: ParallelFaultRecords) -> RoundDecoder:
    canon, minweights, _, _ = code_tables()
    groups: dict[int, list[int]] = {}
    for error in _incoming_single_errors():
        data, obs = simulate_parallel_round(schedule, incoming_data=error)
        groups.setdefault(int(obs), []).append(int(data))
    for data, obs in zip(records.data, records.observation):
        groups.setdefault(int(obs), []).append(int(data))
    keys=[]; corrections=[]; conflicts=0
    for obs in sorted(groups):
        errors=groups[obs]
        if len({int(canon[e]) for e in errors}) > 1:
            conflicts += 1
        correction=min(errors,key=lambda e:(int(minweights[e]),int(e)))
        keys.append(int(obs)); corrections.append(int(correction))
    dec=RoundDecoder(np.asarray(keys,dtype=np.int64),np.asarray(corrections,dtype=np.int32),int(conflicts),0,0)
    corr=dec.corrections_for(records.observation)
    dec.single_fault_failures=int(np.count_nonzero(canon[records.data ^ corr]))
    inc_data=[]; inc_obs=[]
    for error in _incoming_single_errors():
        d,o=simulate_parallel_round(schedule,incoming_data=error); inc_data.append(d); inc_obs.append(o)
    corr=dec.corrections_for(np.asarray(inc_obs,dtype=np.int64))
    dec.incoming_failures=int(np.count_nonzero(canon[np.asarray(inc_data,dtype=np.int32)^corr]))
    return dec


def certify_parallel_schedule(schedule: ParallelSchedule, context: HardwareContext) -> ParallelCertificate:
    if not validate_resource_schedule(schedule):
        raise ValueError('resource-invalid parallel schedule')
    ideal_data, ideal_obs = simulate_parallel_round(schedule)
    extraction_mask = (1 << OBS_FINAL_SHIFT) - 1
    ideal_ok = bool(ideal_data == 0 and (ideal_obs & extraction_mask) == 0)
    records = parallel_fault_records(schedule, context)
    dec = build_parallel_decoder(schedule, records)
    canon, _, _, _ = code_tables()
    corr = dec.corrections_for(records.observation)
    fail = canon[records.data ^ corr] != 0
    c1 = float(records.weight[fail].sum())
    passed = bool(ideal_ok and c1 == 0.0 and dec.single_fault_conflicts == 0
                  and dec.single_fault_failures == 0 and dec.incoming_failures == 0)
    return ParallelCertificate(
        passed=passed, ideal_ok=ideal_ok, c1=c1, conflicts=int(dec.single_fault_conflicts),
        single_fault_failures=int(dec.single_fault_failures), incoming_failures=int(dec.incoming_failures),
        fault_outcomes=int(len(records.data)), physical_fault_locations=int(len(np.unique(records.location))),
        duration_ns=float(schedule.duration_ns), total_data_idle_ns=float(sum(schedule.data_idle_ns)),
        max_parallel_cx=int(schedule.max_parallel_cx), native_cx=int(schedule.total_native_cx),
    )


def summarize_schedule(schedule: ParallelSchedule, context: HardwareContext) -> dict:
    weighted_idle = float(sum(context.idle_rate[node] * ns for node, ns in zip(DATA_NODES, schedule.data_idle_ns)))
    return {
        'method': schedule.method,
        'priority': list(schedule.priority),
        'duration_us': float(schedule.duration_ns / 1000.0),
        'native_cx': int(schedule.total_native_cx),
        'total_data_idle_us': float(sum(schedule.data_idle_ns) / 1000.0),
        'weighted_idle_exposure': weighted_idle,
        'max_parallel_cx': int(schedule.max_parallel_cx),
        'timing_proxy': float(schedule.timing_proxy),
    }
