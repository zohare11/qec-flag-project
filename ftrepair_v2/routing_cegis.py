"""Multi-defect counterexample-guided repair of physical lowering choices."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from heapq import heappush, heappop
from pathlib import Path
from typing import Iterable
import numpy as np

from qecflag.phase4_physics import verification_summary
from qecflag.phase5_hardware import HardwareContext
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase7_forensics import failing_single_fault_rows
from qecflag.phase7_routing import bridge_native_risk, bridge_proxy_metrics


@dataclass
class MultiRoutingRepairResult:
    success: bool
    start_labels: tuple[str, ...]
    start_hubs: tuple[int, ...]
    repaired_labels: tuple[str, ...] | None
    repaired_hubs: tuple[int, ...] | None
    changed_checks: tuple[int, ...]
    verifier_calls: int
    states_seen: int
    initial_c1: float
    final_c1: float | None
    initial_failures: int
    final_failures: int | None
    witness_checks_seen: tuple[int, ...]
    final_proxy_c2: float | None
    trace: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def _passed(risk) -> bool:
    return bool(risk.c1 == 0.0 and risk.decoder.single_fault_conflicts == 0
                and risk.decoder.single_fault_failures == 0 and risk.decoder.incoming_failures == 0)


def _logical_ft(labels) -> bool:
    v = verification_summary(tuple(labels))
    return bool(v['single_fault_conflicts'] == 0 and v['single_fault_logical_failures'] == 0
                and v['single_incoming_error_failures'] == 0)


def _options_from_catalog(project_root: Path) -> dict[int, tuple[tuple[str,int], ...]]:
    cat = ensure_catalog(project_root, progress=False)
    by = {i: set() for i in range(6)}
    for e in cat.entries:
        for ci, (l, h) in enumerate(zip(e['labels'], e['hubs'])):
            by[ci].add((str(l), int(h)))
    return {k: tuple(sorted(v, key=lambda x: (x[1], x[0]))) for k,v in by.items()}


def _fail_info(risk):
    rows = failing_single_fault_rows(risk, 'bridge')
    counts = {}
    for r in rows:
        c = int(r['check_index']); counts[c] = counts.get(c, 0) + 1
    checks = tuple(c for c,_ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    return rows, checks


def repair_routing_multidefect(
    project_root: Path, labels: Iterable[str], hubs: Iterable[int], context: HardwareContext,
    max_edits: int = 4, max_verifier_calls: int = 64,
    witness_check_limit: int = 4, alternatives_per_check: int = 6,
) -> MultiRoutingRepairResult:
    """Best-first CEGIS over local lowering choices implicated by exact witnesses.

    Search is lexicographic in number of changed checks and then cheap proxy C2.
    Only checks observed in exact failing-fault witnesses are expanded.  This
    naturally handles multiple simultaneous defects without being told their
    count or location.
    """
    root = Path(project_root)
    l0 = tuple(map(str, labels)); h0 = tuple(map(int, hubs))
    if len(l0) != 6 or len(h0) != 6: raise ValueError('expected six checks')
    if not _logical_ft(l0): raise ValueError('input must remain logically single-fault FT')
    options = _options_from_catalog(root)

    initial = bridge_native_risk(l0, h0, context, compute_c2=False)
    calls = 1
    rows0, checks0 = _fail_info(initial)
    trace = [{'step':0,'labels':list(l0),'hubs':list(h0),'c1':float(initial.c1),
              'failures':len(rows0),'failing_checks':list(checks0),'passed':_passed(initial)}]
    if _passed(initial):
        proxy = bridge_proxy_metrics(l0,h0,context)
        return MultiRoutingRepairResult(True,l0,h0,l0,h0,tuple(),calls,1,float(initial.c1),0.0,
            len(rows0),0,checks0,float(proxy.c2),trace)

    witness_checks = set(checks0)
    seen = {(l0,h0)}
    pq = []
    serial = 0

    def changed(ls, hs):
        return tuple(i for i in range(6) if ls[i] != l0[i] or hs[i] != h0[i])

    def proxy(ls, hs):
        return float(bridge_proxy_metrics(ls,hs,context).c2)

    # Expand the initial witness set.
    def enqueue_from(ls, hs, implicated):
        nonlocal serial
        expansions = []
        for ci in implicated[:max(1,int(witness_check_limit))]:
            local = []
            for nl, nh in options[ci]:
                if nl == ls[ci] and nh == hs[ci]:
                    continue
                cand_l = list(ls); cand_h = list(hs); cand_l[ci] = nl; cand_h[ci] = nh
                cand_l = tuple(cand_l); cand_h = tuple(cand_h)
                if (cand_l,cand_h) in seen or len(changed(cand_l,cand_h)) > int(max_edits):
                    continue
                if not _logical_ft(cand_l):
                    continue
                pc = proxy(cand_l,cand_h)
                local.append((pc,cand_l,cand_h))
            local.sort(key=lambda x:(x[0],x[1],x[2]))
            expansions.extend(local[:int(alternatives_per_check)])
        for pc, cand_l, cand_h in expansions:
            seen.add((cand_l,cand_h)); serial += 1
            ch = changed(cand_l,cand_h)
            heappush(pq,(len(ch),pc,serial,cand_l,cand_h))

    enqueue_from(l0,h0,checks0 or tuple(range(6)))
    last = initial; last_rows = rows0; last_checks = checks0
    while pq and calls < int(max_verifier_calls):
        _nedit,_pc,_s,ls,hs = heappop(pq)
        risk = bridge_native_risk(ls,hs,context,compute_c2=False); calls += 1
        rows, checks = _fail_info(risk); witness_checks.update(checks)
        trace.append({'step':len(trace),'labels':list(ls),'hubs':list(hs),'changed_checks':list(changed(ls,hs)),
                      'c1':float(risk.c1),'failures':len(rows),'failing_checks':list(checks),'passed':_passed(risk)})
        last,last_rows,last_checks = risk,rows,checks
        if _passed(risk):
            p = proxy(ls,hs)
            return MultiRoutingRepairResult(True,l0,h0,ls,hs,changed(ls,hs),calls,len(seen),
                float(initial.c1),float(risk.c1),len(rows0),len(rows),tuple(sorted(witness_checks)),p,trace)
        if len(changed(ls,hs)) < int(max_edits):
            enqueue_from(ls,hs,checks or tuple(range(6)))

    return MultiRoutingRepairResult(False,l0,h0,None,None,tuple(),calls,len(seen),float(initial.c1),
        float(last.c1) if last is not None else None,len(rows0),len(last_rows) if last_rows is not None else None,
        tuple(sorted(witness_checks)),None,trace)
