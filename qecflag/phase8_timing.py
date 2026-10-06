"""Phase 8: gate-resolved idle timing and repeated-round decoding.

Phase 7 certified bridge-routed rounds against explicit native CNOT faults, but
idle noise was inserted only once per routed logical interaction.  Phase 8
refines the time model: every preparation block, every native CNOT, and every
measurement block advances a serialized clock.  Persistent data qubits acquire
an explicit X/Y/Z idle-fault location during each interval in which they do not
participate in the active native CNOT.

The repeated-memory diagnostic repeats the same routed extraction round without
an ideal recovery between rounds.  Its primary decoder is deliberately simple
and standard for this small Steane pilot: temporal majority of the six measured
stabilizer bits followed by the Steane minimum-weight syndrome correction.  It
is a baseline decoder, not MWPM and not a scalable surface-code decoder.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import numpy as np

from .physics import code_tables
from .phase3_physics import FLAG_A, FLAG_B
from .phase4_physics import OBS_FINAL_SHIFT
from .phase5_hardware import HardwareContext, DATA_NODES, FLAG_NODES
from .phase6_native import (
    N_PHYSICAL, NativeRoundPlan, NativeFaultDescriptor, NativeFaultRecords,
    _pauli, _cx_frame, _clear_qubit, _measurement_flip,
    _data_frame_to_physical, _physical_to_data, _prep_code, _measurement_basis,
)
from .phase7_routing import build_bridge_plan

A = FLAG_A
B = FLAG_B
DEFAULT_PREP_NS = 100.0
DEFAULT_MEAS_NS = 500.0


@dataclass(frozen=True)
class TimedEvent:
    kind: str  # prep, cx, meas
    check: int
    start_ns: float
    duration_ns: float
    control: int = -1
    target: int = -1
    route: int = -1
    gate: int = -1
    token: int = -1

    @property
    def stop_ns(self) -> float:
        return float(self.start_ns + self.duration_ns)

    @property
    def active_nodes(self) -> tuple[int, ...]:
        if self.kind == 'cx':
            return (self.control, self.target)
        return ()


@dataclass(frozen=True)
class TimedRoundPlan:
    native: NativeRoundPlan
    events: tuple[TimedEvent, ...]
    prep_ns: float
    meas_ns: float
    duration_ns: float
    data_idle_ns: tuple[float, ...]


@dataclass(frozen=True)
class TimedCertificate:
    passed: bool
    c1: float
    conflicts: int
    single_fault_failures: int
    incoming_failures: int
    native_cx: int
    duration_ns: float
    idle_locations: int
    physical_fault_locations: int
    fault_outcomes: int


@dataclass(frozen=True)
class RepeatedFault:
    round_index: int
    descriptor: NativeFaultDescriptor


@dataclass
class RepeatedFaultRecords:
    data: np.ndarray
    syndrome_history: np.ndarray  # packed 6 bits/round
    flag_history: np.ndarray      # packed 12 bits/round (A/B per check)
    location: np.ndarray
    weight: np.ndarray
    faults: tuple[RepeatedFault, ...]


def build_timed_bridge_plan(labels: Iterable[str], hubs: Iterable[int], context: HardwareContext,
                            prep_ns: float = DEFAULT_PREP_NS,
                            meas_ns: float = DEFAULT_MEAS_NS) -> TimedRoundPlan:
    if prep_ns < 0 or meas_ns < 0:
        raise ValueError('prep/meas durations must be nonnegative')
    native = build_bridge_plan(labels, hubs, context)
    events: list[TimedEvent] = []
    idle = np.zeros(7, dtype=np.float64)
    t = 0.0
    data_node_to_q = {node: q for q, node in enumerate(DATA_NODES)}

    def add_idle(duration: float, active_nodes: tuple[int, ...]):
        if duration <= 0:
            return
        active = set(active_nodes)
        for q, node in enumerate(DATA_NODES):
            if node not in active:
                idle[q] += duration

    for cp in native.checks:
        events.append(TimedEvent('prep', cp.check, t, float(prep_ns)))
        add_idle(float(prep_ns), ())
        t += float(prep_ns)
        for ri, route in enumerate(cp.routes):
            for gi, cx in enumerate(route.cxs):
                dur = float(cx.duration_ns)
                events.append(TimedEvent(
                    'cx', cp.check, t, dur, control=cx.control, target=cx.target,
                    route=ri, gate=gi, token=route.token,
                ))
                add_idle(dur, (cx.control, cx.target))
                t += dur
        events.append(TimedEvent('meas', cp.check, t, float(meas_ns)))
        add_idle(float(meas_ns), ())
        t += float(meas_ns)
    return TimedRoundPlan(
        native=native, events=tuple(events), prep_ns=float(prep_ns), meas_ns=float(meas_ns),
        duration_ns=float(t), data_idle_ns=tuple(float(x) for x in idle),
    )


def _logical_gate_weights(context: HardwareContext, check: int, token: int) -> np.ndarray:
    slot = token if 0 <= token < 4 else (4 if token == A else 5)
    start = 3 + 15 * slot
    return np.asarray(context.logical[check, start:start + 15], dtype=np.float64)


def _edge_for_event(plan: TimedRoundPlan, event: TimedEvent) -> int:
    cp = plan.native.checks[event.check]
    return int(cp.routes[event.route].cxs[event.gate].edge_id)


def timed_fault_catalog(plan: TimedRoundPlan, context: HardwareContext):
    """Enumerate one-fault outcomes with per-native-interval data idling.

    Location IDs are unique physical stochastic locations.  A CNOT location has
    15 Pauli outcomes; each data-idle interval has X/Y/Z outcomes.
    """
    desc: list[NativeFaultDescriptor] = []
    weights: list[float] = []
    event_index: list[int] = []
    location = 0
    for ei, event in enumerate(plan.events):
        cp = plan.native.checks[event.check]
        if event.kind == 'prep':
            items = [(cp.hub_node, False, 0)]
            if cp.used_a: items.append((FLAG_NODES[A], True, 1))
            if cp.used_b: items.append((FLAG_NODES[B], True, 2))
            for q, is_flag, logical_index in items:
                desc.append(NativeFaultDescriptor('prep', cp.check, location, route=-1, gate=ei,
                                                  qubit=q, pauli_a=_prep_code(cp.check_type, is_flag)))
                weights.append(float(context.logical[cp.check, logical_index] * context.prep_scale[q]))
                event_index.append(ei); location += 1
        elif event.kind == 'cx':
            base = _logical_gate_weights(context, cp.check, event.token)
            edge_scale = float(context.edge_error[_edge_for_event(plan, event)])
            k = 0
            for pa in range(4):
                for pb in range(4):
                    if pa == pb == 0: continue
                    desc.append(NativeFaultDescriptor('cx', cp.check, location, route=event.route,
                                                      gate=event.gate, qubit=-1,
                                                      pauli_a=pa, pauli_b=pb))
                    weights.append(float(base[k] * edge_scale)); event_index.append(ei); k += 1
            location += 1
        elif event.kind == 'meas':
            items = [(cp.hub_node, False, 93)]
            if cp.used_a: items.append((FLAG_NODES[A], True, 94))
            if cp.used_b: items.append((FLAG_NODES[B], True, 95))
            for q, is_flag, logical_index in items:
                desc.append(NativeFaultDescriptor('meas', cp.check, location, route=-1, gate=ei,
                                                  qubit=q, pauli_a=_prep_code(cp.check_type, is_flag)))
                weights.append(float(context.logical[cp.check, logical_index] * context.meas_scale[q]))
                event_index.append(ei); location += 1
        else:
            raise ValueError(event.kind)

        # Persistent data idles throughout this interval unless physically active.
        active = set(event.active_nodes)
        if event.duration_ns > 0:
            for node in DATA_NODES:
                if node in active:
                    continue
                total = float(context.idle_rate[node] * event.duration_ns)
                for code in (1, 2, 3):
                    desc.append(NativeFaultDescriptor('idle_timed', event.check, location,
                                                      route=event.route, gate=ei,
                                                      qubit=node, pauli_a=code))
                    weights.append(total / 3.0); event_index.append(ei)
                location += 1
    return tuple(desc), np.asarray(weights, dtype=np.float64), np.asarray(event_index, dtype=np.int32)


def _apply_timed_round(plan: TimedRoundPlan, frame: int,
                       fault: NativeFaultDescriptor | None = None,
                       collect_bits: bool = True) -> tuple[int, int, int]:
    """Apply one timed round to a physical Pauli frame.

    Returns physical frame, six syndrome bits, and twelve flag bits.
    """
    synd = 0
    flags = 0
    current_check = -1
    # Event indices are encoded into fault.gate for prep/meas/idle_timed.
    for ei, event in enumerate(plan.events):
        cp = plan.native.checks[event.check]
        if event.kind == 'prep':
            current_check = cp.check
            qs = [cp.hub_node]
            if cp.used_a: qs.append(FLAG_NODES[A])
            if cp.used_b: qs.append(FLAG_NODES[B])
            for q in qs:
                frame = _clear_qubit(frame, q)
                if (fault is not None and fault.kind == 'prep' and fault.check == cp.check
                        and fault.gate == ei and fault.qubit == q):
                    frame ^= _pauli(fault.pauli_a, q)
        elif event.kind == 'cx':
            frame = _cx_frame(frame, event.control, event.target)
            if (fault is not None and fault.kind == 'cx' and fault.check == cp.check
                    and fault.route == event.route and fault.gate == event.gate):
                frame ^= _pauli(fault.pauli_a, event.control)
                frame ^= _pauli(fault.pauli_b, event.target)
        elif event.kind == 'meas':
            if (fault is not None and fault.kind == 'meas' and fault.check == cp.check
                    and fault.gate == ei):
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
            for q in qs: frame = _clear_qubit(frame, q)
        if (fault is not None and fault.kind == 'idle_timed' and fault.gate == ei
                and fault.check == cp.check):
            frame ^= _pauli(fault.pauli_a, fault.qubit)
    return int(frame), int(synd), int(flags)


def simulate_timed_round(plan: TimedRoundPlan, fault: NativeFaultDescriptor | None = None,
                         incoming_data: int = 0, include_final_boundary: bool = True) -> tuple[int, int]:
    frame = _data_frame_to_physical(int(incoming_data))
    frame, synd, flags = _apply_timed_round(plan, frame, fault=fault)
    data = _physical_to_data(frame)
    observation = 0
    # preserve Phase-4/7 observation packing: syndrome,A,B per check
    for ci in range(6):
        observation |= ((synd >> ci) & 1) << (3 * ci)
        observation |= ((flags >> (2 * ci)) & 1) << (3 * ci + 1)
        observation |= ((flags >> (2 * ci + 1)) & 1) << (3 * ci + 2)
    if include_final_boundary:
        _, _, syndromes, _ = code_tables()
        observation |= int(syndromes[data]) << OBS_FINAL_SHIFT
    return int(data), int(observation)


def timed_fault_records(plan: TimedRoundPlan, context: HardwareContext) -> NativeFaultRecords:
    desc, weights, _ = timed_fault_catalog(plan, context)
    sig = [simulate_timed_round(plan, fault=d) for d in desc]
    return NativeFaultRecords(
        data=np.asarray([x[0] for x in sig], dtype=np.int32),
        observation=np.asarray([x[1] for x in sig], dtype=np.int64),
        location=np.asarray([d.location for d in desc], dtype=np.int32),
        weight=weights,
        descriptors=desc,
    )


def _incoming_single_errors() -> list[int]:
    result = [0]
    for q in range(7):
        for code in (1, 2, 3):
            result.append(((code & 1) << q) | (((code >> 1) & 1) << (7 + q)))
    return result


def timed_single_fault_certificate(labels: Iterable[str], hubs: Iterable[int], context: HardwareContext,
                                   prep_ns: float = DEFAULT_PREP_NS,
                                   meas_ns: float = DEFAULT_MEAS_NS) -> TimedCertificate:
    plan = build_timed_bridge_plan(labels, hubs, context, prep_ns, meas_ns)
    records = timed_fault_records(plan, context)
    canon, minweights, _, fallback = code_tables()
    groups: dict[int, list[int]] = {}
    incoming = []
    for err in _incoming_single_errors():
        d, o = simulate_timed_round(plan, incoming_data=err)
        groups.setdefault(o, []).append(d); incoming.append((d, o))
    for d, o in zip(records.data, records.observation):
        groups.setdefault(int(o), []).append(int(d))
    corrections = {}
    conflicts = 0
    for obs, errors in groups.items():
        if len({int(canon[e]) for e in errors}) > 1: conflicts += 1
        corrections[int(obs)] = min(errors, key=lambda e: (int(minweights[e]), int(e)))
    def corr(obs: int) -> int:
        if int(obs) in corrections: return int(corrections[int(obs)])
        return int(fallback[(int(obs) >> OBS_FINAL_SHIFT) & 63])
    single_fail = np.asarray([canon[int(d) ^ corr(int(o))] != 0 for d, o in zip(records.data, records.observation)])
    c1 = float(records.weight[single_fail].sum())
    incoming_fail = sum(int(canon[d ^ corr(o)] != 0) for d, o in incoming)
    idle_locations = len({d.location for d in records.descriptors if d.kind == 'idle_timed'})
    passed = bool(c1 == 0.0 and conflicts == 0 and not np.any(single_fail) and incoming_fail == 0)
    return TimedCertificate(
        passed=passed, c1=c1, conflicts=int(conflicts),
        single_fault_failures=int(np.count_nonzero(single_fail)), incoming_failures=int(incoming_fail),
        native_cx=int(plan.native.native_cx), duration_ns=float(plan.duration_ns),
        idle_locations=int(idle_locations), physical_fault_locations=int(len(np.unique(records.location))),
        fault_outcomes=int(len(records.data)),
    )


def simulate_repeated_signature(plan: TimedRoundPlan, rounds: int,
                                fault: RepeatedFault | None = None,
                                incoming_data: int = 0,
                                include_final_boundary: bool = True) -> tuple[int, int, int]:
    if rounds < 1: raise ValueError('rounds must be >=1')
    frame = _data_frame_to_physical(int(incoming_data))
    sh = 0; fh = 0
    for r in range(rounds):
        desc = fault.descriptor if fault is not None and fault.round_index == r else None
        frame, synd, flags = _apply_timed_round(plan, frame, fault=desc)
        sh |= int(synd) << (6 * r)
        fh |= int(flags) << (12 * r)
    data = int(_physical_to_data(frame))
    if include_final_boundary:
        _, _, syndromes, _ = code_tables()
        sh |= int(syndromes[data]) << (6 * rounds)
    return data, int(sh), int(fh)


def repeated_fault_records(plan: TimedRoundPlan, context: HardwareContext, rounds: int) -> RepeatedFaultRecords:
    desc, weights, _ = timed_fault_catalog(plan, context)
    data=[]; sh=[]; fh=[]; loc=[]; ww=[]; faults=[]
    nloc = int(max((d.location for d in desc), default=-1) + 1)
    for r in range(rounds):
        for d, w in zip(desc, weights):
            rf = RepeatedFault(r, d)
            dd, ss, ff = simulate_repeated_signature(plan, rounds, rf)
            data.append(dd); sh.append(ss); fh.append(ff)
            loc.append(r * nloc + d.location); ww.append(float(w)); faults.append(rf)
    return RepeatedFaultRecords(
        np.asarray(data,dtype=np.int32), np.asarray(sh,dtype=np.int64), np.asarray(fh,dtype=np.int64),
        np.asarray(loc,dtype=np.int32), np.asarray(ww,dtype=np.float64), tuple(faults),
    )


def temporal_majority_syndrome(history: int, rounds: int) -> int:
    out = 0
    threshold = rounds // 2 + 1
    for bit in range(6):
        count = sum((int(history) >> (6*r + bit)) & 1 for r in range(rounds))
        if count >= threshold: out |= 1 << bit
    return int(out)


def standard_steane_history_correction(history: int, rounds: int) -> int:
    """Temporal-majority syndrome followed by Steane minimum-weight correction."""
    _, _, _, fallback = code_tables()
    return int(fallback[temporal_majority_syndrome(history, rounds)])


def _wilson(failures: int, shots: int, z: float=1.959963984540054):
    rate=failures/shots; denom=1+z*z/shots
    center=(rate+z*z/(2*shots))/denom
    radius=z*np.sqrt(rate*(1-rate)/shots+z*z/(4*shots*shots))/denom
    return max(0.0,float(center-radius)), min(1.0,float(center+radius))


def simulate_repeated_finite_p(plan: TimedRoundPlan, context: HardwareContext, rounds: int,
                               p: float, shots: int, seed: int, batch_size: int=5000) -> dict:
    """Monte Carlo by superposing exact single-fault repeated-round signatures."""
    if p < 0 or shots <= 0: raise ValueError('invalid p/shots')
    rec = repeated_fault_records(plan, context, rounds)
    locations = np.unique(rec.location)
    groups = [np.flatnonzero(rec.location == x) for x in locations]
    max_rate = max((float(rec.weight[idx].sum()) for idx in groups), default=0.0)
    if p * max_rate > 1: raise ValueError('p makes a physical-location probability exceed 1')
    canon, _, _, _ = code_tables()
    rng=np.random.default_rng(seed); failures=0
    for start in range(0,shots,batch_size):
        b=min(batch_size,shots-start)
        data=np.zeros(b,dtype=np.int32); hist=np.zeros(b,dtype=np.int64)
        for idx in groups:
            probs=p*rec.weight[idx]; cum=np.cumsum(probs)
            draw=np.searchsorted(cum,rng.random(b),side='right')
            data ^= np.append(rec.data[idx],0)[draw]
            hist ^= np.append(rec.syndrome_history[idx],0)[draw]
        # Number of rounds is small, so vectorized lookup table over history values.
        uniq, inv=np.unique(hist, return_inverse=True)
        corr=np.asarray([standard_steane_history_correction(int(h),rounds) for h in uniq],dtype=np.int32)[inv]
        failures += int(np.count_nonzero(canon[data ^ corr]))
    lo,hi=_wilson(failures,shots)
    return {
        'rounds':int(rounds),'p':float(p),'shots':int(shots),'seed':int(seed),
        'failures':int(failures),'logical_failure_rate':failures/shots,
        'wilson95_low':lo,'wilson95_high':hi,
        'decoder':'temporal-majority six-bit syndrome + Steane minimum-weight correction',
        'native_cx_per_round':int(plan.native.native_cx),'duration_us_per_round':float(plan.duration_ns/1000.0),
        'fault_locations_per_round':int(len(locations)//rounds if rounds else 0),
    }

@dataclass
class RepeatedHistoryDecoder:
    keys: np.ndarray
    corrections: np.ndarray
    rounds: int
    single_fault_conflicts: int
    single_fault_failures: int
    incoming_failures: int

    def correction_for(self, syndrome_history: int, flag_history: int = 0) -> int:
        key = int(syndrome_history) | (int(flag_history) << (6 * (self.rounds + 1)))
        if len(self.keys):
            pos = int(np.searchsorted(self.keys, key))
            if pos < len(self.keys) and int(self.keys[pos]) == key:
                return int(self.corrections[pos])
        # Minimum-weight fallback from the most recent measured syndrome.
        _, _, _, fallback = code_tables()
        last = (int(syndrome_history) >> (6 * self.rounds)) & 63
        return int(fallback[last])


def build_repeated_history_decoder(plan: TimedRoundPlan, context: HardwareContext,
                                   rounds: int, records: RepeatedFaultRecords | None = None) -> RepeatedHistoryDecoder:
    """Small-code minimum-weight fault-history decoder.

    Every modeled single physical fault at every round, plus all single incoming
    data Paulis, is treated as a candidate explanation for the complete syndrome
    and flag history.  For each observed history, the minimum-weight compatible
    data correction is stored.  This is an exact lookup implementation of a
    minimum-weight fault-history decoder for this small pilot; it is not MWPM.
    """
    if rounds < 1: raise ValueError('rounds must be >=1')
    rec = repeated_fault_records(plan, context, rounds) if records is None else records
    canon, minweights, _, _ = code_tables()
    groups: dict[int, list[int]] = {}
    incoming=[]
    for err in _incoming_single_errors():
        d, sh, fh = simulate_repeated_signature(plan, rounds, incoming_data=err)
        key=int(sh) | (int(fh) << (6*(rounds+1))); groups.setdefault(key,[]).append(int(d)); incoming.append((d,sh,fh))
    for d,sh,fh in zip(rec.data,rec.syndrome_history,rec.flag_history):
        key=int(sh) | (int(fh) << (6*(rounds+1))); groups.setdefault(key,[]).append(int(d))
    keys=[]; corrs=[]; conflicts=0
    for key in sorted(groups):
        errors=groups[key]
        if len({int(canon[e]) for e in errors})>1: conflicts += 1
        corr=min(errors,key=lambda e:(int(minweights[e]),int(e)))
        keys.append(key); corrs.append(corr)
    dec=RepeatedHistoryDecoder(np.asarray(keys,dtype=np.int64),np.asarray(corrs,dtype=np.int32),rounds,conflicts,0,0)
    sf=0
    for d,sh,fh in zip(rec.data,rec.syndrome_history,rec.flag_history):
        sf += int(canon[int(d)^dec.correction_for(int(sh),int(fh))] != 0)
    inc=0
    for d,sh,fh in incoming:
        inc += int(canon[int(d)^dec.correction_for(int(sh),int(fh))] != 0)
    dec.single_fault_failures=int(sf); dec.incoming_failures=int(inc)
    return dec


def simulate_repeated_finite_p_history(plan: TimedRoundPlan, context: HardwareContext, rounds: int,
                                       p: float, shots: int, seed: int, batch_size: int=5000) -> dict:
    """Repeated-round Monte Carlo with the minimum-weight fault-history decoder."""
    if p < 0 or shots <= 0: raise ValueError('invalid p/shots')
    rec=repeated_fault_records(plan,context,rounds)
    dec=build_repeated_history_decoder(plan,context,rounds,records=rec)
    locations=np.unique(rec.location); groups=[np.flatnonzero(rec.location==x) for x in locations]
    max_rate=max((float(rec.weight[idx].sum()) for idx in groups),default=0.0)
    if p*max_rate>1: raise ValueError('p makes a physical-location probability exceed 1')
    canon,_,_,_=code_tables(); rng=np.random.default_rng(seed); failures=0
    for start in range(0,shots,batch_size):
        b=min(batch_size,shots-start)
        data=np.zeros(b,dtype=np.int32); sh=np.zeros(b,dtype=np.int64); fh=np.zeros(b,dtype=np.int64)
        for idx in groups:
            probs=p*rec.weight[idx]; cum=np.cumsum(probs); draw=np.searchsorted(cum,rng.random(b),side='right')
            data ^= np.append(rec.data[idx],0)[draw]
            sh ^= np.append(rec.syndrome_history[idx],0)[draw]
            fh ^= np.append(rec.flag_history[idx],0)[draw]
        keys=sh | (fh << (6*(rounds+1))); uniq,inv=np.unique(keys,return_inverse=True)
        corr=np.empty(len(uniq),dtype=np.int32)
        mask=(1<<(6*(rounds+1)))-1
        for i,key in enumerate(uniq):
            s=int(key)&mask; f=int(key)>>(6*(rounds+1)); corr[i]=dec.correction_for(s,f)
        failures += int(np.count_nonzero(canon[data ^ corr[inv]]))
    lo,hi=_wilson(failures,shots)
    return {
        'rounds':int(rounds),'p':float(p),'shots':int(shots),'seed':int(seed),
        'failures':int(failures),'logical_failure_rate':failures/shots,
        'wilson95_low':lo,'wilson95_high':hi,
        'decoder':'minimum-weight fault-history decoder over full syndrome+flag history',
        'decoder_single_fault_conflicts':dec.single_fault_conflicts,
        'decoder_single_fault_failures':dec.single_fault_failures,
        'decoder_incoming_failures':dec.incoming_failures,
        'native_cx_per_round':int(plan.native.native_cx),'duration_us_per_round':float(plan.duration_ns/1000.0),
        'fault_locations_per_round':int(len(locations)//rounds if rounds else 0),
    }
