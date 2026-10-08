"""Exact synthesis of a parallel flag block with CP-SAT.

Kept for comparison: the SAT encoding in synth_sat.py solves the same model much faster.
`to_published` turns a result from either into a full round.

One block measures the three Z checks at once (the X block is the Hadamard dual).  Given
the ancilla qubits (one of them the flag/root) and the nodes that may hold data, the model
chooses, for each of T time slots, one CNOT (or nothing):

* ancilla -> ancilla along a coupler, or data -> ancilla along a coupler;
* which candidate nodes hold the 7 data qubits.

Linear part (exact): every ancilla's Z value is tracked as a GF(2) vector over (root bit,
data nodes).  At the end the root bit sits on the root only, three ancillas read out rows
whose columns -- one 3-bit column per data node -- are the 7 distinct non-zero vectors (any
such assignment is a valid labelling of the Steane code), and any further ancillas read 0.

Fault-tolerance part (exact for these faults): a Z fault on an ancilla after any slot
spreads to a fixed set of data qubits and reaches the root (flag) or not; the same for Z
pairs left by a faulty CNOT (two ancillas, or a data qubit plus an ancilla).  Unflagged, the
data error must be decodable from its syndrome alone; flagged, errors with the same syndrome
must share a logical class.  Their spreading is tracked backwards with the same GF(2)
algebra.  Everything else (X faults, data faults, the X block, idle noise everywhere) is left
to the full Stim check of the finished round, which callers must run.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import networkx as nx


@dataclass
class Synthesis:
    status: str
    slots: list            # [(control node, target node), ...] in time order
    data: dict             # data node -> 3-bit column (bit j: in read-out j)
    readouts: tuple        # ancilla nodes reading rows 0, 1, 2
    root: int
    anc: tuple
    wall: float

    @property
    def n_cx(self):
        return len(self.slots)


def synthesize(G: nx.Graph, anc, root, T: int, readouts=None, candidates=None, time_limit=120.0,
               workers=2, pairs=True, exact_T=False, hint=None):
    from ortools.sat.python import cp_model
    anc = tuple(anc)
    A = set(anc)
    nonroot = [a for a in anc if a != root]
    readouts = tuple(readouts) if readouts else tuple(nonroot[:3])
    zeros = [a for a in nonroot if a not in readouts]
    cand = tuple(sorted(candidates if candidates is not None else
                        {n for a in anc for n in G[a] if n not in A}))
    if len(cand) < 7:
        return Synthesis('INFEASIBLE', [], {}, readouts, root, anc, 0.0)
    bits = ('r',) + cand                                     # vector coordinates
    bi = {b: i for i, b in enumerate(bits)}
    gates = [(u, v) for u in anc for v in anc if u != v and G.has_edge(u, v)]
    gates += [(n, a) for n in cand for a in anc if G.has_edge(n, a)]
    m = cp_model.CpModel()
    g = {(t, e): m.NewBoolVar('') for t in range(T) for e in gates}
    idle = [m.NewBoolVar('') for _ in range(T)]
    for t in range(T):
        m.AddExactlyOne([g[(t, e)] for e in gates] + [idle[t]])
        if t + 1 < T:
            m.AddImplication(idle[t], idle[t + 1])            # idle slots only at the end
    if exact_T:
        for t in range(T):
            m.Add(idle[t] == 0)
    used = {n: m.NewBoolVar('') for n in cand}               # node holds a data qubit
    m.Add(sum(used.values()) == 7)
    for (t, e), var in g.items():
        if e[0] in used:
            m.AddImplication(var, used[e[0]])               # only data nodes couple

    def xor(terms):
        """Parity of a list of literals and 0/1 constants (returns an int when constant)."""
        c = sum(x for x in terms if isinstance(x, int)) % 2
        vs = [x for x in terms if x is not None and not isinstance(x, int)]
        if not vs:
            return c
        if len(vs) == 1 and c == 0:
            return vs[0]
        b = m.NewBoolVar(''); k = m.NewIntVar(0, len(vs) + 1, '')
        m.Add(sum(vs) + c == 2 * k + b)
        return b

    def land(x, y):
        if isinstance(x, int):
            return y if x else 0
        if isinstance(y, int):
            return x if y else 0
        z = m.NewBoolVar('')
        m.AddMultiplicationEquality(z, [x, y])
        return z

    # forward GF(2) state of every ancilla
    S = {a: [1 if (a == root and b == 'r') else 0 for b in bits] for a in anc}
    for t in range(T):
        new = {}
        for v in anc:
            vec = []
            for i, b in enumerate(bits):
                terms = [S[v][i]]
                for (c, w) in gates:
                    if w != v:
                        continue
                    if c in A:
                        terms.append(land(g[(t, (c, w))], S[c][i]))
                    elif b == c:
                        terms.append(g[(t, (c, w))])
                vec.append(xor(terms))
            new[v] = vec
        S = new

    def fix(x, val):
        if isinstance(x, int):
            if x != val:
                m.AddBoolOr([])                               # contradiction
        else:
            m.Add(x == val)

    for a in nonroot:
        fix(S[a][0], 0)                                       # root bit only on the root
    for a in zeros:
        for n in cand:
            fix(S[a][bi[n]], 0)
    col = {}
    for n in cand:
        bitsn = [S[readouts[j]][bi[n]] for j in range(3)]
        cv = m.NewIntVar(0, 7, '')
        m.Add(cv == sum((1 << j) * x for j, x in enumerate(bitsn)))
        m.Add(cv >= 1).OnlyEnforceIf(used[n])
        m.Add(cv == 0).OnlyEnforceIf(used[n].Not())
        col[n] = (cv, bitsn)
    # the 7 used nodes carry the 7 distinct non-zero columns
    m.AddAllDifferent([_tag(m, col[n][0], used[n], i) for i, n in enumerate(cand)])

    # backward Z propagation: Z[t][x] = coordinates (ancillas + data nodes) of a Z on x right after slot t-1
    zbits = anc + cand
    zi = {b: i for i, b in enumerate(zbits)}
    Z = {a: [1 if b == a else 0 for b in zbits] for a in anc}
    events = []                                               # (flag, data-vector) per origin and slot
    hist = [None] * (T + 1)
    hist[T] = Z
    for t in range(T - 1, -1, -1):
        nxt = hist[t + 1]
        cur = {}
        for v in anc:
            vec = []
            for i, b in enumerate(zbits):
                terms = [nxt[v][i]]
                for (c, w) in gates:
                    if w != v:
                        continue
                    if c in A:
                        terms.append(land(g[(t, (c, w))], nxt[c][i]))
                    elif b == c:
                        terms.append(g[(t, (c, w))])
                vec.append(xor(terms))
            cur[v] = vec
        hist[t] = cur

    # syndrome and parity of the data part of each Z vector
    def syn_par(vec):
        par = xor([vec[zi[n]] for n in cand])
        syn = []
        for j in range(3):
            syn.append(xor([land(vec[zi[n]], col[n][1][j]) for n in cand]))
        return syn, par

    info = {}
    for t in range(T + 1):
        for a in anc:
            vec = hist[t][a]
            syn, par = syn_par(vec)
            info[(t, a)] = (vec[zi[root]], syn, par)

    pi = [m.NewBoolVar('') for _ in range(8)]
    m.Add(pi[0] == 0)

    def constrain(flag, syn, par, cond=None):
        enf = [] if cond is None else [cond]
        flag_v = flag
        if isinstance(flag_v, int):
            fb = m.NewConstant(flag_v)
        else:
            fb = flag_v
        sv = [s if not isinstance(s, int) else m.NewConstant(s) for s in syn]
        pv = par if not isinstance(par, int) else m.NewConstant(par)
        anyz = m.NewBoolVar(''); m.AddMaxEquality(anyz, sv)
        m.Add(pv == anyz).OnlyEnforceIf(enf + [fb.Not()])
        for s in range(8):
            lits = [sv[i] if (s >> i) & 1 else sv[i].Not() for i in range(3)]
            e = m.NewBoolVar('')
            m.AddBoolAnd(lits).OnlyEnforceIf(e)
            m.AddBoolOr([x.Not() for x in lits]).OnlyEnforceIf(e.Not())
            m.Add(pv == pi[s]).OnlyEnforceIf(enf + [fb, e])

    for (t, a), (flag, syn, par) in info.items():
        constrain(flag, syn, par)
    if pairs:
        def xr(x, y):
            return xor([x, y])
        for t in range(T):
            for (c, w) in gates:
                fw, sw, pw = info[(t + 1, w)]
                if c in A:
                    fc, sc, pc = info[(t + 1, c)]
                    constrain(xr(fw, fc), [xr(sw[j], sc[j]) for j in range(3)], xr(pw, pc), g[(t, (c, w))])
                else:                                         # data Z on the control plus the hook on w
                    sd = [col[c][1][j] for j in range(3)]
                    constrain(fw, [xr(sw[j], sd[j]) for j in range(3)], xr(pw, 1), g[(t, (c, w))])

    m.Minimize(sum(1 - idle[t] for t in range(T)))
    if hint:
        for t, e in enumerate(hint):
            if (t, e) in g:
                m.AddHint(g[(t, e)], 1)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    st = solver.Solve(m)
    name = solver.StatusName(st)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Synthesis(name, [], {}, readouts, root, anc, solver.WallTime())
    slots = [e for t in range(T) for e in gates if solver.Value(g[(t, e)])]
    data = {n: solver.Value(col[n][0]) for n in cand if solver.Value(used[n])}
    return Synthesis(name, slots, data, readouts, root, anc, solver.WallTime())


def _tag(m, cv, used, i):
    """Distinctness helper: used nodes keep their column, unused ones get a unique dummy value."""
    x = m.NewIntVar(0, 1000, '')
    m.Add(x == cv).OnlyEnforceIf(used)
    m.Add(x == 100 + i).OnlyEnforceIf(used.Not())
    return x


def to_published(res: Synthesis, G: nx.Graph, name='synthesized block'):
    """PublishedRound for the full round (X block, then Z block) from a synthesis result."""
    from .core import SUPPORTS
    from .published import Block, PublishedRound
    # data labelling: column c -> the data index whose Steane column (which checks contain it) is c
    cols = {sum(1 << i for i in range(3) if q in SUPPORTS[i]): q for q in range(7)}
    dq = {n: cols[c] for n, c in res.data.items()}
    layout = {f'd{dq[n] + 1}': n for n in res.data}
    layout.update({f'a{a}': a for a in res.anc})
    gates = []
    for c, t in res.slots:
        gates.append((f'd{dq[c] + 1}' if c in dq else f'a{c}', f'a{t}'))
    checks = {f'a{a}': j for j, a in enumerate(res.readouts)}
    extra = tuple(f'a{a}' for a in res.anc if a != res.root and a not in res.readouts)
    blk = Block(checks, (f'a{res.root}',), tuple(gates), 'Z', zeros=extra)
    edges = tuple(sorted(tuple(sorted(e)) for e in G.edges))
    n_nodes = max(G.nodes) + 1
    return PublishedRound(name, 'graph', edges, n_nodes, layout, {q + 1: q for q in range(7)},
                          {0: 0, 1: 1, 2: 2}, (blk,))
