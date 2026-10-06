"""Richer operation-localized routing/lowering CEGIS for FT repair v3.

Compared with v2, the repair language now includes:
  * per-logical-interaction physical path changes,
  * hub changes,
  * local flag/template/CNOT-order changes from the 96-action table.

The verifier localizes failures at native gate/route granularity.  Search remains
lexicographic: exact FT is mandatory, then minimize compiler edits, then a cheap
physical proxy.  Multiple safe repairs can be enumerated for downstream
cross-layer scheduling.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from heapq import heappush, heappop
from pathlib import Path
from typing import Iterable
import numpy as np

from qecflag.phase5_actions import ensure_hardware_action_table
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase5_hardware import HardwareContext

from .model import (
    RoutingState, logical_ft, physical_path_candidates, route_proxy, changed_checks,
    edit_atoms, passed_native_risk,
)
from .cache import RoutingVerifierCache
from .localization import routing_failure_cores, implicated_routes, implicated_checks


@dataclass
class RoutingRepairV3Result:
    success: bool
    start_state: RoutingState
    repaired_state: RoutingState | None
    verifier_calls: int
    cache_hits: int
    states_seen: int
    initial_c1: float
    final_c1: float | None
    initial_failures: int
    final_failures: int | None
    changed_checks: tuple[int, ...]
    changed_paths: tuple[tuple[int, int], ...]
    edit_count: int
    witness_checks_seen: tuple[int, ...]
    witness_routes_seen: tuple[tuple[int, int], ...]
    top_failure_cores: list[dict]
    final_proxy: float | None
    solutions_found: int
    trace: list[dict]

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _changed_paths(base: RoutingState, state: RoutingState) -> tuple[tuple[int, int], ...]:
    a = base.override_map; b = state.override_map
    return tuple(sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k)))


def _state_key(base: RoutingState, state: RoutingState, context: HardwareContext):
    atoms = edit_atoms(base, state)
    return (len(atoms), route_proxy(state, context), state.signature())


def _check_options(root: Path, state: RoutingState, check: int, context: HardwareContext,
                   limit: int = 12) -> tuple[RoutingState, ...]:
    """Rank local template/hub replacements, preferring certified-catalog choices.

    The certified Phase-7 catalog is a high-value proposal source: it contains
    local compiler choices known to participate in at least one safe physical
    round.  V3 searches those first, then supplements from the full 96-action
    table only when needed.  Exact verification still decides safety in the
    *current* round/context.
    """
    table = ensure_hardware_action_table(root)
    cat = ensure_catalog(root, progress=False)
    catalog_pairs=[];seen=set()
    for e in cat.entries:
        pair=(str(e['labels'][check]),int(e['hubs'][check]))
        if pair not in seen:
            seen.add(pair);catalog_pairs.append(pair)
    all_pairs=list(catalog_pairs)
    if len(all_pairs)<int(limit):
        for action in range(table.n_actions):
            pair=(str(table.template_label(action)),int(table.hub(action)))
            if pair not in seen:
                seen.add(pair);all_pairs.append(pair)
    candidates=[]
    catset=set(catalog_pairs)
    for label,hub in all_pairs:
        if (label,hub)==(state.labels[check],state.hubs[check]):continue
        cand=state.with_check(check,label,hub,clear_paths=True)
        if not logical_ft(cand.labels):continue
        try:p=route_proxy(cand,context)
        except Exception:continue
        candidates.append((0 if (label,hub) in catset else 1,p,hub,label,cand))
    candidates.sort(key=lambda x:(x[0],x[1],x[2],x[3]))
    return tuple(x[4] for x in candidates[:max(1,int(limit))])


def _path_options(state: RoutingState, check: int, route: int, context: HardwareContext,
                  limit: int = 6) -> tuple[RoutingState, ...]:
    try:
        paths = physical_path_candidates(state, check, route, context=context,
                                         max_paths=max(2, int(limit) + 1), include_data_interiors=True)
    except Exception:
        return tuple()
    current = state.override_map.get((check, route))
    # Determine actual default by first returned path only if no override; the
    # candidate helper always places the current path first.
    actual = paths[0] if current is None else current
    out = []
    for p in paths:
        if p == actual:
            continue
        cand = state.with_path(check, route, p)
        out.append((route_proxy(cand, context), p, cand))
    out.sort(key=lambda x: (x[0], x[1]))
    return tuple(x[2] for x in out[:max(1, int(limit))])


def _minimize_safe_state(base: RoutingState, safe: RoutingState, context: HardwareContext,
                         cache: RoutingVerifierCache, budget: int = 24) -> RoutingState:
    """Deletion-minimize a certified repair using exact re-verification."""
    current = safe
    attempts = 0
    changed = True
    while changed and attempts < int(budget):
        changed = False
        # Prefer removing path edits first because they are the most local.
        for key in list(_changed_paths(base, current)):
            if attempts >= int(budget): break
            # A base path belongs to the base check's endpoints.  If the check
            # template/hub itself has changed, blindly restoring that path can
            # attach it to incompatible endpoints; defer to whole-check reversion.
            if (current.labels[key[0]], current.hubs[key[0]]) != (base.labels[key[0]], base.hubs[key[0]]):
                continue
            trial = current.with_path(key[0], key[1], base.override_map.get(key))
            if not logical_ft(trial.labels): continue
            r = cache.evaluate(trial, context, compute_c2=False); attempts += 1
            if passed_native_risk(r):
                current = trial; changed = True; break
        if changed:
            continue
        for c in changed_checks(base, current):
            if attempts >= int(budget): break
            if (current.labels[c], current.hubs[c]) == (base.labels[c], base.hubs[c]):
                continue
            labels = list(current.labels); hubs = list(current.hubs)
            labels[c] = base.labels[c]; hubs[c] = base.hubs[c]
            # Reverting the logical check also removes path edits attached to it.
            m = {k: v for k, v in current.override_map.items() if k[0] != c}
            for k, v in base.override_map.items():
                if k[0] == c: m[k] = v
            trial = RoutingState.from_parts(labels, hubs, m)
            if not logical_ft(trial.labels): continue
            r = cache.evaluate(trial, context, compute_c2=False); attempts += 1
            if passed_native_risk(r):
                current = trial; changed = True; break
    return current


def enumerate_safe_routing_repairs(
    project_root: Path, labels: Iterable[str] | RoutingState, hubs: Iterable[int] | None,
    context: HardwareContext, *, max_edits: int = 5, max_verifier_calls: int = 72,
    witness_route_limit: int = 8, witness_check_limit: int = 5,
    path_alternatives_per_route: int = 5, check_alternatives_per_check: int = 10,
    max_solutions: int = 4, cache: RoutingVerifierCache | None = None,
    minimize: bool = True,
) -> tuple[list[RoutingState], dict]:
    """Return several distinct certified repairs for downstream joint selection."""
    root = Path(project_root)
    if isinstance(labels, RoutingState):
        base = labels
    else:
        if hubs is None: raise ValueError('hubs are required with raw labels')
        base = RoutingState.from_parts(labels, hubs)
    if not logical_ft(base.labels):
        raise ValueError('input compiler state must preserve logical FT')
    cache = RoutingVerifierCache() if cache is None else cache
    start_calls = cache.stats.misses; start_hits = cache.stats.hits
    initial = cache.evaluate(base, context, compute_c2=False)
    cores0 = routing_failure_cores(initial)
    trace = [{
        'step': 0, 'edit_count': 0, 'c1': float(initial.c1),
        'failures': int(initial.decoder.single_fault_failures),
        'implicated_checks': list(implicated_checks(initial)),
        'implicated_routes': [list(x) for x in implicated_routes(initial)],
        'passed': passed_native_risk(initial),
    }]
    if passed_native_risk(initial):
        return [base], {'initial': initial, 'trace': trace, 'states_seen': 1,
                        'witness_checks': set(), 'witness_routes': set(), 'cores0': cores0,
                        'calls': cache.stats.misses-start_calls, 'hits': cache.stats.hits-start_hits}

    seen = {base.signature()}; pq = []; serial = 0
    witness_checks = set(implicated_checks(initial)); witness_routes = set(implicated_routes(initial))
    solutions: list[RoutingState] = []

    def push(cand: RoutingState, reason: str):
        nonlocal serial
        sig = cand.signature()
        if sig in seen: return
        atoms = edit_atoms(base, cand)
        if len(atoms) > int(max_edits) or not logical_ft(cand.labels): return
        seen.add(sig); serial += 1
        try: pr = route_proxy(cand, context)
        except Exception: return
        rr=0 if reason.startswith('check:') else 1
        heappush(pq, (len(atoms), rr, pr, serial, reason, cand))

    def expand(state: RoutingState, risk):
        routes = implicated_routes(risk, limit=witness_route_limit)
        checks = implicated_checks(risk, limit=witness_check_limit)
        if not routes and not checks:
            checks = tuple(range(6))
        for c, r in routes:
            for cand in _path_options(state, c, r, context, path_alternatives_per_route):
                push(cand, f'path:{c}:{r}')
        for c in checks:
            for cand in _check_options(root, state, c, context, check_alternatives_per_check):
                push(cand, f'check:{c}')

    expand(base, initial)
    while pq and cache.stats.misses - start_calls < int(max_verifier_calls):
        _nedit, _rr, _proxy, _s, reason, state = heappop(pq)
        risk = cache.evaluate(state, context, compute_c2=False)
        routes = implicated_routes(risk, limit=witness_route_limit)
        checks = implicated_checks(risk, limit=witness_check_limit)
        witness_routes.update(routes); witness_checks.update(checks)
        trace.append({
            'step': len(trace), 'reason': reason, 'edit_count': len(edit_atoms(base,state)),
            'changed_checks': list(changed_checks(base,state)),
            'changed_paths': [list(x) for x in _changed_paths(base,state)],
            'c1': float(risk.c1), 'failures': int(risk.decoder.single_fault_failures),
            'implicated_checks': list(checks), 'implicated_routes': [list(x) for x in routes],
            'passed': passed_native_risk(risk),
        })
        if passed_native_risk(risk):
            final = _minimize_safe_state(base, state, context, cache,
                                         budget=min(24, max(0, int(max_verifier_calls)-(cache.stats.misses-start_calls)))) if minimize else state
            if final.signature() not in {x.signature() for x in solutions}:
                solutions.append(final)
                solutions.sort(key=lambda s: _state_key(base,s,context))
                solutions = solutions[:int(max_solutions)]
            # Continue to collect alternatives if budget allows.  Once we have
            # max_solutions, states with strictly more edits than the worst safe
            # repair cannot improve lexicographic minimality.
            if len(solutions) >= int(max_solutions):
                worst_edits = len(edit_atoms(base, solutions[-1]))
                if not pq or pq[0][0] > worst_edits:
                    break
            continue
        if len(edit_atoms(base,state)) < int(max_edits):
            expand(state, risk)

    meta = {
        'initial': initial, 'trace': trace, 'states_seen': len(seen),
        'witness_checks': witness_checks, 'witness_routes': witness_routes, 'cores0': cores0,
        'calls': cache.stats.misses-start_calls, 'hits': cache.stats.hits-start_hits,
    }
    solutions.sort(key=lambda s: _state_key(base,s,context))
    return solutions, meta


def repair_routing_v3(
    project_root: Path, labels: Iterable[str] | RoutingState, hubs: Iterable[int] | None,
    context: HardwareContext, **kwargs,
) -> RoutingRepairV3Result:
    base = labels if isinstance(labels, RoutingState) else RoutingState.from_parts(labels, hubs)
    cache = kwargs.pop('cache', None) or RoutingVerifierCache()
    solutions, meta = enumerate_safe_routing_repairs(project_root, base, None, context, cache=cache, **kwargs)
    initial = meta['initial']
    repaired = solutions[0] if solutions else None
    final_risk = cache.evaluate(repaired, context, compute_c2=False) if repaired is not None else None
    changed = changed_checks(base, repaired) if repaired is not None else tuple()
    changed_paths = _changed_paths(base, repaired) if repaired is not None else tuple()
    return RoutingRepairV3Result(
        success=bool(repaired is not None), start_state=base, repaired_state=repaired,
        verifier_calls=int(meta['calls']), cache_hits=int(meta['hits']), states_seen=int(meta['states_seen']),
        initial_c1=float(initial.c1), final_c1=float(final_risk.c1) if final_risk is not None else None,
        initial_failures=int(initial.decoder.single_fault_failures),
        final_failures=int(final_risk.decoder.single_fault_failures) if final_risk is not None else None,
        changed_checks=changed, changed_paths=changed_paths,
        edit_count=len(edit_atoms(base,repaired)) if repaired is not None else 0,
        witness_checks_seen=tuple(sorted(meta['witness_checks'])),
        witness_routes_seen=tuple(sorted(meta['witness_routes'])),
        top_failure_cores=[x.to_dict() for x in meta['cores0'][:20]],
        final_proxy=route_proxy(repaired,context) if repaired is not None else None,
        solutions_found=len(solutions), trace=meta['trace'],
    )
