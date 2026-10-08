"""Stim memory experiments for single-auxiliary color code schedules."""
from __future__ import annotations

import stim

from .lattice import lattice, schedule_from_colors


def memory_circuit(d, sched=None, rounds=None, p=1e-3, basis='Z', noise='cnot', order=('X', 'Z')):
    """Data reset, `rounds` rounds of (X block, Z block), data measured in `basis`.

    noise: 'cnot'    two-qubit depolarizing p after every CNOT only (Kishony & Fowler's noisy-CNOT model);
           'si1000'  Gidney-Newman-McEwen superconducting-inspired model;
           'uniform' p at every location.
    Detector coordinates: (x, y, round, type) with type 0 = X check, 1 = Z check, 2 = final data check.
    Returns (circuit, data, plaquettes, schedule)."""
    data, plaq = lattice(d)
    sched = sched or schedule_from_colors(plaq)
    rounds = rounds or d
    nd = len(data)
    dq = {v: i for i, v in enumerate(data)}
    aux = {i: nd + i for i in range(len(plaq))}
    steps = max(t for s in sched.values() for t in s.values())
    si = noise == 'si1000'
    c = stim.Circuit()
    for v, i in dq.items():
        c.append('QUBIT_COORDS', [i], [v[0], v[1]])
    for j, p_ in enumerate(plaq):
        c.append('QUBIT_COORDS', [aux[j]], [p_['center'][0], p_['center'][1], 1])
    allq = list(range(nd + len(plaq)))

    def idle(active, extra=0.0):
        if noise == 'cnot':
            return
        rest = [q for q in allq if q not in active]
        if rest:
            c.append('DEPOLARIZE1', rest, (p / 10 if si else p) + extra)

    flip = lambda b: 'X_ERROR' if b == 'Z' else 'Z_ERROR'
    c.append('R' if basis == 'Z' else 'RX', [dq[v] for v in data])
    if noise != 'cnot':
        c.append(flip(basis), [dq[v] for v in data], 2 * p if si else p)
    c.append('TICK')
    meas = []
    auxs = list(aux.values())
    for rnd in range(rounds):
        for typ in order:
            c.append('R' if typ == 'Z' else 'RX', auxs)
            if noise != 'cnot':
                c.append(flip(typ), auxs, 2 * p if si else p)
                idle(auxs, 2 * p if si else 0)
            c.append('TICK')
            for t in range(1, steps + 1):
                pairs = []
                for j, s in sched.items():
                    for v, tt in s.items():
                        if tt == t:
                            pairs += [dq[v], aux[j]] if typ == 'Z' else [aux[j], dq[v]]
                if pairs:
                    c.append('CX', pairs)
                    c.append('DEPOLARIZE2', pairs, p)
                    idle(set(pairs))
                c.append('TICK')
            if noise != 'cnot':
                c.append(flip(typ), auxs, 5 * p if si else p)
                idle(auxs, 2 * p if si else 0)
            c.append('M' if typ == 'Z' else 'MX', auxs)
            meas += [(rnd, typ, j) for j in range(len(plaq))]
            c.append('TICK')
    if noise != 'cnot':
        c.append(flip(basis), [dq[v] for v in data], 5 * p if si else p)
    c.append('M' if basis == 'Z' else 'MX', [dq[v] for v in data])
    nm = len(meas) + nd
    rec = lambda k: stim.target_rec(k - nm)
    mi = {m: k for k, m in enumerate(meas)}
    for rnd in range(rounds):
        for typ in order:
            for j, p_ in enumerate(plaq):
                xy = [p_['center'][0], p_['center'][1], rnd, 0 if typ == 'X' else 1]
                cur = mi[(rnd, typ, j)]
                if rnd == 0:
                    if typ == basis:
                        c.append('DETECTOR', [rec(cur)], xy)
                else:
                    c.append('DETECTOR', [rec(cur), rec(mi[(rnd - 1, typ, j)])], xy)
    for j, p_ in enumerate(plaq):
        last = mi[(rounds - 1, basis, j)]
        c.append('DETECTOR', [rec(last)] + [rec(len(meas) + dq[v]) for v in p_['sup'].values()],
                 [p_['center'][0], p_['center'][1], rounds, 2])
    # logical: product over all data qubits (n odd, every stabilizer has even weight)
    c.append('OBSERVABLE_INCLUDE', [rec(len(meas) + i) for i in range(nd)], 0)
    return c, data, plaq, sched
