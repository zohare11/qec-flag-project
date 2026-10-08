"""Interleaved X/Z syndrome extraction for the color code, one auxiliary per plaquette.

Each round has two blocks.  In block 1 the plaquettes in `first_x` measure X while all others
measure Z; in block 2 they swap.  An X check and a Z check measured in the same block on adjacent
plaquettes share two data qubits, and the measurement stays correct only if the X check reaches
both shared qubits before the Z check, or both after ("commutation rule").

Hook errors are then no longer purely spatial: an X hook spread by an X check reaches some
neighbouring Z checks before they read the data and others after, so its syndrome is split
between two rounds.  The separate-block bound d - floor((d+1)/6) need not apply.
"""
from __future__ import annotations

import itertools

import stim

from .lattice import lattice

COLORS = ('red', 'green', 'blue')
LABELS = ('TL', 'TR', 'L', 'R', 'BL', 'BR')


def bulk_structure(d=11):
    """(vertex types, adjacency types) of the bulk: which (colour, label) pairs meet at a vertex, and
    for each pair of adjacent hexagons the two shared vertices as ((colour, label), (colour, label))."""
    data, plaq = lattice(d)
    by_v = {}
    for i, p in enumerate(plaq):
        for lab, v in p['sup'].items():
            by_v.setdefault(v, []).append((i, lab))
    vtypes, adj = set(), set()
    for v, us in by_v.items():
        if len(us) == 3 and all(len(plaq[i]['sup']) == 6 for i, _ in us):
            vtypes.add(tuple(sorted((plaq[i]['color'], lab) for i, lab in us)))
    for i, p in enumerate(plaq):
        for j, q in enumerate(plaq):
            if i < j and len(p['sup']) == 6 and len(q['sup']) == 6:
                sh = set(p['sup'].values()) & set(q['sup'].values())
                if sh:
                    ip = {v: k for k, v in p['sup'].items()}
                    iq = {v: k for k, v in q['sup'].items()}
                    adj.add(tuple(sorted(tuple(sorted(((p['color'], ip[v]), (q['color'], iq[v])))) for v in sh)))
    return sorted(vtypes), sorted(adj)


def valid_tables(x_colors, limit=None, time_limit=600, seed=0, extra=None):
    """Enumerate per-colour step tables {colour: {label: step}} (same table in both blocks) obeying
    the data-conflict rule and the commutation rule for colours in `x_colors` vs the others."""
    from ortools.sat.python import cp_model
    vtypes, adj = bulk_structure()
    m = cp_model.CpModel()
    T = {(c, l): m.NewIntVar(1, 6, f'{c}{l}') for c in COLORS for l in LABELS}
    for c in COLORS:
        m.AddAllDifferent([T[(c, l)] for l in LABELS])
    for vt in vtypes:
        m.AddAllDifferent([T[x] for x in vt])
    for (u1, v1), (u2, v2) in [tuple(tuple(sorted(e)) for e in a) for a in adj]:
        # u = (colour, label) of one plaquette, v of the other, at the two shared vertices
        A1, B1 = (u1, v1) if (u1[0] in x_colors) else (v1, u1)
        A2, B2 = (u2, v2) if (u2[0] in x_colors) else (v2, u2)
        if (A1[0] in x_colors) == (B1[0] in x_colors):
            continue                        # same check type in each block: commute
        b1 = m.NewBoolVar('')
        m.Add(T[A1] < T[B1]).OnlyEnforceIf(b1)
        m.Add(T[A1] > T[B1]).OnlyEnforceIf(b1.Not())
        m.Add(T[A2] < T[B2]).OnlyEnforceIf(b1)
        m.Add(T[A2] > T[B2]).OnlyEnforceIf(b1.Not())
    if extra:
        extra(m, T)
    sols = []

    class CB(cp_model.CpSolverSolutionCallback):
        def on_solution_callback(self):
            sols.append({c: {l: self.Value(T[(c, l)]) for l in LABELS} for c in COLORS})
            if limit and len(sols) >= limit:
                self.StopSearch()

    s = cp_model.CpSolver()
    s.parameters.enumerate_all_solutions = True
    s.parameters.max_time_in_seconds = time_limit
    s.parameters.random_seed = seed
    st = s.Solve(m, CB())
    return sols, s.StatusName(st)


def schedule_from_table(plaq, table):
    return {i: {v: table[p['color']][k] for k, v in p['sup'].items()} for i, p in enumerate(plaq)}


def check_interleaved(plaq, sched1, sched2, first_x):
    """Assert no data conflicts and the commutation rule in both blocks."""
    for sched, xs in ((sched1, first_x), (sched2, {i for i in range(len(plaq))} - set(first_x))):
        use = {}
        for i, s in sched.items():
            for v, t in s.items():
                assert (v, t) not in use, f'data {v} twice at step {t}'
                use[(v, t)] = i
        for i, j in itertools.combinations(range(len(plaq)), 2):
            if (i in xs) == (j in xs):
                continue
            sh = set(sched[i]) & set(sched[j])
            if sh:
                order = {sched[i][v] < sched[j][v] for v in sh}
                assert len(order) == 1, f'plaquettes {i}, {j}: shared qubits in mixed order'
    return True


def interleaved_circuit(d, sched1, sched2, first_x, rounds=None, p=1e-3, basis='Z', noise='cnot'):
    """Memory experiment; block 1: plaquettes in first_x measure X (others Z) with sched1; block 2 swapped
    with sched2.  Detector coordinates as in circuits.memory_circuit (type 0 = X, 1 = Z, 2 = final)."""
    data, plaq = lattice(d)
    rounds = rounds or d
    first_x = set(first_x)
    nd = len(data)
    dq = {v: i for i, v in enumerate(data)}
    aux = {i: nd + i for i in range(len(plaq))}
    si = noise == 'si1000'
    allq = list(range(nd + len(plaq)))
    c = stim.Circuit()
    for v, i in dq.items():
        c.append('QUBIT_COORDS', [i], [v[0], v[1]])
    for j, p_ in enumerate(plaq):
        c.append('QUBIT_COORDS', [aux[j]], [p_['center'][0], p_['center'][1], 1])

    def idle(active, extra=0.0):
        if noise == 'cnot':
            return
        rest = [q for q in allq if q not in active]
        if rest:
            c.append('DEPOLARIZE1', rest, (p / 10 if si else p) + extra)

    c.append('R' if basis == 'Z' else 'RX', [dq[v] for v in data])
    if noise != 'cnot':
        c.append('X_ERROR' if basis == 'Z' else 'Z_ERROR', [dq[v] for v in data], 2 * p if si else p)
    c.append('TICK')
    meas = []
    blocks = ((sched1, first_x), (sched2, set(range(len(plaq))) - first_x))
    for rnd in range(rounds):
        for sched, xs in blocks:
            xa = [aux[j] for j in sorted(xs)]
            za = [aux[j] for j in range(len(plaq)) if j not in xs]
            if xa:
                c.append('RX', xa)
            if za:
                c.append('R', za)
            if noise != 'cnot':
                if xa:
                    c.append('Z_ERROR', xa, 2 * p if si else p)
                if za:
                    c.append('X_ERROR', za, 2 * p if si else p)
                idle(xa + za, 2 * p if si else 0)
            c.append('TICK')
            steps = max(t for s in sched.values() for t in s.values())
            for t in range(1, steps + 1):
                pairs = []
                for j, s in sched.items():
                    for v, tt in s.items():
                        if tt == t:
                            pairs += [aux[j], dq[v]] if j in xs else [dq[v], aux[j]]
                if pairs:
                    c.append('CX', pairs)
                    c.append('DEPOLARIZE2', pairs, p)
                    idle(set(pairs))
                c.append('TICK')
            if noise != 'cnot':
                if xa:
                    c.append('Z_ERROR', xa, 5 * p if si else p)
                if za:
                    c.append('X_ERROR', za, 5 * p if si else p)
                idle(xa + za, 2 * p if si else 0)
            if xa:
                c.append('MX', xa)
                meas += [(rnd, 'X', j) for j in sorted(xs)]
            if za:
                c.append('M', za)
                meas += [(rnd, 'Z', j) for j in range(len(plaq)) if j not in xs]
            c.append('TICK')
    if noise != 'cnot':
        c.append('X_ERROR' if basis == 'Z' else 'Z_ERROR', [dq[v] for v in data], 5 * p if si else p)
    c.append('M' if basis == 'Z' else 'MX', [dq[v] for v in data])
    nm = len(meas) + nd
    rec = lambda k: stim.target_rec(k - nm)
    mi = {m_: k for k, m_ in enumerate(meas)}
    for (rnd, typ, j), k in sorted(mi.items(), key=lambda kv: kv[1]):
        xy = [plaq[j]['center'][0], plaq[j]['center'][1], rnd, 0 if typ == 'X' else 1]
        if rnd == 0:
            if typ == basis:
                c.append('DETECTOR', [rec(k)], xy)
        else:
            c.append('DETECTOR', [rec(k), rec(mi[(rnd - 1, typ, j)])], xy)
    for j, p_ in enumerate(plaq):
        last = mi[(rounds - 1, basis, j)]
        c.append('DETECTOR', [rec(last)] + [rec(len(meas) + dq[v]) for v in p_['sup'].values()],
                 [p_['center'][0], p_['center'][1], rounds, 2])
    c.append('OBSERVABLE_INCLUDE', [rec(len(meas) + i) for i in range(nd)], 0)
    return c, data, plaq
