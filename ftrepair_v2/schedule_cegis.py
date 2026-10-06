"""Global CEGIS repair for compiler-introduced unsafe parallel schedules.

Unlike v1's one-witness/one-pair greedy loop, this module accumulates clauses
from *all* current single-fault counterexamples.  A clause contains pairwise
precedence constraints capable of eliminating a witness.  The next repair is an
exact minimum-cardinality weighted hitting set over all accumulated clauses.
Every candidate is still accepted only by the authoritative physical verifier.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from itertools import combinations
from typing import Iterable
import numpy as np

from qecflag.phase5_hardware import HardwareContext
from qecflag.phase10_scheduler import ParallelSchedule, validate_resource_schedule, schedule_parallel
from ftrepair.schedule_repair import schedule_with_precedence, _evaluate_schedule
from .hittingset import minimum_weight_hitting_set, normalize_clauses

Pair = tuple[int, int]
ALL_PAIRS: tuple[Pair, ...] = tuple(combinations(range(6), 2))


@dataclass
class CEGISScheduleRepairResult:
    success: bool
    method: str
    constraints: tuple[Pair, ...]
    verifier_calls: int
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
    retained_speedup_vs_serial_percent: float | None
    trace: list[dict]
    final_schedule: ParallelSchedule | None = None

    def to_dict(self, include_schedule: bool = False) -> dict:
        d = asdict(self)
        if not include_schedule:
            d.pop('final_schedule', None)
        return d


def _overlap(a, b) -> bool:
    return a.start_ns < b.stop_ns - 1e-9 and b.start_ns < a.stop_ns - 1e-9


def _active_cx_checks(schedule: ParallelSchedule, start: float, stop: float) -> set[int]:
    return {
        int(se.event.check) for se in schedule.events
        if se.event.kind == 'cx'
        and se.start_ns < stop - 1e-9 and se.stop_ns > start + 1e-9
    }


def witness_clauses(schedule: ParallelSchedule, records, fail_mask) -> tuple[list[frozenset[Pair]], list[dict]]:
    """Translate exact failing faults into repair clauses.

    For an event fault, any currently overlapping CX check pair involving the
    event's check can remove that concurrency.  For an idle-slice fault, any pair
    among simultaneously active CX checks is a candidate.  If a witness has no
    instantaneous overlap, use pairs between its check and any check whose CX
    stream overlaps the witness check's full CX span; this captures unsafe
    interleaving even when the precise faulty gate is not simultaneous.
    """
    by_uid = {se.event.uid: se for se in schedule.events}
    by_slice = {sl.index: sl for sl in schedule.idle_slices}
    cx_by_check = {
        c: [se for se in schedule.events if se.event.kind == 'cx' and se.event.check == c]
        for c in range(6)
    }
    clauses: list[frozenset[Pair]] = []
    rows: list[dict] = []

    for idx in np.flatnonzero(fail_mask):
        desc = records.descriptors[int(idx)]
        clause: set[Pair] = set()
        origin_check = None
        window = None
        if getattr(desc, 'event_uid', -1) >= 0 and desc.event_uid in by_uid:
            base = by_uid[desc.event_uid]
            origin_check = int(base.event.check)
            window = (float(base.start_ns), float(base.stop_ns))
            for other in schedule.events:
                if other.event.kind != 'cx' or other.event.check == origin_check:
                    continue
                if _overlap(base, other):
                    clause.add(tuple(sorted((origin_check, int(other.event.check)))))
        elif getattr(desc, 'slice_index', -1) >= 0 and desc.slice_index in by_slice:
            sl = by_slice[desc.slice_index]
            window = (float(sl.start_ns), float(sl.stop_ns))
            active = sorted(_active_cx_checks(schedule, *window))
            clause.update(tuple(sorted(x)) for x in combinations(active, 2))

        if not clause and origin_check is not None and cx_by_check[origin_check]:
            a0 = min(x.start_ns for x in cx_by_check[origin_check])
            a1 = max(x.stop_ns for x in cx_by_check[origin_check])
            for c in range(6):
                if c == origin_check or not cx_by_check[c]:
                    continue
                b0 = min(x.start_ns for x in cx_by_check[c])
                b1 = max(x.stop_ns for x in cx_by_check[c])
                if a0 < b1 - 1e-9 and b0 < a1 - 1e-9:
                    clause.add(tuple(sorted((origin_check, c))))

        if not clause:
            # Last-resort global concurrency clause: a verifier failure with no
            # localizable overlap should still force refinement, but only using
            # check pairs that actually overlap somewhere in this schedule.
            for a, b in ALL_PAIRS:
                if any(_overlap(x, y) for x in cx_by_check[a] for y in cx_by_check[b]):
                    clause.add((a, b))

        if clause:
            clauses.append(frozenset(clause))
        rows.append({
            'fault_index': int(idx),
            'kind': str(getattr(desc, 'kind', 'unknown')),
            'origin_check': origin_check,
            'candidate_pairs': [list(p) for p in sorted(clause)],
            'weight': float(records.weight[int(idx)]),
            'window': list(window) if window is not None else None,
        })
    return clauses, rows


def _pair_penalties(labels, hubs, context: HardwareContext, method: str,
                    priority: tuple[int, ...], serial_duration: float) -> dict[Pair, float]:
    """Estimate optimization damage of forbidding one check pair.

    A tiny max-parallelism penalty breaks ties in favor of preserving CX
    concurrency.  These are only synthesis costs; the verifier remains the
    authority on safety.
    """
    base = schedule_with_precedence(labels, hubs, context, method, priority, ())
    out = {}
    for pair in ALL_PAIRS:
        s = schedule_with_precedence(labels, hubs, context, method, priority, (pair,))
        dur_pen = max(0.0, (s.duration_ns - base.duration_ns) / max(serial_duration, 1e-12))
        par_pen = max(0, base.max_parallel_cx - s.max_parallel_cx) * 0.01
        out[pair] = float(dur_pen + par_pen + 1e-9)
    return out


def repair_parallel_schedule_cegis(
    labels: Iterable[str], hubs: Iterable[int], context: HardwareContext,
    method: str = 'shortest_greedy', check_priority: tuple[int, ...] | None = None,
    max_constraints: int = 15, max_verifier_calls: int = 20,
) -> CEGISScheduleRepairResult:
    labels = tuple(labels); hubs = tuple(int(x) for x in hubs)
    priority = tuple(range(6)) if check_priority is None else tuple(check_priority)
    serial = schedule_parallel(labels, hubs, context, 'serialized')
    initial = schedule_with_precedence(labels, hubs, context, method, priority, ())
    if not validate_resource_schedule(initial):
        raise ValueError('initial schedule is resource-invalid')
    records, _dec, fail, cert = _evaluate_schedule(initial, context)
    verifier_calls = 1
    initial_failures = int(np.count_nonzero(fail))
    trace = [{
        'iteration': 0, 'constraints': [], 'passed': bool(cert.passed), 'c1': float(cert.c1),
        'failures': initial_failures, 'duration_ns': float(initial.duration_ns),
        'max_parallel_cx': int(initial.max_parallel_cx),
    }]
    if cert.passed:
        speed = (1.0 - initial.duration_ns / serial.duration_ns) * 100.0
        return CEGISScheduleRepairResult(True, method, tuple(), 1, 0, float(cert.c1), float(cert.c1),
            initial_failures, initial_failures, float(initial.duration_ns), float(initial.duration_ns),
            int(initial.max_parallel_cx), int(initial.max_parallel_cx), 0, 0, float(speed), trace, initial)

    penalties = _pair_penalties(labels, hubs, context, method, priority, serial.duration_ns)
    clauses: list[frozenset[Pair]] = []
    witness_rows_seen = 0
    current = initial; current_records = records; current_fail = fail; current_cert = cert
    fixed: set[Pair] = set()
    constraints: tuple[Pair, ...] = tuple()

    for iteration in range(1, int(max_verifier_calls)):
        new_clauses, witness_rows = witness_clauses(current, current_records, current_fail)
        witness_rows_seen += len(witness_rows)
        # Current witnesses occur despite all already-fixed precedences.  Solve a
        # minimum hitting set over the *remaining* repair atoms and then add the
        # whole batch monotonically.  This prevents cycling between equally-small
        # repairs that reintroduce previously eliminated counterexamples.
        residual = []
        for c in new_clauses:
            rem = frozenset(p for p in c if p not in fixed)
            if rem:
                residual.append(rem)
        residual = list(normalize_clauses(residual))
        clauses.extend(residual)
        clauses = list(normalize_clauses(clauses))
        additions = minimum_weight_hitting_set(
            residual, weights=penalties, universe=[p for p in ALL_PAIRS if p not in fixed],
            max_size=max(0, int(max_constraints)-len(fixed)),
        ) if residual else None
        if not additions:
            break
        fixed.update(tuple(sorted(p)) for p in additions)
        if len(fixed) > int(max_constraints):
            break
        constraints = tuple(sorted(fixed))
        current = schedule_with_precedence(labels, hubs, context, method, priority, constraints)
        current_records, _dec, current_fail, current_cert = _evaluate_schedule(current, context)
        verifier_calls += 1
        nfail = int(np.count_nonzero(current_fail))
        trace.append({
            'iteration': iteration,
            'added_constraints': [list(p) for p in sorted(additions)],
            'constraints': [list(p) for p in constraints],
            'clauses_added': [[list(p) for p in sorted(c)] for c in residual],
            'passed': bool(current_cert.passed), 'c1': float(current_cert.c1),
            'failures': nfail, 'duration_ns': float(current.duration_ns),
            'max_parallel_cx': int(current.max_parallel_cx),
            'witnesses_added': len(witness_rows),
        })
        if current_cert.passed:
            speed = (1.0 - current.duration_ns / serial.duration_ns) * 100.0
            return CEGISScheduleRepairResult(
                True, method, constraints, verifier_calls, iteration,
                float(cert.c1), float(current_cert.c1), initial_failures, nfail,
                float(initial.duration_ns), float(current.duration_ns),
                int(initial.max_parallel_cx), int(current.max_parallel_cx),
                len(clauses), witness_rows_seen, float(speed), trace, current,
            )
        if verifier_calls >= int(max_verifier_calls):
            break

    speed = (1.0 - current.duration_ns / serial.duration_ns) * 100.0 if current is not None else None
    return CEGISScheduleRepairResult(
        False, method, constraints, verifier_calls, max(0, verifier_calls - 1),
        float(cert.c1), float(current_cert.c1), initial_failures, int(np.count_nonzero(current_fail)),
        float(initial.duration_ns), float(current.duration_ns),
        int(initial.max_parallel_cx), int(current.max_parallel_cx),
        len(clauses), witness_rows_seen, float(speed) if speed is not None else None, trace, current,
    )


def minimize_safe_constraints(labels, hubs, context: HardwareContext, method: str,
                              constraints: Iterable[Pair], check_priority: tuple[int,...] | None = None,
                              verifier_budget: int = 32):
    """Delta-debug a certified constraint set while preserving exact FT.

    Returns (constraints, schedule, certificate, verifier_calls).  Constraints
    are tested in descending estimated timing penalty so expensive restrictions
    are preferentially removed.
    """
    priority=tuple(range(6)) if check_priority is None else tuple(check_priority)
    serial=schedule_parallel(labels,hubs,context,'serialized')
    penalties=_pair_penalties(tuple(labels),tuple(hubs),context,method,priority,serial.duration_ns)
    fixed=set(tuple(sorted(p)) for p in constraints)
    calls=0
    current=schedule_with_precedence(labels,hubs,context,method,priority,fixed)
    _r,_d,_f,cert=_evaluate_schedule(current,context);calls+=1
    if not cert.passed:
        return tuple(sorted(fixed)),current,cert,calls
    order=sorted(fixed,key=lambda p:(-penalties.get(p,0.0),p))
    for p in order:
        if calls>=int(verifier_budget):break
        trial=set(fixed);trial.remove(p)
        s=schedule_with_precedence(labels,hubs,context,method,priority,trial)
        _r,_d,_f,c=_evaluate_schedule(s,context);calls+=1
        if c.passed:
            fixed=trial;current=s;cert=c
    return tuple(sorted(fixed)),current,cert,calls


def repair_parallel_schedule_portfolio(labels: Iterable[str], hubs: Iterable[int], context: HardwareContext,
                                       method: str='shortest_greedy', check_priority: tuple[int,...] | None=None,
                                       max_constraints: int=15, max_verifier_calls: int=32) -> CEGISScheduleRepairResult:
    """Robust v2 portfolio: global CEGIS, witness-greedy seed, exact minimization.

    The global hitting-set path is attempted first.  If it cannot certify within
    budget, the mature v1 witness-greedy repair is used as an independent seed.
    Any safe seed is then exact-delta-minimized, so v2 never accepts safety from
    the heuristic itself.  This makes the implementation robust enough for the
    multi-family benchmark while preserving a clean pure-hitting-set ablation.
    """
    labels=tuple(labels);hubs=tuple(int(x) for x in hubs)
    priority=tuple(range(6)) if check_priority is None else tuple(check_priority)
    global_budget=max(4,int(max_verifier_calls)//2)
    pure=repair_parallel_schedule_cegis(labels,hubs,context,method,priority,max_constraints,global_budget)
    if pure.success:
        cons,sched,cert,extra=minimize_safe_constraints(labels,hubs,context,method,pure.constraints,priority,
                                                        verifier_budget=max(1,int(max_verifier_calls)-pure.verifier_calls))
        if cert.passed:
            serial=schedule_parallel(labels,hubs,context,'serialized')
            speed=(1-sched.duration_ns/serial.duration_ns)*100.0
            pure.constraints=cons;pure.final_schedule=sched;pure.final_c1=float(cert.c1)
            pure.final_duration_ns=float(sched.duration_ns);pure.final_max_parallel_cx=int(sched.max_parallel_cx)
            pure.verifier_calls+=extra;pure.retained_speedup_vs_serial_percent=float(speed)
            pure.trace.append({'strategy':'global_hittingset_then_minimize','minimized_constraints':[list(x) for x in cons]})
            return pure

    # Independent v1 seed.
    from ftrepair.schedule_repair import repair_parallel_schedule
    v1=repair_parallel_schedule(labels,hubs,context,method,priority,max_constraints=max_constraints)
    calls=pure.verifier_calls + v1.verifier_calls
    if not v1.success or v1.final_schedule is None:
        pure.trace.append({'strategy':'portfolio_exhausted','v1_success':False,'v1_calls':v1.verifier_calls})
        pure.verifier_calls=calls
        return pure
    remain=max(1,int(max_verifier_calls)-calls)
    cons,sched,cert,extra=minimize_safe_constraints(labels,hubs,context,method,v1.constraints,priority,verifier_budget=remain)
    calls+=extra
    serial=schedule_parallel(labels,hubs,context,'serialized')
    speed=(1-sched.duration_ns/serial.duration_ns)*100.0
    records,_dec,fail,_c=_evaluate_schedule(sched,context)
    calls+=1
    return CEGISScheduleRepairResult(
        bool(cert.passed),method,cons,calls,len(cons),float(pure.initial_c1),float(cert.c1),
        int(pure.initial_failures),int(np.count_nonzero(fail)),float(pure.initial_duration_ns),float(sched.duration_ns),
        int(pure.initial_max_parallel_cx),int(sched.max_parallel_cx),int(pure.clauses_seen),int(pure.witness_rows_seen),
        float(speed),pure.trace+v1.trace+[{'strategy':'v1_seed_then_exact_minimize','minimized_constraints':[list(x) for x in cons]}],sched)
