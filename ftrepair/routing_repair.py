"""Counterexample-guided repair of compiler-introduced routing failures.

The repair engine treats the single-fault verifier as authoritative.  It starts
from a logically fault-tolerant Steane extraction round, compiles it with the
unsafe generic SWAP router, extracts failing physical-fault witnesses, and then
searches for a nearby bridge-routed implementation.  Search expansions are
restricted to checks implicated by current counterexamples.

This is intentionally a deterministic research prototype, not a claim of a
complete FT compiler repair algorithm.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
import numpy as np

from qecflag.physics import code_tables
from qecflag.phase4_physics import verification_summary
from qecflag.phase5_actions import ensure_hardware_action_table
from qecflag.phase5_hardware import HardwareContext
from qecflag.phase6_native import (
    NativeRisk, build_native_plan, native_fault_records, build_native_decoder,
)
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase7_forensics import failing_single_fault_rows, summarize_failure_rows
from qecflag.phase7_routing import bridge_native_risk, bridge_proxy_metrics


@dataclass(frozen=True)
class RoutingCertificate:
    primitive: str
    passed: bool
    c1: float
    conflicts: int
    single_fault_failures: int
    incoming_failures: int
    native_cx: int
    duration_ns: float
    fault_outcomes: int
    physical_fault_locations: int


@dataclass
class RoutingRepairResult:
    success: bool
    start_labels: tuple[str, ...]
    start_hubs: tuple[int, ...]
    repaired_labels: tuple[str, ...] | None
    repaired_hubs: tuple[int, ...] | None
    changed_checks: tuple[int, ...]
    verifier_calls: int
    search_depth: int
    initial_swap: RoutingCertificate
    initial_bridge: RoutingCertificate
    final_bridge: RoutingCertificate | None
    initial_failure_summary: dict
    final_proxy_c2: float | None
    candidate_states_seen: int
    trace: list[dict]

    def to_dict(self) -> dict:
        out = asdict(self)
        # asdict already converts nested dataclasses but retains tuples, which
        # JSON handles fine through the standard encoder.
        return out


def _certificate_from_risk(risk: NativeRisk, primitive: str) -> RoutingCertificate:
    locs = int(len(np.unique(risk.records.location)))
    passed = bool(
        risk.c1 == 0.0
        and risk.decoder.single_fault_conflicts == 0
        and risk.decoder.single_fault_failures == 0
        and risk.decoder.incoming_failures == 0
    )
    return RoutingCertificate(
        primitive=str(primitive), passed=passed, c1=float(risk.c1),
        conflicts=int(risk.decoder.single_fault_conflicts),
        single_fault_failures=int(risk.decoder.single_fault_failures),
        incoming_failures=int(risk.decoder.incoming_failures),
        native_cx=int(risk.plan.native_cx), duration_ns=float(risk.plan.duration_ns),
        fault_outcomes=int(len(risk.records.data)), physical_fault_locations=locs,
    )


def swap_single_fault_risk(labels: Iterable[str], hubs: Iterable[int],
                           context: HardwareContext) -> NativeRisk:
    """Single-fault-only risk for the Phase-6 SWAP router (no C2 enumeration)."""
    plan = build_native_plan(labels, hubs, context)
    records = native_fault_records(plan, context)
    decoder = build_native_decoder(plan, records)
    canon, _, _, _ = code_tables()
    corr = decoder.corrections_for(records.observation)
    fail = canon[records.data ^ corr] != 0
    c1 = float(records.weight[fail].sum())
    return NativeRisk(
        plan=plan, records=records, decoder=decoder, c1=c1, c2=0.0,
        single_fault_failure_count=int(np.count_nonzero(fail)), malignant_pair_count=0,
    )


def logical_round_is_single_fault_ft(labels: Iterable[str]) -> bool:
    v = verification_summary(tuple(labels))
    return bool(
        int(v['single_fault_conflicts']) == 0
        and int(v['single_fault_logical_failures']) == 0
        and int(v['single_incoming_error_failures']) == 0
    )


def _failure_checks(risk: NativeRisk, primitive: str) -> tuple[list[int], list[dict]]:
    rows = failing_single_fault_rows(risk, primitive)
    counts = Counter(int(r['check_index']) for r in rows)
    # Most implicated checks first, then deterministic check index.
    checks = [c for c, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return checks, rows


def _allowed_local_options(project_root: Path) -> dict[int, tuple[tuple[str, int], ...]]:
    """Local (template, hub) pairs that appear in a Phase-7 certified round."""
    cat = ensure_catalog(project_root, progress=False)
    by_check: dict[int, set[tuple[str, int]]] = {i: set() for i in range(6)}
    for e in cat.entries:
        for ci, (label, hub) in enumerate(zip(e['labels'], e['hubs'])):
            by_check[ci].add((str(label), int(hub)))
    return {ci: tuple(sorted(v, key=lambda x: (x[1], x[0]))) for ci, v in by_check.items()}


def _state_key(labels: tuple[str, ...], hubs: tuple[int, ...]) -> tuple:
    return tuple(zip(labels, hubs))


def _changed_checks(start_labels, start_hubs, labels, hubs) -> tuple[int, ...]:
    return tuple(i for i in range(6) if start_labels[i] != labels[i] or int(start_hubs[i]) != int(hubs[i]))


def repair_routing(project_root: Path, labels: Iterable[str], hubs: Iterable[int],
                   context: HardwareContext, max_edits: int = 3,
                   max_verifier_calls: int = 96,
                   witness_check_limit: int = 3) -> RoutingRepairResult:
    """Repair a logically FT round after physical routing breaks FT.

    The first repair is always a compiler-level primitive replacement:
    SWAP-restore -> bridge.  If the same logical schedule is still unsafe, a
    BFS changes only local check implementations implicated by exact failing
    single-fault witnesses.  Candidate local replacements come only from the
    pre-certified Phase-7 physical catalog.
    """
    root = Path(project_root)
    labels0 = tuple(str(x) for x in labels)
    hubs0 = tuple(int(x) for x in hubs)
    if len(labels0) != 6 or len(hubs0) != 6:
        raise ValueError('expected six checks')
    if not logical_round_is_single_fault_ft(labels0):
        raise ValueError('routing repair requires a logically single-fault-FT input round')

    verifier_calls = 0
    swap = swap_single_fault_risk(labels0, hubs0, context); verifier_calls += 1
    swap_cert = _certificate_from_risk(swap, 'swap_restore')
    swap_checks, swap_rows = _failure_checks(swap, 'swap_restore')

    bridge0 = bridge_native_risk(labels0, hubs0, context, compute_c2=False); verifier_calls += 1
    bridge0_cert = _certificate_from_risk(bridge0, 'bridge')
    trace = [{
        'step': 0, 'operation': 'replace_router', 'primitive': 'bridge',
        'labels': list(labels0), 'hubs': list(hubs0),
        'passed': bridge0_cert.passed, 'c1': bridge0_cert.c1,
        'failing_checks': _failure_checks(bridge0, 'bridge')[0] if not bridge0_cert.passed else [],
    }]
    if bridge0_cert.passed:
        proxy = bridge_proxy_metrics(labels0, hubs0, context)
        return RoutingRepairResult(
            True, labels0, hubs0, labels0, hubs0, tuple(), verifier_calls, 0,
            swap_cert, bridge0_cert, bridge0_cert, summarize_failure_rows(swap_rows),
            float(proxy.c2), 1, trace,
        )

    allowed = _allowed_local_options(root)
    q = deque([(labels0, hubs0, 0)])
    seen = {_state_key(labels0, hubs0)}
    candidates_seen = 1
    best_safe: tuple | None = None

    while q and verifier_calls < int(max_verifier_calls):
        cur_labels, cur_hubs, depth = q.popleft()
        risk = bridge0 if depth == 0 and cur_labels == labels0 and cur_hubs == hubs0 else bridge_native_risk(
            cur_labels, cur_hubs, context, compute_c2=False
        )
        if not (depth == 0 and cur_labels == labels0 and cur_hubs == hubs0):
            verifier_calls += 1
        cert = _certificate_from_risk(risk, 'bridge')
        if cert.passed:
            changed = _changed_checks(labels0, hubs0, cur_labels, cur_hubs)
            proxy = bridge_proxy_metrics(cur_labels, cur_hubs, context)
            # Candidate expansions are proxy-ranked before exact verification.
            # Returning the first certified state keeps the loop genuinely
            # counterexample-guided and avoids exhaustively re-verifying every
            # equal-edit alternative merely to shave proxy cost.
            trace.append({
                'step': len(trace), 'operation': 'repair_complete', 'passed': True,
                'changed_checks': list(changed), 'labels': list(cur_labels), 'hubs': list(cur_hubs),
                'c1': cert.c1, 'proxy_c2': float(proxy.c2),
            })
            return RoutingRepairResult(
                True, labels0, hubs0, cur_labels, cur_hubs, changed, verifier_calls, len(changed),
                swap_cert, bridge0_cert, cert, summarize_failure_rows(swap_rows),
                float(proxy.c2), candidates_seen, trace,
            )
        if depth >= int(max_edits):
            continue

        implicated, rows = _failure_checks(risk, 'bridge')
        if not implicated:
            implicated = list(range(6))
        implicated = implicated[:max(1, int(witness_check_limit))]
        trace.append({
            'step': len(trace), 'operation': 'witness', 'depth': depth,
            'labels': list(cur_labels), 'hubs': list(cur_hubs), 'c1': cert.c1,
            'failing_checks': implicated,
            'failure_count': len(rows),
        })
        expansions = []
        for ci in implicated:
            for label, hub in allowed[ci]:
                if label == cur_labels[ci] and int(hub) == int(cur_hubs[ci]):
                    continue
                nl = list(cur_labels); nh = list(cur_hubs)
                nl[ci] = label; nh[ci] = int(hub)
                nl = tuple(nl); nh = tuple(nh)
                key = _state_key(nl, nh)
                if key in seen:
                    continue
                changed = _changed_checks(labels0, hubs0, nl, nh)
                if len(changed) > int(max_edits):
                    continue
                # Ranking candidates by the cheap Phase-7 proxy does not certify
                # them; it only decides which exact verifier call to make first.
                proxy = bridge_proxy_metrics(nl, nh, context)
                expansions.append(((len(changed), proxy.c2, proxy.native_cx, proxy.duration_ns, ci, hub, label), nl, nh))
        expansions.sort(key=lambda x: x[0])
        for _rank, nl, nh in expansions:
            key = _state_key(nl, nh)
            if key in seen:
                continue
            seen.add(key); candidates_seen += 1
            q.append((nl, nh, depth + 1))

    if best_safe is None:
        return RoutingRepairResult(
            False, labels0, hubs0, None, None, tuple(), verifier_calls, int(max_edits),
            swap_cert, bridge0_cert, None, summarize_failure_rows(swap_rows), None,
            candidates_seen, trace,
        )
    _, labels1, hubs1, cert1, proxy1 = best_safe
    changed = _changed_checks(labels0, hubs0, labels1, hubs1)
    trace.append({
        'step': len(trace), 'operation': 'repair_complete', 'passed': True,
        'changed_checks': list(changed), 'labels': list(labels1), 'hubs': list(hubs1),
        'c1': cert1.c1, 'proxy_c2': float(proxy1.c2),
    })
    return RoutingRepairResult(
        True, labels0, hubs0, labels1, hubs1, changed, verifier_calls, len(changed),
        swap_cert, bridge0_cert, cert1, summarize_failure_rows(swap_rows),
        float(proxy1.c2), candidates_seen, trace,
    )


def find_logical_ft_bridge_unsafe_homogeneous_cases(project_root: Path, context: HardwareContext,
                                                     limit: int = 8) -> list[dict]:
    """Deterministically locate logically FT homogeneous rounds unsafe after bridge routing."""
    table = ensure_hardware_action_table(Path(project_root))
    out = []
    for action in range(table.n_actions):
        labels = tuple(table.template_label(action) for _ in range(6))
        hubs = tuple(table.hub(action) for _ in range(6))
        if not logical_round_is_single_fault_ft(labels):
            continue
        risk = bridge_native_risk(labels, hubs, context, compute_c2=False)
        cert = _certificate_from_risk(risk, 'bridge')
        if not cert.passed:
            out.append({
                'action': int(action), 'hardware_label': table.labels[action],
                'labels': list(labels), 'hubs': list(hubs), 'bridge_c1': cert.c1,
                'bridge_failures': cert.single_fault_failures,
            })
            if len(out) >= int(limit):
                break
    return out
