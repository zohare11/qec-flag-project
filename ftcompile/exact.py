"""Exact repairability oracle for bridge-path choices.

Question: for a fixed logical round, placement and hubs, does ANY choice of
physical path for every logical CNOT make the compiled round single-fault FT?
And if so, what is the smallest change from a given starting compilation?

Why this is tractable
---------------------
A bridge implements exactly CNOT(endpoints) (x) identity(interior) as a Clifford.
So an error that already exists propagates through a later bridge exactly as
through a direct CNOT, whatever its path.  Hence every single fault belongs to
one route and its signature (detectors, observables) depends only on that
route's own path.  (Incoming, preparation and measurement faults do not depend
on paths at all.)  A conflict is a pair of single events with equal detectors
and different observables, so the FT condition splits into
    - unary constraints:  route r may not use path a, and
    - binary constraints: route r with path a and route s with path b may not
      appear together,
which a CP-SAT solver handles exactly.  `validate_decomposition` checks the
claim against full-circuit Stim checks.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

import stim

from .compilers import Graph, bridge_cnots, compile_bridge
from .core import LogicalRound, Noise, check_program, to_stim

Sig = dict  # frozenset(detectors) -> set of frozenset(observables)


def signature_map(circuit: stim.Circuit) -> dict[frozenset, set[frozenset]]:
    out: dict[frozenset, set] = defaultdict(set)
    for inst in circuit.detector_error_model(decompose_errors=False).flattened():
        if inst.type != 'error':
            continue
        t = inst.targets_copy()
        out[frozenset(x.val for x in t if x.is_relative_detector_id())].add(
            frozenset(x.val for x in t if x.is_logical_observable_id()))
    return out


def _route_of(tag: str) -> str:
    return tag.split(':', 1)[1] if ':' in tag else ''


@dataclass
class PathModel:
    routes: list[str]
    candidates: dict[str, list[tuple[int, ...]]]
    sigs: dict[tuple[str, int], dict[frozenset, set[frozenset]]]
    fixed: dict[frozenset, set[frozenset]]
    unary: set[tuple[str, int]] = field(default_factory=set)
    binary: set[tuple[tuple[str, int], tuple[str, int]]] = field(default_factory=set)
    fixed_conflict: bool = False


def build_model(lr: LogicalRound, graph: Graph | None = None, extra_hops: int = 2,
                noise: Noise = Noise()) -> PathModel:
    graph = graph or Graph()
    base = compile_bridge(lr, graph, 'shortest')
    routes = list(base.meta['paths'])
    cands = {r: list(graph.paths(p[0], p[-1], extra_hops=extra_hops)) for r, p in base.meta['paths'].items()}
    fixed_tags = lambda tag: tag == 'incoming' or tag.startswith('prep:') or tag.startswith('meas:')
    fixed = signature_map(to_stim(base, noise, keep=fixed_tags))
    sigs = {}
    for r in routes:
        for i, path in enumerate(cands[r]):
            prog = compile_bridge(lr, graph, 'shortest', overrides={r: path})
            sigs[(r, i)] = signature_map(to_stim(prog, noise, keep=lambda tag, r=r: _route_of(tag) == r))
    m = PathModel(routes, cands, sigs, fixed)
    _derive_constraints(m)
    return m


def _derive_constraints(m: PathModel) -> None:
    by_key: dict[frozenset, list] = defaultdict(list)       # detectors -> [(owner, obs)]
    for d, obs in m.fixed.items():
        for o in obs:
            by_key[d].append(('fixed', o))
    by_key[frozenset()].append(('fixed', frozenset()))       # the no-error event
    for owner, sig in m.sigs.items():
        for d, obs in sig.items():
            for o in obs:
                by_key[d].append((owner, o))
    for d, entries in by_key.items():
        if len({o for _, o in entries}) < 2:
            continue
        for (a, oa), (b, ob) in combinations(entries, 2):
            if oa == ob:
                continue
            if a == 'fixed' and b == 'fixed':
                m.fixed_conflict = True
            elif a == 'fixed' or b == 'fixed':
                m.unary.add(b if a == 'fixed' else a)
            elif a == b:
                m.unary.add(a)
            elif a[0] != b[0]:
                m.binary.add((a, b) if a < b else (b, a))


def predicted_signatures(m: PathModel, choice: dict[str, int]) -> set[tuple[frozenset, frozenset]]:
    pairs = {(d, o) for d, obs in m.fixed.items() for o in obs}
    for r, i in choice.items():
        pairs |= {(d, o) for d, obs in m.sigs[(r, i)].items() for o in obs}
    return pairs


def validate_decomposition(m: PathModel, lr: LogicalRound, graph: Graph, choice: dict[str, int],
                           noise: Noise = Noise()) -> bool:
    """Union of per-route signatures == signatures of the full compiled circuit."""
    prog = compile_bridge(lr, graph, 'shortest', overrides={r: m.candidates[r][i] for r, i in choice.items()})
    full = {(d, o) for d, obs in signature_map(to_stim(prog, noise)).items() for o in obs}
    return full == predicted_signatures(m, choice)


@dataclass
class OracleResult:
    status: str                       # 'feasible' | 'infeasible'
    choice: dict[str, int] | None
    objective: float | None
    paths: dict[str, tuple[int, ...]] | None


def solve(m: PathModel, objective: str = 'none', start: dict[str, tuple[int, ...]] | None = None,
          routes: list[str] | None = None, time_limit: float = 60.0) -> OracleResult:
    """objective: 'none' (feasibility), 'edits' (fewest routes changed vs `start`),
    'cx' (fewest native CNOTs).  `routes` restricts the model to a subset
    (a relaxation, used to find small infeasible cores)."""
    from ortools.sat.python import cp_model
    routes = routes or m.routes
    rs = set(routes)
    if m.fixed_conflict:
        return OracleResult('infeasible', None, None, None)
    model = cp_model.CpModel()
    x = {(r, i): model.NewBoolVar(f'{r}_{i}') for r in routes for i in range(len(m.candidates[r]))}
    for r in routes:
        model.AddExactlyOne(x[(r, i)] for i in range(len(m.candidates[r])))
    for v in m.unary:
        if v[0] in rs:
            model.Add(x[v] == 0)
    for a, b in m.binary:
        if a[0] in rs and b[0] in rs:
            model.AddBoolOr([x[a].Not(), x[b].Not()])
    if objective == 'edits':
        terms = []
        for r in routes:
            same = [i for i, p in enumerate(m.candidates[r]) if p == start[r]]
            terms.append(1 - sum(x[(r, i)] for i in same))
        model.Minimize(sum(terms))
    elif objective == 'cx':
        model.Minimize(sum(len(bridge_cnots(m.candidates[r][i])) * x[(r, i)] for r in routes
                           for i in range(len(m.candidates[r]))))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 1
    st = solver.Solve(model)
    if st == cp_model.INFEASIBLE:
        return OracleResult('infeasible', None, None, None)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return OracleResult('unknown', None, None, None)
    choice = {r: next(i for i in range(len(m.candidates[r])) if solver.Value(x[(r, i)])) for r in routes}
    obj = solver.ObjectiveValue() if objective != 'none' else None
    if objective != 'none' and st != cp_model.OPTIMAL:
        obj = None
    return OracleResult('feasible', choice, obj, {r: m.candidates[r][i] for r, i in choice.items()})


def infeasible_core(m: PathModel) -> dict:
    """Smallest set of checks (1 or 2) whose routes alone already admit no FT paths."""
    checks = sorted({r.split('.')[0] for r in m.routes}, key=lambda c: int(c[1:]))
    routes_of = {c: [r for r in m.routes if r.split('.')[0] == c] for c in checks}
    empty = [r for r in m.routes if all((r, i) in m.unary for i in range(len(m.candidates[r])))]
    if empty:
        return {'kind': 'route_with_no_safe_path', 'routes': empty}
    for c in checks:
        if solve(m, routes=routes_of[c]).status == 'infeasible':
            return {'kind': 'single_check', 'checks': [c]}
    for a, b in combinations(checks, 2):
        if solve(m, routes=routes_of[a] + routes_of[b]).status == 'infeasible':
            return {'kind': 'check_pair', 'checks': [a, b]}
    return {'kind': 'larger', 'checks': checks}
