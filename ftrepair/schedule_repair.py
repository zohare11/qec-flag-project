"""Counterexample-guided repair of unsafe parallel syndrome-extraction schedules.

Phase 10 showed that a resource-valid parallel schedule can destroy the
single-fault guarantee.  This module adds a CEGAR-style loop: certify an
aggressive schedule, localize failing fault witnesses to overlapping check
pairs, add the smallest deterministic precedence constraint suggested by the
witnesses, reschedule, and repeat until C1=0 or the repair budget is exhausted.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict
from typing import Iterable
import numpy as np

from qecflag.physics import code_tables
from qecflag.phase4_physics import OBS_FINAL_SHIFT
from qecflag.phase5_hardware import HardwareContext
from qecflag.phase10_scheduler import (
    ProgramEvent, ScheduledEvent, ParallelSchedule,
    build_programs, _priority_key, _finalize_schedule,
    validate_resource_schedule, parallel_fault_records, build_parallel_decoder,
    certify_parallel_schedule, ParallelCertificate, simulate_parallel_round,
)


@dataclass
class ScheduleRepairResult:
    success: bool
    method: str
    priority: tuple[int, ...]
    constraints: tuple[tuple[int, int], ...]
    iterations: int
    verifier_calls: int
    initial_c1: float
    final_c1: float | None
    initial_duration_ns: float
    final_duration_ns: float | None
    initial_max_parallel_cx: int
    final_max_parallel_cx: int | None
    initial_failures: int
    final_failures: int | None
    trace: list[dict]
    final_schedule: ParallelSchedule | None = None

    def to_dict(self, include_schedule: bool = False) -> dict:
        d = asdict(self)
        if not include_schedule:
            d.pop('final_schedule', None)
        return d


def _last_cx_seq(programs, check: int) -> int:
    seqs = [ev.seq for ev in programs[check] if ev.kind == 'cx']
    return max(seqs) if seqs else -1


def schedule_with_precedence(labels: Iterable[str], hubs: Iterable[int], context: HardwareContext,
                             method: str = 'asap',
                             check_priority: tuple[int, ...] | None = None,
                             forbidden_pairs: Iterable[tuple[int, int]] = ()) -> ParallelSchedule:
    """Schedule with pairwise check precedence constraints on native CNOTs.

    A pair (a,b) means their native CNOT streams may not overlap or interleave.
    The check appearing earlier in ``check_priority`` owns the precedence.
    Prep/measurement blocks may still overlap when resources permit.
    """
    native, programs = build_programs(labels, hubs, context)
    if check_priority is None:
        check_priority = tuple(range(6))
    priority = tuple(int(x) for x in check_priority)
    if tuple(sorted(priority)) != tuple(range(6)):
        raise ValueError('check_priority must be a permutation of 0..5')
    rank = {c: i for i, c in enumerate(priority)}
    forbidden = {tuple(sorted((int(a), int(b)))) for a, b in forbidden_pairs if int(a) != int(b)}
    if any(a < 0 or b > 5 for a, b in forbidden):
        raise ValueError('check pair out of range')

    ptr = [0] * 6
    ready_at = [0.0] * 6
    running: list[ScheduledEvent] = []
    scheduled: list[ScheduledEvent] = []
    t = 0.0
    total = sum(len(p) for p in programs)
    eps = 1e-9
    last_cx = [_last_cx_seq(programs, c) for c in range(6)]

    def higher_precedence_unfinished(c: int, tnow: float) -> bool:
        for pair in forbidden:
            if c not in pair:
                continue
            d = pair[0] if pair[1] == c else pair[1]
            if rank[d] >= rank[c]:
                continue
            # Higher-priority d must have completed its last CX.
            for se in running:
                if se.event.check == d and se.event.kind == 'cx' and se.stop_ns > tnow + eps:
                    return True
            if ptr[d] == 0:
                return True
            # ptr points to next unscheduled event. If the most recently scheduled
            # event seq is before the last CX seq, d still has a CX to schedule.
            if ptr[d] <= last_cx[d]:
                return True
        return False

    while len(scheduled) < total:
        running = [x for x in running if x.stop_ns > t + eps]
        busy = set()
        for x in running:
            busy.update(x.event.resources)

        candidates = []
        for c in range(6):
            if ptr[c] < len(programs[c]) and ready_at[c] <= t + eps:
                candidates.append(programs[c][ptr[c]])
        candidates.sort(key=lambda e: _priority_key(e, method, context, programs, priority))

        launched = False
        for ev in candidates:
            if any(r in busy for r in ev.resources):
                continue
            if ev.kind == 'cx':
                if higher_precedence_unfinished(ev.check, t):
                    continue
                pair_conflict = False
                for se in running:
                    if se.event.kind != 'cx' or se.event.check == ev.check:
                        continue
                    if tuple(sorted((ev.check, se.event.check))) in forbidden:
                        pair_conflict = True; break
                if pair_conflict:
                    continue
            se = ScheduledEvent(ev, float(t))
            scheduled.append(se); running.append(se); launched = True
            busy.update(ev.resources)
            ptr[ev.check] += 1
            ready_at[ev.check] = se.stop_ns

        if len(scheduled) >= total:
            break
        if running:
            next_t = min(x.stop_ns for x in running)
        else:
            future = [ready_at[c] for c in range(6) if ptr[c] < len(programs[c])]
            if not future:
                raise RuntimeError('constrained scheduler stalled')
            next_t = min(future)
        if next_t <= t + eps:
            if not launched:
                # Advance to the earliest already-scheduled completion or the next
                # higher-priority dependency completion.
                candidates_t = [x.stop_ns for x in running if x.stop_ns > t + eps]
                if not candidates_t:
                    raise RuntimeError('constrained scheduler made no progress')
                next_t = min(candidates_t)
            else:
                next_t = t + eps
        t = float(next_t)

    s = _finalize_schedule(native, scheduled, context, f'repaired_{method}', priority)
    if not validate_resource_schedule(s):
        raise RuntimeError('repair scheduler produced resource-invalid schedule')
    return s


def _evaluate_schedule(schedule: ParallelSchedule, context: HardwareContext):
    """One-pass single-fault evaluation used by the repair loop."""
    if not validate_resource_schedule(schedule):
        raise ValueError('resource-invalid parallel schedule')
    ideal_data, ideal_obs = simulate_parallel_round(schedule)
    extraction_mask = (1 << OBS_FINAL_SHIFT) - 1
    ideal_ok = bool(ideal_data == 0 and (ideal_obs & extraction_mask) == 0)
    records = parallel_fault_records(schedule, context)
    decoder = build_parallel_decoder(schedule, records)
    canon, _, _, _ = code_tables()
    corr = decoder.corrections_for(records.observation)
    fail = canon[records.data ^ corr] != 0
    c1 = float(records.weight[fail].sum())
    cert = ParallelCertificate(
        passed=bool(ideal_ok and c1 == 0.0 and decoder.single_fault_conflicts == 0
                    and decoder.single_fault_failures == 0 and decoder.incoming_failures == 0),
        ideal_ok=ideal_ok, c1=c1, conflicts=int(decoder.single_fault_conflicts),
        single_fault_failures=int(decoder.single_fault_failures),
        incoming_failures=int(decoder.incoming_failures), fault_outcomes=int(len(records.data)),
        physical_fault_locations=int(len(np.unique(records.location))),
        duration_ns=float(schedule.duration_ns), total_data_idle_ns=float(sum(schedule.data_idle_ns)),
        max_parallel_cx=int(schedule.max_parallel_cx), native_cx=int(schedule.total_native_cx),
    )
    return records, decoder, fail, cert


def _pair_scores_from_witnesses(schedule: ParallelSchedule, records, fail,
                                forbidden: set[tuple[int, int]]) -> tuple[Counter, int]:
    uid = {se.event.uid: se for se in schedule.events}
    slices = {sl.index: sl for sl in schedule.idle_slices}
    scores: Counter = Counter()
    nfail = int(np.count_nonzero(fail))

    for idx in np.flatnonzero(fail):
        desc = records.descriptors[int(idx)]
        w = float(records.weight[int(idx)])
        candidate_checks: set[int] = set()
        if desc.event_uid >= 0 and desc.event_uid in uid:
            base = uid[desc.event_uid]
            c = int(base.event.check)
            for other in schedule.events:
                if other.event.check == c or other.event.kind != 'cx':
                    continue
                overlap = base.start_ns < other.stop_ns - 1e-9 and other.start_ns < base.stop_ns - 1e-9
                if overlap:
                    candidate_checks.add(int(other.event.check))
            for d in candidate_checks:
                pair = tuple(sorted((c, d)))
                if pair not in forbidden:
                    scores[pair] += max(w, 1e-15)
        elif desc.slice_index >= 0 and desc.slice_index in slices:
            sl = slices[desc.slice_index]
            active = sorted({
                int(se.event.check) for se in schedule.events
                if se.event.kind == 'cx'
                and se.start_ns < sl.stop_ns - 1e-9 and se.stop_ns > sl.start_ns + 1e-9
            })
            for i, a in enumerate(active):
                for b in active[i + 1:]:
                    pair = (a, b)
                    if pair not in forbidden:
                        scores[pair] += max(w, 1e-15)

    # Fallback: score all currently overlapping CX check pairs by overlap time.
    if not scores:
        evs = [se for se in schedule.events if se.event.kind == 'cx']
        for i, a in enumerate(evs):
            for b in evs[i + 1:]:
                if a.event.check == b.event.check:
                    continue
                pair = tuple(sorted((int(a.event.check), int(b.event.check))))
                if pair in forbidden:
                    continue
                overlap = min(a.stop_ns, b.stop_ns) - max(a.start_ns, b.start_ns)
                if overlap > 1e-9:
                    scores[pair] += float(overlap)
    return scores, nfail


def repair_parallel_schedule(labels: Iterable[str], hubs: Iterable[int], context: HardwareContext,
                             method: str = 'asap',
                             check_priority: tuple[int, ...] | None = None,
                             max_constraints: int = 15) -> ScheduleRepairResult:
    labels = tuple(labels); hubs = tuple(int(x) for x in hubs)
    priority = tuple(range(6)) if check_priority is None else tuple(int(x) for x in check_priority)
    forbidden: set[tuple[int, int]] = set()
    trace: list[dict] = []
    verifier_calls = 0

    initial = schedule_with_precedence(labels, hubs, context, method, priority, forbidden)
    initial_records, _initial_dec, initial_fail_mask, initial_cert = _evaluate_schedule(initial, context); verifier_calls += 1
    initial_failures = int(np.count_nonzero(initial_fail_mask))
    trace.append({
        'iteration': 0, 'constraints': [], 'c1': float(initial_cert.c1),
        'passed': bool(initial_cert.passed), 'duration_ns': float(initial.duration_ns),
        'max_parallel_cx': int(initial.max_parallel_cx), 'single_fault_failures': initial_failures,
    })
    if initial_cert.passed:
        return ScheduleRepairResult(
            True, method, priority, tuple(), 0, verifier_calls, float(initial_cert.c1),
            float(initial_cert.c1), float(initial.duration_ns), float(initial.duration_ns),
            int(initial.max_parallel_cx), int(initial.max_parallel_cx), initial_failures, initial_failures,
            trace, initial,
        )

    current = initial
    current_cert = initial_cert
    current_records = initial_records
    current_fail_mask = initial_fail_mask
    final_failures = initial_failures
    for iteration in range(1, int(max_constraints) + 1):
        scores, nfail = _pair_scores_from_witnesses(current, current_records, current_fail_mask, forbidden)
        if not scores:
            break
        pair = min(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        forbidden.add(pair)
        current = schedule_with_precedence(labels, hubs, context, method, priority, forbidden)
        current_records, _current_dec, current_fail_mask, current_cert = _evaluate_schedule(current, context); verifier_calls += 1
        final_failures = int(np.count_nonzero(current_fail_mask))
        trace.append({
            'iteration': iteration, 'added_constraint': list(pair),
            'constraint_score': float(scores[pair]),
            'constraints': [list(x) for x in sorted(forbidden)],
            'c1': float(current_cert.c1), 'passed': bool(current_cert.passed),
            'duration_ns': float(current.duration_ns), 'max_parallel_cx': int(current.max_parallel_cx),
            'single_fault_failures': final_failures,
        })
        if current_cert.passed:
            return ScheduleRepairResult(
                True, method, priority, tuple(sorted(forbidden)), iteration, verifier_calls,
                float(initial_cert.c1), float(current_cert.c1), float(initial.duration_ns),
                float(current.duration_ns), int(initial.max_parallel_cx), int(current.max_parallel_cx),
                initial_failures, final_failures, trace, current,
            )

    return ScheduleRepairResult(
        False, method, priority, tuple(sorted(forbidden)), len(forbidden), verifier_calls,
        float(initial_cert.c1), float(current_cert.c1), float(initial.duration_ns),
        float(current.duration_ns), int(initial.max_parallel_cx), int(current.max_parallel_cx),
        initial_failures, final_failures, trace, current,
    )
