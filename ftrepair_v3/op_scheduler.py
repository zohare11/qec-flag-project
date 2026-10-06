"""Operation-level scheduling and counterexample-guided repair for FT repair v3.

V2 could only forbid an entire pair of stabilizer checks from overlapping.  V3
uses precedence atoms between *specific physical operations*.  A constraint
``(A -> B)`` means operation A must complete before operation B may start.  Same-
check program order and physical resource exclusion are always enforced.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from collections import defaultdict
from typing import Iterable
import numpy as np

from qecflag.phase3_physics import FLAG_A, FLAG_B
from qecflag.phase5_hardware import HardwareContext, FLAG_NODES
from qecflag.phase10_scheduler import (
    ProgramEvent, ScheduledEvent, ParallelSchedule, _finalize_schedule, _priority_key,
    validate_resource_schedule,
)
from qecflag.phase8_timing import DEFAULT_PREP_NS, DEFAULT_MEAS_NS
from ftrepair.schedule_repair import _evaluate_schedule

from .model import RoutingState, build_plan, context_fingerprint
from .cache import GenericVerifierCache
from .hittingset_bb import hybrid_hitting_set

A = FLAG_A
B = FLAG_B
OpKey = tuple[int, int]  # (check, sequence index)
OpAtom = tuple[int, int, int, int]  # before_check,before_seq,after_check,after_seq


def _check_resources(cp) -> tuple[int, ...]:
    out = [int(cp.hub_node)]
    if cp.used_a: out.append(int(FLAG_NODES[A]))
    if cp.used_b: out.append(int(FLAG_NODES[B]))
    return tuple(sorted(set(out)))


def build_programs_from_plan(plan, context: HardwareContext,
                             prep_ns: float = DEFAULT_PREP_NS,
                             meas_ns: float = DEFAULT_MEAS_NS):
    programs = []
    uid = 0
    for cp in plan.checks:
        seq = 0; evs = []; res = _check_resources(cp)
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
    return tuple(programs)


def _event_map(programs):
    return {(e.check, e.seq): e for p in programs for e in p}


def _norm_atom(atom: Iterable[int]) -> OpAtom:
    a = tuple(int(x) for x in atom)
    if len(a) != 4:
        raise ValueError('operation precedence atom must have four integers')
    if (a[0],a[1]) == (a[2],a[3]):
        raise ValueError('self precedence is invalid')
    return a


def _validate_precedence_dag(programs, constraints: Iterable[OpAtom]) -> tuple[OpAtom, ...]:
    emap = _event_map(programs)
    cons = tuple(sorted(set(_norm_atom(x) for x in constraints)))
    nodes = set(emap)
    graph = {n: set() for n in nodes}; indeg = {n: 0 for n in nodes}
    # Native program order is immutable.
    for p in programs:
        for a,b in zip(p[:-1],p[1:]):
            u=(a.check,a.seq);v=(b.check,b.seq)
            if v not in graph[u]: graph[u].add(v);indeg[v]+=1
    for bc,bs,ac,as_ in cons:
        u=(bc,bs);v=(ac,as_)
        if u not in nodes or v not in nodes:
            raise ValueError(f'precedence references missing operation {u}->{v}')
        if v not in graph[u]: graph[u].add(v);indeg[v]+=1
    ready=sorted([n for n,d in indeg.items() if d==0]);seen=0
    while ready:
        u=ready.pop(0);seen+=1
        for v in sorted(graph[u]):
            indeg[v]-=1
            if indeg[v]==0:
                ready.append(v);ready.sort()
    if seen != len(nodes):
        raise ValueError('operation precedence constraints create a cycle')
    return cons


def schedule_with_operation_precedence(state: RoutingState, context: HardwareContext,
                                       method: str = 'shortest_greedy',
                                       constraints: Iterable[OpAtom] = (),
                                       check_priority: tuple[int,...] | None = None) -> ParallelSchedule:
    plan = build_plan(state, context)
    programs = build_programs_from_plan(plan, context)
    cons = _validate_precedence_dag(programs, constraints)
    if check_priority is None: check_priority = tuple(range(6))
    priority = tuple(map(int,check_priority))
    if tuple(sorted(priority)) != tuple(range(6)):
        raise ValueError('check_priority must be a permutation of 0..5')
    preds = defaultdict(set)
    for bc,bs,ac,as_ in cons:
        preds[(ac,as_)].add((bc,bs))

    ptr=[0]*6; ready_at=[0.0]*6; running=[]; scheduled=[]; done=set(); t=0.0
    total=sum(len(p) for p in programs);eps=1e-9
    while len(scheduled) < total:
        still=[]
        for se in running:
            if se.stop_ns <= t + eps:
                done.add((se.event.check,se.event.seq))
            else:
                still.append(se)
        running=still
        busy=set()
        for se in running: busy.update(se.event.resources)

        candidates=[]
        for c in range(6):
            if ptr[c] >= len(programs[c]) or ready_at[c] > t + eps: continue
            ev=programs[c][ptr[c]]; key=(ev.check,ev.seq)
            if not preds[key].issubset(done): continue
            candidates.append(ev)
        candidates.sort(key=lambda e:_priority_key(e,method,context,programs,priority))
        launched=False
        for ev in candidates:
            if any(r in busy for r in ev.resources): continue
            se=ScheduledEvent(ev,float(t));scheduled.append(se);running.append(se);launched=True
            busy.update(ev.resources);ptr[ev.check]+=1;ready_at[ev.check]=se.stop_ns
        if len(scheduled)>=total: break
        times=[se.stop_ns for se in running if se.stop_ns>t+eps]
        # A check may be blocked by a predecessor that has not even launched. If
        # nothing is running this indicates an impossible/cyclic dependency that
        # should already have been rejected by DAG validation.
        if not times:
            if not launched:
                raise RuntimeError('operation-level scheduler stalled')
            times=[ready_at[c] for c in range(6) if ptr[c]<len(programs[c]) and ready_at[c]>t+eps]
        if not times:
            raise RuntimeError('operation-level scheduler made no progress')
        t=float(min(times))
    sched=_finalize_schedule(plan,scheduled,context,f'op_repair_{method}',priority)
    if not validate_resource_schedule(sched):
        raise RuntimeError('operation-level scheduler produced a resource-invalid schedule')
    return sched


def operation_schedule_signature(schedule: ParallelSchedule) -> tuple:
    return tuple((e.event.check,e.event.seq,e.event.kind,round(e.start_ns,9),round(e.stop_ns,9),
                  e.event.control,e.event.target,e.event.route,e.event.gate) for e in schedule.events)


def evaluate_schedule_cached(schedule: ParallelSchedule, context: HardwareContext,
                             cache: GenericVerifierCache | None = None):
    if cache is None:
        return _evaluate_schedule(schedule, context)
    key=(context_fingerprint(context), operation_schedule_signature(schedule))
    ok,val=cache.get(key)
    if ok: return val
    return cache.put(key,_evaluate_schedule(schedule,context))


def _overlap(a: ScheduledEvent,b: ScheduledEvent)->bool:
    return a.start_ns < b.stop_ns - 1e-9 and b.start_ns < a.stop_ns - 1e-9


def _atom(before: ScheduledEvent, after: ScheduledEvent) -> OpAtom:
    return (int(before.event.check),int(before.event.seq),int(after.event.check),int(after.event.seq))


def _candidate_orientations(a: ScheduledEvent,b: ScheduledEvent, rank: dict[int,int]) -> tuple[OpAtom, ...]:
    # Keep explicit precedence consistent with one global check order.  This
    # guarantees acyclicity while still constraining only the implicated native
    # operations rather than serializing whole check streams.
    if rank[int(a.event.check)] <= rank[int(b.event.check)]:
        return (_atom(a,b),)
    return (_atom(b,a),)


def _stream_boundary_atom(a_check:int,b_check:int,rank:dict[int,int],cx_by_check:dict[int,list[ScheduledEvent]]) -> OpAtom | None:
    if not cx_by_check.get(a_check) or not cx_by_check.get(b_check):
        return None
    if rank[a_check] <= rank[b_check]:
        before=max(cx_by_check[a_check],key=lambda x:x.event.seq)
        after=min(cx_by_check[b_check],key=lambda x:x.event.seq)
    else:
        before=max(cx_by_check[b_check],key=lambda x:x.event.seq)
        after=min(cx_by_check[a_check],key=lambda x:x.event.seq)
    return _atom(before,after)


def operation_witness_clauses(schedule: ParallelSchedule, records, fail_mask,
                              max_atoms_per_witness: int = 16):
    """Translate exact physical failures into operation-level repair clauses.

    Directly overlapping CXs are preferred.  If a failure is caused by an
    interleaving rather than simultaneous gates, V3 also considers the nearest
    cross-check CX operations around the faulty operation's completion time.
    """
    by_uid={se.event.uid:se for se in schedule.events}
    rank={c:i for i,c in enumerate(schedule.priority)}
    by_slice={sl.index:sl for sl in schedule.idle_slices}
    cx=[se for se in schedule.events if se.event.kind=='cx']
    cx_by_check={c:sorted([se for se in cx if se.event.check==c],key=lambda x:x.event.seq) for c in range(6)}
    rows=[];clauses=[]
    for idx in np.flatnonzero(fail_mask):
        desc=records.descriptors[int(idx)]; cand=[]; origin=None; window=None
        if getattr(desc,'event_uid',-1)>=0 and desc.event_uid in by_uid:
            base=by_uid[desc.event_uid];origin=base;window=(base.start_ns,base.stop_ns)
            # Exact simultaneous interactions first.
            for other in cx:
                if other.event.check==base.event.check: continue
                if _overlap(base,other):
                    cand.extend(_candidate_orientations(base,other,rank))
                    sa=_stream_boundary_atom(int(base.event.check),int(other.event.check),rank,cx_by_check)
                    if sa is not None:cand.append(sa)
            # Interleaving fallback: nearest other-check CXs around the faulty
            # operation.  These atoms can move only the local physical boundary,
            # unlike v2's whole-check precedence.
            if not cand:
                others=[o for o in cx if o.event.check!=base.event.check]
                others.sort(key=lambda o:(abs(o.start_ns-base.start_ns),abs(o.stop_ns-base.stop_ns),o.event.uid))
                for other in others[:4]:
                    cand.extend(_candidate_orientations(base,other,rank))
                    sa=_stream_boundary_atom(int(base.event.check),int(other.event.check),rank,cx_by_check)
                    if sa is not None:cand.append(sa)
        elif getattr(desc,'slice_index',-1)>=0 and desc.slice_index in by_slice:
            sl=by_slice[desc.slice_index];window=(sl.start_ns,sl.stop_ns)
            active=[se for se in cx if se.start_ns<sl.stop_ns-1e-9 and se.stop_ns>sl.start_ns+1e-9]
            for i,a in enumerate(active):
                for b in active[i+1:]:
                    if a.event.check!=b.event.check:
                        cand.extend(_candidate_orientations(a,b,rank))
                        sa=_stream_boundary_atom(int(a.event.check),int(b.event.check),rank,cx_by_check)
                        if sa is not None:cand.append(sa)
        # Deduplicate and discard constraints already satisfied by the current
        # timeline; such atoms cannot alter this witness.
        emap={(se.event.check,se.event.seq):se for se in schedule.events}
        useful=[];seen=set()
        for at in cand:
            if at in seen: continue
            seen.add(at)
            before=emap[(at[0],at[1])];after=emap[(at[2],at[3])]
            if before.stop_ns <= after.start_ns + 1e-9:
                continue
            useful.append(at)
        useful=useful[:max(1,int(max_atoms_per_witness))]
        if useful: clauses.append(frozenset(useful))
        rows.append({'fault_index':int(idx),'kind':str(getattr(desc,'kind','unknown')),
                     'origin_operation':[origin.event.check,origin.event.seq] if origin else None,
                     'window':list(window) if window else None,
                     'candidate_atoms':[list(x) for x in useful],
                     'weight':float(records.weight[int(idx)])})
    return clauses,rows


def atom_penalties(schedule: ParallelSchedule, atoms: Iterable[OpAtom]) -> dict[OpAtom,float]:
    emap={(se.event.check,se.event.seq):se for se in schedule.events}
    out={}
    for a in atoms:
        b=emap[(a[0],a[1])];c=emap[(a[2],a[3])]
        delay=max(0.0,b.stop_ns-c.start_ns)
        # Prefer a precedence that requires little movement and preserves more
        # overlap.  This is synthesis ranking only, never a safety criterion.
        out[a]=float(delay/max(schedule.duration_ns,1e-12)+1e-9)
    return out


@dataclass
class OperationScheduleRepairResult:
    success: bool
    constraints: tuple[OpAtom,...]
    verifier_calls: int
    cache_hits: int
    iterations: int
    initial_c1: float
    final_c1: float
    initial_failures: int
    final_failures: int
    initial_duration_ns: float
    final_duration_ns: float
    initial_max_parallel_cx: int
    final_max_parallel_cx: int
    clauses_seen: int
    witness_rows_seen: int
    speedup_vs_serial_percent: float | None
    trace: list[dict]
    final_schedule: ParallelSchedule | None = None

    def to_dict(self,include_schedule:bool=False):
        d=asdict(self)
        if not include_schedule:d.pop('final_schedule',None)
        return d


def _serial_schedule(state:RoutingState,context:HardwareContext):
    # A global chain over the same physical plan reproduces serial check order.
    plan=build_plan(state,context);programs=build_programs_from_plan(plan,context)
    cons=[]
    for c in range(5):
        cons.append((c,programs[c][-1].seq,c+1,programs[c+1][0].seq))
    return schedule_with_operation_precedence(state,context,'asap',cons)


def minimize_operation_constraints(state:RoutingState,context:HardwareContext,method:str,
                                   constraints:Iterable[OpAtom],cache:GenericVerifierCache,
                                   budget:int=24):
    """Chunk-first exact deletion minimization (ddmin-style)."""
    cons=list(sorted(set(constraints)));calls0=cache.stats.misses
    current=schedule_with_operation_precedence(state,context,method,cons)
    _r,_d,_f,cert=evaluate_schedule_cached(current,context,cache)
    if not cert.passed:return tuple(cons),current,cert,cache.stats.misses-calls0
    gran=2
    while len(cons)>=2 and cache.stats.misses-calls0<int(budget):
        n=len(cons);chunk=max(1,(n+gran-1)//gran);removed=False
        for i in range(0,n,chunk):
            if cache.stats.misses-calls0>=int(budget):break
            trial=cons[:i]+cons[i+chunk:]
            try:s=schedule_with_operation_precedence(state,context,method,trial)
            except (ValueError,RuntimeError):continue
            _r,_d,_f,c=evaluate_schedule_cached(s,context,cache)
            if c.passed:
                cons=trial;current=s;cert=c;gran=max(2,gran-1);removed=True;break
        if not removed:
            if gran>=len(cons):break
            gran=min(len(cons),gran*2)
    # Final single deletion pass.
    i=0
    while i<len(cons) and cache.stats.misses-calls0<int(budget):
        trial=cons[:i]+cons[i+1:]
        try:s=schedule_with_operation_precedence(state,context,method,trial)
        except (ValueError,RuntimeError):i+=1;continue
        _r,_d,_f,c=evaluate_schedule_cached(s,context,cache)
        if c.passed:
            cons=trial;current=s;cert=c
        else:i+=1
    return tuple(sorted(cons)),current,cert,cache.stats.misses-calls0


def repair_operation_schedule(state:RoutingState,context:HardwareContext,method:str='shortest_greedy',
                              max_constraints:int=32,max_verifier_calls:int=32,
                              max_atoms_per_witness:int=16,
                              cache:GenericVerifierCache|None=None,
                              minimize:bool=True)->OperationScheduleRepairResult:
    cache=GenericVerifierCache() if cache is None else cache
    start_calls=cache.stats.misses;start_hits=cache.stats.hits
    initial=schedule_with_operation_precedence(state,context,method,())
    records,_dec,fail,cert=evaluate_schedule_cached(initial,context,cache)
    initial_fail=int(np.count_nonzero(fail));trace=[{'iteration':0,'constraints':0,'c1':float(cert.c1),
        'failures':initial_fail,'duration_ns':float(initial.duration_ns),'max_parallel_cx':int(initial.max_parallel_cx),'passed':bool(cert.passed)}]
    serial=_serial_schedule(state,context)
    if cert.passed:
        speed=(1-initial.duration_ns/serial.duration_ns)*100
        return OperationScheduleRepairResult(True,tuple(),cache.stats.misses-start_calls,cache.stats.hits-start_hits,0,
            float(cert.c1),float(cert.c1),initial_fail,initial_fail,float(initial.duration_ns),float(initial.duration_ns),
            int(initial.max_parallel_cx),int(initial.max_parallel_cx),0,0,float(speed),trace,initial)
    constraints=tuple();clauses=[];witness_rows_seen=0;current=initial;current_records=records;current_fail=fail;current_cert=cert
    for iteration in range(1,int(max_verifier_calls)+1):
        new,row=operation_witness_clauses(current,current_records,current_fail,max_atoms_per_witness)
        witness_rows_seen+=len(row)
        residual=[]
        fixed=set(constraints)
        for c in new:
            rem=frozenset(a for a in c if a not in fixed)
            if rem:residual.append(rem)
        clauses.extend(residual)
        # Keep unique/subsumption-reduced clauses through v2 utility.
        from ftrepair_v2.hittingset import normalize_clauses
        clauses=list(normalize_clauses(clauses))
        if not clauses:break
        atoms=set().union(*clauses);weights=atom_penalties(current,atoms)
        sol=hybrid_hitting_set(clauses,weights=weights,max_size=int(max_constraints))
        if sol is None:break
        constraints=tuple(sorted(sol))
        try:current=schedule_with_operation_precedence(state,context,method,constraints)
        except (ValueError,RuntimeError):
            # Block one orientation from the latest solution by forcing a residual
            # clause of its alternatives on the next iteration.
            if constraints:
                clauses.append(frozenset(a for a in atoms if a not in constraints))
            continue
        current_records,_dec,current_fail,current_cert=evaluate_schedule_cached(current,context,cache)
        nf=int(np.count_nonzero(current_fail))
        trace.append({'iteration':iteration,'constraints':len(constraints),'constraint_atoms':[list(x) for x in constraints],
                      'c1':float(current_cert.c1),'failures':nf,'duration_ns':float(current.duration_ns),
                      'max_parallel_cx':int(current.max_parallel_cx),'passed':bool(current_cert.passed),'clauses':len(clauses)})
        if current_cert.passed:
            if minimize and cache.stats.misses-start_calls<int(max_verifier_calls):
                cons,s,c,extra=minimize_operation_constraints(state,context,method,constraints,cache,
                    budget=max(1,int(max_verifier_calls)-(cache.stats.misses-start_calls)))
                constraints,current,current_cert=cons,s,c
                current_records,_dec,current_fail,_=evaluate_schedule_cached(current,context,cache)
                trace.append({'strategy':'operation_ddmin','constraints':len(constraints),'extra_exact_calls':extra})
            speed=(1-current.duration_ns/serial.duration_ns)*100
            return OperationScheduleRepairResult(True,constraints,cache.stats.misses-start_calls,cache.stats.hits-start_hits,iteration,
                float(cert.c1),float(current_cert.c1),initial_fail,int(np.count_nonzero(current_fail)),float(initial.duration_ns),
                float(current.duration_ns),int(initial.max_parallel_cx),int(current.max_parallel_cx),len(clauses),witness_rows_seen,float(speed),trace,current)
        if cache.stats.misses-start_calls>=int(max_verifier_calls):break
    speed=(1-current.duration_ns/serial.duration_ns)*100 if current else None
    return OperationScheduleRepairResult(False,constraints,cache.stats.misses-start_calls,cache.stats.hits-start_hits,max(0,len(trace)-1),
        float(cert.c1),float(current_cert.c1),initial_fail,int(np.count_nonzero(current_fail)),float(initial.duration_ns),
        float(current.duration_ns),int(initial.max_parallel_cx),int(current.max_parallel_cx),len(clauses),witness_rows_seen,
        float(speed) if speed is not None else None,trace,current)


def _all_stream_boundary_atoms(state:RoutingState,context:HardwareContext,priority:tuple[int,...]|None=None):
    priority=tuple(range(6)) if priority is None else tuple(priority)
    rank={c:i for i,c in enumerate(priority)}
    plan=build_plan(state,context);programs=build_programs_from_plan(plan,context)
    cx_by={c:[e for e in programs[c] if e.kind=='cx'] for c in range(6)}
    atoms=[]
    for a in range(6):
        for b in range(a+1,6):
            if rank[a]<=rank[b]:
                before=max(cx_by[a],key=lambda e:e.seq);after=min(cx_by[b],key=lambda e:e.seq)
            else:
                before=max(cx_by[b],key=lambda e:e.seq);after=min(cx_by[a],key=lambda e:e.seq)
            atoms.append((before.check,before.seq,after.check,after.seq))
    return tuple(sorted(atoms))


def _full_serial_atoms(state:RoutingState,context:HardwareContext,priority:tuple[int,...]|None=None):
    priority=tuple(range(6)) if priority is None else tuple(priority)
    plan=build_plan(state,context);programs=build_programs_from_plan(plan,context)
    out=[]
    for a,b in zip(priority[:-1],priority[1:]):
        out.append((a,programs[a][-1].seq,b,programs[b][0].seq))
    return tuple(out)


def _pair_of_atom(a:OpAtom):
    return tuple(sorted((int(a[0]),int(a[2]))))


def repair_operation_schedule_portfolio(state:RoutingState,context:HardwareContext,
                                        method:str='shortest_greedy',
                                        check_priority:tuple[int,...]|None=None,
                                        max_constraints:int=40,max_verifier_calls:int=40,
                                        pure_fraction:float=0.25,
                                        cache:GenericVerifierCache|None=None)->OperationScheduleRepairResult:
    """Robust V3 schedule portfolio with operation-level relaxation.

    1. Try pure operation-level CEGIS.
    2. If needed, start from a conservative set of stream-boundary precedence
       atoms that serializes CX streams while still allowing prep/meas overlap.
    3. Exact-ddmin that safe seed.
    4. Replace coarse stream boundaries with witness-local operation precedences
       whenever exact verification proves the narrower repair is safe.

    Thus V3 is never less safe than the conservative fallback, but it can retain
    more parallelism than whole-check pair constraints.
    """
    cache=GenericVerifierCache() if cache is None else cache
    start_calls=cache.stats.misses;start_hits=cache.stats.hits
    priority=tuple(range(6)) if check_priority is None else tuple(check_priority)
    pure_budget=max(3,min(int(max_verifier_calls)-1,int(round(max_verifier_calls*float(pure_fraction)))))
    pure=repair_operation_schedule(state,context,method,max_constraints=max_constraints,
        max_verifier_calls=pure_budget,cache=cache,minimize=True)
    candidates=[]
    if pure.success and pure.final_schedule is not None:
        candidates.append(pure)
    remaining=max(0,int(max_verifier_calls)-(cache.stats.misses-start_calls))
    if remaining<=0:
        pure.verifier_calls=cache.stats.misses-start_calls;pure.cache_hits=cache.stats.hits-start_hits
        return pure

    # Conservative safe seed: all check-pair CX stream boundaries.
    seed_cons=_all_stream_boundary_atoms(state,context,priority)
    try:
        seed_sched=schedule_with_operation_precedence(state,context,method,seed_cons,priority)
        rec,dec,fail,seed_cert=evaluate_schedule_cached(seed_sched,context,cache)
    except Exception:
        seed_cert=None
    if seed_cert is None or not seed_cert.passed:
        # Absolute fallback is the known serial order.  This should pass whenever
        # the routed state itself is single-fault certified.
        seed_cons=_full_serial_atoms(state,context,priority)
        seed_sched=schedule_with_operation_precedence(state,context,'asap',seed_cons,priority)
        rec,dec,fail,seed_cert=evaluate_schedule_cached(seed_sched,context,cache)
    if not seed_cert.passed:
        # The routing state itself is not schedulably safe; return the pure result.
        pure.trace.append({'strategy':'conservative_seed_failed','c1':float(seed_cert.c1)})
        pure.verifier_calls=cache.stats.misses-start_calls;pure.cache_hits=cache.stats.hits-start_hits
        return pure

    remaining=max(1,int(max_verifier_calls)-(cache.stats.misses-start_calls))
    cons,current,cert,_=minimize_operation_constraints(state,context,method,seed_cons,cache,budget=max(1,remaining//2))
    trace=list(pure.trace)+[{'strategy':'conservative_stream_seed','seed_constraints':len(seed_cons),
                            'minimized_constraints':len(cons),'c1':float(cert.c1),
                            'duration_ns':float(current.duration_ns),'max_parallel_cx':int(current.max_parallel_cx)}]

    # Try narrowing each remaining cross-check stream boundary to local atoms.
    i=0
    while i<len(cons) and cache.stats.misses-start_calls<int(max_verifier_calls):
        coarse=cons[i];pair=_pair_of_atom(coarse)
        trial_cons=tuple(x for x in cons if x!=coarse)
        try:trial_sched=schedule_with_operation_precedence(state,context,method,trial_cons,priority)
        except Exception:
            i+=1;continue
        tr_rec,_d,tr_fail,tr_cert=evaluate_schedule_cached(trial_sched,context,cache)
        if tr_cert.passed:
            cons=trial_cons;current=trial_sched;cert=tr_cert
            trace.append({'strategy':'remove_stream_boundary','pair':list(pair),'replacement_atoms':0})
            continue
        clauses,rows=operation_witness_clauses(trial_sched,tr_rec,tr_fail,max_atoms_per_witness=24)
        # Restrict refinement to this check pair and exclude the same coarse atom.
        local_clauses=[]
        for cl in clauses:
            loc=frozenset(a for a in cl if _pair_of_atom(a)==pair and a!=coarse)
            if loc:local_clauses.append(loc)
        if not local_clauses:
            i+=1;continue
        from ftrepair_v2.hittingset import normalize_clauses
        local_clauses=normalize_clauses(local_clauses)
        atoms=set().union(*local_clauses);weights=atom_penalties(trial_sched,atoms)
        repl=hybrid_hitting_set(local_clauses,weights=weights,max_size=min(8,len(atoms)))
        if not repl:
            i+=1;continue
        candidate_cons=tuple(sorted(set(trial_cons)|set(repl)))
        if len(candidate_cons)>int(max_constraints):
            i+=1;continue
        try:cand_sched=schedule_with_operation_precedence(state,context,method,candidate_cons,priority)
        except Exception:
            i+=1;continue
        _r,_d,_f,cand_cert=evaluate_schedule_cached(cand_sched,context,cache)
        if cand_cert.passed and cand_sched.duration_ns < current.duration_ns-1e-9:
            cons=candidate_cons;current=cand_sched;cert=cand_cert
            trace.append({'strategy':'refine_stream_boundary','pair':list(pair),
                          'replacement_atoms':len(repl),'duration_ns':float(current.duration_ns)})
            # Reconsider from beginning because refinement can make another coarse
            # boundary redundant.
            i=0;continue
        i+=1

    # Final exact minimization with any remaining budget.
    rem=max(0,int(max_verifier_calls)-(cache.stats.misses-start_calls))
    if rem>0:
        cons,current,cert,_=minimize_operation_constraints(state,context,method,cons,cache,budget=rem)
    final_rec,_d,final_fail,final_cert=evaluate_schedule_cached(current,context,cache)
    serial=_serial_schedule(state,context)
    speed=(1-current.duration_ns/serial.duration_ns)*100
    fallback=OperationScheduleRepairResult(bool(final_cert.passed),tuple(cons),cache.stats.misses-start_calls,
        cache.stats.hits-start_hits,len(trace),float(pure.initial_c1),float(final_cert.c1),int(pure.initial_failures),
        int(np.count_nonzero(final_fail)),float(pure.initial_duration_ns),float(current.duration_ns),
        int(pure.initial_max_parallel_cx),int(current.max_parallel_cx),int(pure.clauses_seen),int(pure.witness_rows_seen),
        float(speed),trace,current)
    candidates.append(fallback)
    # Best safe candidate: duration first, then fewer constraints, then verifier
    # calls. Safety has already been established exactly for every candidate.
    safe=[x for x in candidates if x.success and x.final_schedule is not None]
    if safe:
        best=min(safe,key=lambda x:(x.final_duration_ns,len(x.constraints),x.verifier_calls))
        best.verifier_calls=cache.stats.misses-start_calls;best.cache_hits=cache.stats.hits-start_hits
        return best
    fallback.verifier_calls=cache.stats.misses-start_calls;fallback.cache_hits=cache.stats.hits-start_hits
    return fallback
