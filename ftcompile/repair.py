"""Witness-guided repair of bridge-routing decisions.

Loop:  check -> witnesses -> routes whose gates appear in them (suspects)
       -> try cheaper-first alternative paths for suspects -> keep the change that
       most lowers the first-order failure probability (C1*p) -> repeat until the single-fault check passes
       (or no change helps / the verifier budget runs out) -> undo any changes
       that turn out to be unnecessary.

Only the physical path of each logical CNOT is changed; the logical circuit,
qubit placement and check order stay fixed.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .compilers import Graph, bridge_cnots, compile_bridge
from .core import FTResult, LogicalRound, Noise, PhysicalProgram, check_program


def suspect_routes(res: FTResult) -> list[str]:
    """Routes whose own CNOT faults appear in conflicting signatures, most frequent first."""
    cnt: Counter = Counter()
    for w in res.witnesses:
        for ev in w.events:
            for tag, _pauli in ev['locations']:
                kind, _, route = tag.partition(':')
                if kind in ('bridge', 'direct') and route:
                    cnt[route] += 1
    return [r for r, _ in cnt.most_common()]


def route_cost(paths: dict[str, tuple[int, ...]]) -> int:
    return sum(len(bridge_cnots(p)) for p in paths.values())


@dataclass
class RepairResult:
    success: bool
    verifier_calls: int
    start_conflicts: int
    final_conflicts: int
    start_cx: int
    final_cx: int
    changed_routes: dict[str, tuple[tuple[int, ...], tuple[int, ...]]]   # route -> (old path, new path)
    first_suspects: list[str]
    program: PhysicalProgram
    history: list[dict] = field(default_factory=list)


def repair_paths(lr: LogicalRound, graph: Graph | None = None, start_policy: str = 'shortest',
                 max_calls: int = 120, extra_hops: int = 2, max_suspects: int = 6,
                 alts_per_route: int = 6, noise: Noise = Noise()) -> RepairResult:
    graph = graph or Graph()
    start = compile_bridge(lr, graph, start_policy)
    base_paths = dict(start.meta['paths'])
    paths = dict(base_paths)

    def build(ps):
        return compile_bridge(lr, graph, start_policy, overrides=ps)

    res = check_program(start, noise)
    calls = 1
    start_conflicts = res.n_conflicts
    first_suspects = suspect_routes(res)
    history = []
    while not res.passed and calls < max_calls:
        # Most-implicated route first; take the best of its alternatives as soon
        # as one lowers the first-order failure (first-improvement hill climbing).
        best = None
        for r in suspect_routes(res)[:max_suspects]:
            s, t = paths[r][0], paths[r][-1]
            route_best = None
            for alt in graph.paths(s, t, extra_hops=extra_hops)[:alts_per_route + 1]:
                if alt == paths[r] or calls >= max_calls:
                    continue
                trial = {**paths, r: alt}
                tr = check_program(build(trial), noise, explain=False); calls += 1
                key = (tr.first_order_failure, route_cost(trial))
                if route_best is None or key < route_best[0]:
                    route_best = (key, r, alt)
                if tr.passed:
                    break
            if route_best is not None and route_best[0][0] < res.first_order_failure:
                best = route_best
                break
        if best is None:
            break   # stuck: no single path change lowers the first-order failure
        (_, cost), r, alt = best
        history.append({'route': r, 'old': paths[r], 'new': alt, 'f1_before': res.first_order_failure,
                        'f1_after': best[0][0], 'cx_after': cost})
        paths[r] = alt
        res = check_program(build(paths), noise); calls += 1
    if res.passed:   # drop changes that were not needed
        for r in [r for r in paths if paths[r] != base_paths[r]]:
            trial = {**paths, r: base_paths[r]}
            tr = check_program(build(trial), noise, explain=False); calls += 1
            if tr.passed:
                paths = trial
    final = build(paths)
    final_res = check_program(final, noise, explain=False)
    changed = {r: (base_paths[r], paths[r]) for r in paths if paths[r] != base_paths[r]}
    return RepairResult(final_res.passed, calls, start_conflicts, final_res.n_conflicts,
                        start.n_cx, final.n_cx, changed, first_suspects, final, history)
