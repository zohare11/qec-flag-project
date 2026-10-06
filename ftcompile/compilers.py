"""Compilers that lower a logical round onto a coupling graph.

compile_bridge  -- every logical CX becomes a nearest-neighbour "bridge" CNOT
                   sequence along a chosen path; qubits never move.  The path
                   policy is the compiler decision that repair can change.
compile_qiskit  -- Qiskit transpile(): SABRE routing (SWAPs move qubits) and/or its
                   optimization passes.
compile_unrouted -- the logical round as written (all-to-all reference).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Callable

import networkx as nx

from .core import (GRID_EDGES, GRID_PLACEMENT, N_DATA, N_VIRTUAL, LogicalRound, Op,
                   PhysicalProgram)


def bridge_cnots(path: tuple[int, ...]) -> list[tuple[int, int]]:
    """CNOT(path[0] -> path[-1]) with nearest-neighbour CNOTs, all interior qubits
    restored exactly.  4d-4 CNOTs for d >= 2 hops (1 for d = 1)."""
    d = len(path) - 1
    if d < 1:
        raise ValueError('path needs two distinct endpoints')
    if d == 1:
        return [(path[0], path[1])]
    sweep = [(path[i], path[i + 1]) for i in range(d)] + [(path[i], path[i + 1]) for i in range(d - 2, 0, -1)]
    return sweep + sweep


class Graph:
    def __init__(self, edges=GRID_EDGES, placement=GRID_PLACEMENT):
        self.edges = sorted(tuple(sorted(e)) for e in edges)
        self.g = nx.Graph(self.edges)
        self.placement = dict(placement)
        self.n_nodes = max(max(e) for e in self.edges) + 1
        self.data_nodes = frozenset(self.placement[q] for q in range(N_DATA))

    @lru_cache(maxsize=None)
    def paths(self, s: int, t: int, extra_hops: int = 2, max_hops: int | None = None) -> tuple[tuple[int, ...], ...]:
        """All simple paths up to `extra_hops` longer than the shortest, sorted by
        (hops, data qubits in the interior, node sequence)."""
        dist = nx.shortest_path_length(self.g, s, t)
        cutoff = dist + extra_hops if max_hops is None else min(dist + extra_hops, max_hops)
        ps = [tuple(p) for p in nx.all_simple_paths(self.g, s, t, cutoff=cutoff)]
        return tuple(sorted(ps, key=lambda p: (len(p), self.data_interior(p), p)))

    def data_interior(self, p) -> int:
        return sum(1 for x in p[1:-1] if x in self.data_nodes)


def policy_shortest(graph: Graph, s: int, t: int) -> tuple[int, ...]:
    """Ordinary, FT-unaware choice: fewest hops, ties broken by node sequence."""
    return min(graph.paths(s, t), key=lambda p: (len(p), p))


def policy_ancilla_first(graph: Graph, s: int, t: int) -> tuple[int, ...]:
    """The project's Phase-7 rule: paths of <= 3 hops, prefer interiors with no
    data qubit, then fewest hops, then node sequence."""
    ps = graph.paths(s, t, extra_hops=2, max_hops=3)
    clean = [p for p in ps if graph.data_interior(p) == 0]
    return min(clean or ps, key=lambda p: (len(p), p))


POLICIES: dict[str, Callable] = {'shortest': policy_shortest, 'ancilla_first': policy_ancilla_first}


def compile_bridge(lr: LogicalRound, graph: Graph | None = None, policy: str = 'shortest',
                   overrides: dict[str, tuple[int, ...]] | None = None) -> PhysicalProgram:
    graph = graph or Graph()
    overrides = overrides or {}
    pick = POLICIES[policy]
    ops: list[Op] = []
    paths: dict[str, tuple[int, ...]] = {}
    for o in lr.ops:
        nodes = tuple(graph.placement[q] for q in o.qubits)
        if o.name != 'CX':
            ops.append(Op(o.name, nodes, tag=o.tag, key=o.key))
            continue
        path = tuple(overrides.get(o.tag) or pick(graph, *nodes))
        if path[0] != nodes[0] or path[-1] != nodes[1]:
            raise ValueError(f'path {path} does not join {nodes}')
        paths[o.tag] = path
        kind = 'direct' if len(path) == 2 else 'bridge'
        for a, b in bridge_cnots(path):
            if tuple(sorted((a, b))) not in graph.g.edges:
                raise ValueError(f'non-edge {a}-{b}')
            ops.append(Op('CX', (a, b), tag=o.tag, kind=kind))
    pos = {q: graph.placement[q] for q in range(N_DATA)}
    return PhysicalProgram(ops, graph.n_nodes, pos, dict(pos), lr.syn_keys, lr.flag_keys,
                           meta={'compiler': f'bridge/{policy}', 'paths': paths, 'overrides': dict(overrides)})


def compile_qiskit(lr: LogicalRound, graph: Graph | None = None, routed: bool = True, seed: int = 7,
                   optimization_level: int | None = 1) -> PhysicalProgram:
    """Compile with Qiskit's transpile().  routed=True: SABRE routing on the
    coupling graph with the fixed initial placement (SWAPs kept explicit, then
    expanded to 3 CNOTs).  routed=False: no connectivity limits, only Qiskit's
    optimization passes.  optimization_level=None means Qiskit's default."""
    from qiskit import QuantumCircuit, transpile
    from qiskit.circuit.library import CXGate
    from qiskit.transpiler import CouplingMap

    graph = graph or Graph()
    keys = [o.key for o in lr.ops if o.key]
    kidx = {k: i for i, k in enumerate(keys)}
    qc = QuantumCircuit(N_VIRTUAL, len(keys))
    for o in lr.ops:
        q = o.qubits
        if o.name == 'R':
            qc.reset(q[0])
        elif o.name == 'RX':
            qc.reset(q[0]); qc.h(q[0])
        elif o.name == 'CX':
            qc.append(CXGate(label=o.tag), [q[0], q[1]])
        elif o.name == 'M':
            qc.measure(q[0], kidx[o.key])
        elif o.name == 'MX':
            qc.h(q[0]); qc.measure(q[0], kidx[o.key])
    kw = dict(seed_transpiler=seed)
    if optimization_level is not None:
        kw['optimization_level'] = optimization_level
    if routed:
        cmap = CouplingMap([list(e) for e in graph.edges] + [[b, a] for a, b in graph.edges])
        tc = transpile(qc, coupling_map=cmap, initial_layout=[graph.placement[v] for v in range(N_VIRTUAL)],
                       basis_gates=['cx', 'h', 'swap'], routing_method='sabre', **kw)
        node = lambda i: i                                   # already physical
    else:
        tc = transpile(qc, basis_gates=['cx', 'h'], **kw)
        node = lambda i: graph.placement[i]                  # virtual -> placed node
    ops: list[Op] = []
    n_swaps = 0
    for inst in tc.data:
        name = inst.operation.name
        qs = tuple(node(tc.find_bit(x).index) for x in inst.qubits)
        if name == 'reset':
            ops.append(Op('R', qs, tag='prep'))
        elif name == 'h':
            ops.append(Op('H', qs))
        elif name == 'cx':
            ops.append(Op('CX', qs, tag=inst.operation.label or 'unlabeled', kind='direct'))
        elif name == 'swap':
            a, b = qs
            for c, t in ((a, b), (b, a), (a, b)):
                ops.append(Op('CX', (c, t), tag=f'swap{n_swaps}', kind='swap'))
            n_swaps += 1
        elif name == 'measure':
            ops.append(Op('M', qs, tag='meas', key=keys[tc.find_bit(inst.clbits[0]).index]))
        elif name in ('barrier', 'delay'):
            continue
        else:
            raise ValueError(f'unexpected gate {name} after transpilation')
    start = {q: graph.placement[q] for q in range(N_DATA)}
    if routed:
        final = tc.layout.final_index_layout()
        end = {q: int(final[q]) for q in range(N_DATA)}
    else:
        end = dict(start)
    n_logical = sum(1 for o in ops if o.name == 'CX' and o.kind == 'direct')
    level = 'default' if optimization_level is None else optimization_level
    return PhysicalProgram(ops, graph.n_nodes, start, end, lr.syn_keys, lr.flag_keys,
                           meta={'compiler': f'qiskit/{"sabre" if routed else "no-routing"}/opt{level}/seed{seed}',
                                 'swaps': n_swaps, 'logical_cx_kept': n_logical})


def compile_sabre(lr: LogicalRound, graph: Graph | None = None, seed: int = 7,
                  optimization_level: int | None = 1) -> PhysicalProgram:
    return compile_qiskit(lr, graph, routed=True, seed=seed, optimization_level=optimization_level)


def compile_unrouted(lr: LogicalRound, graph: Graph | None = None) -> PhysicalProgram:
    """Reference: the logical round exactly as written, ignoring connectivity."""
    graph = graph or Graph()
    ops = [Op(o.name, tuple(graph.placement[q] for q in o.qubits), tag=o.tag, key=o.key, kind=o.kind)
           for o in lr.ops]
    pos = {q: graph.placement[q] for q in range(N_DATA)}
    return PhysicalProgram(ops, graph.n_nodes, pos, dict(pos), lr.syn_keys, lr.flag_keys,
                           meta={'compiler': 'unrouted (all-to-all)'})
