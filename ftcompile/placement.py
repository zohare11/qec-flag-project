"""Fast, exact evaluation of qubit placements.

For a placement (virtual qubit -> grid node) and a logical round, decide whether
some choice of bridge paths makes the compiled round single-fault FT -- the same
question as ftcompile.exact, but fast enough to try thousands of placements.

Why it can be fast
------------------
* A bridge is exactly CNOT(endpoints) (x) identity(interior), so any error that
  leaves a bridge propagates through the rest of the round exactly as in the
  unrouted logical circuit.  The signature (detectors, observables) of "Pauli P
  on virtual qubit v right after logical CNOT r" -- the *tail map* -- therefore
  depends on the logical round only, not on placement or paths.  It is read once
  per round from Stim.
* A fault inside a bridge leaves a residual Pauli on the path's qubits.  Which
  residuals can occur depends only on the path length (positions 0..d), so they
  are tabulated once per length.
* Signatures are linear: residual signature = XOR of tail-map entries of the
  virtual qubits sitting on the path (the free node contributes nothing).
Every other single fault (incoming, preparation, measurement, any single-qubit
error between routes) does not depend on placement or paths at all.

`validate` checks the predicted signature set against a full Stim circuit.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .compilers import Graph, bridge_cnots, compile_bridge
from .core import GRID_EDGES, N_VIRTUAL, LogicalRound, Noise, Op, PhysicalProgram, to_stim

FREE = -1


# ---------------------------------------------------------------- tables
def _dem_key(err) -> int:
    dets = obs = 0
    for t in err.dem_error_terms:
        d = t.dem_target
        if d.is_relative_detector_id():
            dets ^= 1 << d.val
        elif d.is_logical_observable_id():
            obs ^= 1 << d.val
    return (dets << 2) | obs


@dataclass
class RoundTables:
    routes: list[tuple[str, int, int]]       # (route tag, control virtual, target virtual), in order
    tail: dict[str, np.ndarray]              # route -> (N_VIRTUAL, 2) int64: signature of X / Z after the route
    fixed: np.ndarray                        # signatures that do not depend on placement or paths


def round_tables(lr: LogicalRound) -> RoundTables:
    ops = [Op(o.name, o.qubits, tag=o.tag, key=o.key, kind=o.kind) for o in lr.ops]
    ident = {q: q for q in range(7)}
    prog = PhysicalProgram(ops, N_VIRTUAL, ident, dict(ident), lr.syn_keys, lr.flag_keys)
    circ = to_stim(prog, Noise())
    routes = [(o.tag, o.qubits[0], o.qubits[1]) for o in lr.ops if o.name == 'CX']
    tail = {r: np.zeros((N_VIRTUAL, 2), dtype=np.int64) for r, _, _ in routes}
    seen_y = {}
    fixed = {0}
    for e in circ.explain_detector_error_model_errors(reduce_to_one_representative_error=False):
        key = _dem_key(e)
        for loc in e.circuit_error_locations:
            tag = loc.noise_tag
            prod = [(t.gate_target.qubit_value, t.gate_target.pauli_type) for t in loc.flipped_pauli_product]
            if tag == 'incoming' or tag.startswith('prep:') or tag.startswith('meas:'):
                fixed.add(key)
            elif len(prod) == 1:                      # single-qubit error right after a logical CNOT
                route = tag.split(':', 1)[1]
                q, p = prod[0]
                if p == 'X':
                    tail[route][q, 0] = key
                elif p == 'Z':
                    tail[route][q, 1] = key
                else:
                    seen_y[(route, q)] = key
    for (route, q), key in seen_y.items():
        assert tail[route][q, 0] ^ tail[route][q, 1] == key, 'tail map is not linear?'
    for r, _, _ in routes:              # any single-qubit error after any route is always possible
        t = tail[r]
        fixed.update(int(x) for x in np.concatenate([t[:, 0], t[:, 1], t[:, 0] ^ t[:, 1]]))
    return RoundTables(routes, tail, np.array(sorted(fixed), dtype=np.int64))


@lru_cache(maxsize=None)
def residual_table(d: int) -> tuple[np.ndarray, np.ndarray]:
    """All residual Paulis left on path positions 0..d by one fault inside a d-hop
    bridge (a two-qubit Pauli after any of its CNOTs, or an idle X/Y/Z on another
    path qubit).  Returns boolean arrays (n, d+1) of X and Z parts."""
    cxs = bridge_cnots(tuple(range(d + 1)))
    out = set()
    for k, (c, t) in enumerate(cxs):
        faults = []
        for pa in range(4):
            for pb in range(4):
                if pa or pb:
                    faults.append({c: pa, t: pb})
        for j in range(d + 1):
            if j not in (c, t):
                faults += [{j: 1}, {j: 2}, {j: 3}]
        for f in faults:
            x = [0] * (d + 1); z = [0] * (d + 1)
            for q, p in f.items():
                x[q] = p & 1; z[q] = (p >> 1) & 1
            for c2, t2 in cxs[k + 1:]:
                x[t2] ^= x[c2]; z[c2] ^= z[t2]
            if any(x) or any(z):
                out.add((tuple(x), tuple(z)))
    xs = np.array([o[0] for o in sorted(out)], dtype=bool)
    zs = np.array([o[1] for o in sorted(out)], dtype=bool)
    return xs, zs


_BASE = Graph()


@lru_cache(maxsize=None)
def candidate_paths(s: int, t: int, extra_hops: int = 2) -> tuple[tuple[int, ...], ...]:
    return _BASE.paths(s, t, extra_hops=extra_hops)


# ---------------------------------------------------------------- per-placement model
@dataclass
class PlacementModel:
    routes: list[str]
    candidates: dict[str, tuple[tuple[int, ...], ...]]
    sigs: dict[tuple[str, int], np.ndarray]
    allowed: dict[str, list[int]]
    fixed_obs: dict[int, int]


def path_signatures(tables: RoundTables, route: str, path: tuple[int, ...], inv: dict[int, int]) -> np.ndarray:
    xs, zs = residual_table(len(path) - 1)
    t = tables.tail[route]
    rows = np.zeros((len(path), 2), dtype=np.int64)
    for i, node in enumerate(path):
        v = inv.get(node, FREE)
        if v != FREE:
            rows[i] = t[v]
    contrib = np.where(xs, rows[None, :, 0], 0) ^ np.where(zs, rows[None, :, 1], 0)
    return np.unique(np.bitwise_xor.reduce(contrib, axis=1))


def build(tables: RoundTables, placement: dict[int, int], extra_hops: int = 2) -> PlacementModel:
    inv = {n: v for v, n in placement.items()}
    fixed_obs = {}
    for k in tables.fixed:
        fixed_obs[int(k) >> 2] = int(k) & 3        # consistent by construction (unrouted round is FT)
    routes, cands, sigs, allowed = [], {}, {}, {}
    for r, cv, tv in tables.routes:
        routes.append(r)
        cands[r] = candidate_paths(placement[cv], placement[tv], extra_hops)
        allowed[r] = []
        for i, p in enumerate(cands[r]):
            s = path_signatures(tables, r, p, inv)
            sigs[(r, i)] = s
            dets = s >> 2; obs = s & 3
            if len(np.unique(dets)) < len(s):
                continue                               # two of its own faults collide
            if any(fixed_obs.get(int(d), o) != o for d, o in zip(dets, obs)):
                continue                               # collides with a placement-independent fault
            allowed[r].append(i)
    return PlacementModel(routes, cands, sigs, allowed, fixed_obs)


def binary_nogoods(m: PlacementModel) -> set:
    by_dets: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for r in m.routes:
        for i in m.allowed[r]:
            for s in m.sigs[(r, i)]:
                d = int(s) >> 2
                if d not in m.fixed_obs:
                    by_dets[d][int(s) & 3].append((r, i))
    bad = set()
    for groups in by_dets.values():
        if len(groups) < 2:
            continue
        keys = list(groups)
        for a in range(len(keys)):
            for b in range(a + 1, len(keys)):
                for u in groups[keys[a]]:
                    for w in groups[keys[b]]:
                        if u[0] != w[0]:
                            bad.add((u, w) if u < w else (w, u))
    return bad


def solve(m: PlacementModel, objective: str = 'none', time_limit: float = 30.0):
    """Returns (status, {route: path} or None, objective value or None)."""
    if any(not m.allowed[r] for r in m.routes):
        return 'infeasible', None, None
    bad = binary_nogoods(m)
    if objective == 'none':                       # cheap first try: greedy choice
        choice = {r: m.allowed[r][0] for r in m.routes}
        if not any(choice[u[0]] == u[1] and choice[w[0]] == w[1] for u, w in bad):
            return 'feasible', {r: m.candidates[r][i] for r, i in choice.items()}, None
    from ortools.sat.python import cp_model
    model = cp_model.CpModel()
    x = {(r, i): model.NewBoolVar(f'{r}_{i}') for r in m.routes for i in m.allowed[r]}
    for r in m.routes:
        model.AddExactlyOne(x[(r, i)] for i in m.allowed[r])
    for u, w in bad:
        model.AddBoolOr([x[u].Not(), x[w].Not()])
    if objective == 'cx':
        model.Minimize(sum(len(bridge_cnots(m.candidates[r][i])) * x[(r, i)] for r, i in x))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 1
    st = solver.Solve(model)
    if st == cp_model.INFEASIBLE:
        return 'infeasible', None, None
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return 'unknown', None, None
    paths = {r: next(m.candidates[r][i] for i in m.allowed[r] if solver.Value(x[(r, i)])) for r in m.routes}
    return 'feasible', paths, (solver.ObjectiveValue() if objective != 'none' and st == cp_model.OPTIMAL else None)


# ---------------------------------------------------------------- checks
def predicted_signatures(tables: RoundTables, placement: dict[int, int], paths: dict[str, tuple[int, ...]]) -> set:
    inv = {n: v for v, n in placement.items()}
    out = {int(k) for k in tables.fixed} - {0}
    for r, p in paths.items():
        out |= {int(s) for s in path_signatures(tables, r, p, inv)}
    out.discard(0)
    return out


def validate(lr: LogicalRound, tables: RoundTables, placement: dict[int, int], paths: dict[str, tuple[int, ...]]) -> bool:
    """Predicted signature set == signature set of the full compiled Stim circuit."""
    g = Graph(GRID_EDGES, placement)
    circ = to_stim(compile_bridge(lr, g, 'shortest', overrides=paths), Noise())
    full = set()
    for inst in circ.detector_error_model(decompose_errors=False).flattened():
        if inst.type != 'error':
            continue
        dets = obs = 0
        for t in inst.targets_copy():
            if t.is_relative_detector_id():
                dets ^= 1 << t.val
            elif t.is_logical_observable_id():
                obs ^= 1 << t.val
        full.add((dets << 2) | obs)
    return full == predicted_signatures(tables, placement, paths)
