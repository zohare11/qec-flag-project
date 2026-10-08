"""Stim memory experiments for single-auxiliary color code schedules."""
from __future__ import annotations

import stim

from .lattice import lattice, schedule_from_colors


def flag_steps(sched_p, steps=6):
    """The two free steps of a weight-4 plaquette, if they bracket its middle hook (else None)."""
    used = sorted(sched_p.values())
    free = [t for t in range(1, steps + 1) if t not in used]
    if len(used) != 4 or len(free) != 2:
        return None
    a, b = free
    return (a, b) if a < used[1] and b > used[2] else None


def memory_circuit(d, sched=None, rounds=None, p=1e-3, basis='Z', noise='cnot', order=('X', 'Z'), flags=False):
    """Data reset, `rounds` rounds of (X block, Z block), data measured in `basis`.

    noise: 'cnot'    two-qubit depolarizing p after every CNOT only (Kishony & Fowler's noisy-CNOT model);
           'si1000'  Gidney-Newman-McEwen superconducting-inspired model;
           'uniform' p at every location.
    flags: one flag qubit per weight-4 plaquette, coupled to its auxiliary at the two free steps
           (X block: CX aux -> flag, flag measured in Z; Z block: CX flag -> aux, flag measured in X).
    Detector coordinates: (x, y, round, type) with type 0 = X check, 1 = Z check, 2 = final data check,
    4 = X-block flag (catches X hooks), 5 = Z-block flag (catches Z hooks).
    Returns (circuit, data, plaquettes, schedule)."""
    data, plaq = lattice(d)
    sched = sched or schedule_from_colors(plaq)
    rounds = rounds or d
    nd = len(data)
    dq = {v: i for i, v in enumerate(data)}
    aux = {i: nd + i for i in range(len(plaq))}
    steps = max(t for s in sched.values() for t in s.values())
    fl = {}
    if flags:
        for i, p_ in enumerate(plaq):
            if len(p_['sup']) == 4:
                fs = flag_steps(sched[i], steps)
                assert fs, f'plaquette {i}: free steps do not bracket the middle hook'
                fl[i] = (nd + len(plaq) + len(fl), fs)
    si = noise == 'si1000'
    c = stim.Circuit()
    for v, i in dq.items():
        c.append('QUBIT_COORDS', [i], [v[0], v[1]])
    for j, p_ in enumerate(plaq):
        c.append('QUBIT_COORDS', [aux[j]], [p_['center'][0], p_['center'][1], 1])
    for j, (q, _) in fl.items():
        c.append('QUBIT_COORDS', [q], [plaq[j]['center'][0], plaq[j]['center'][1], 2])
    allq = list(range(nd + len(plaq) + len(fl)))

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
    flgs = [q for q, _ in fl.values()]
    for rnd in range(rounds):
        for typ in order:
            c.append('R' if typ == 'Z' else 'RX', auxs)
            if flgs:
                c.append('RX' if typ == 'Z' else 'R', flgs)
            if noise != 'cnot':
                c.append(flip(typ), auxs, 2 * p if si else p)
                if flgs:
                    c.append('Z_ERROR' if typ == 'Z' else 'X_ERROR', flgs, 2 * p if si else p)
                idle(auxs + flgs, 2 * p if si else 0)
            c.append('TICK')
            for t in range(1, steps + 1):
                pairs = []
                for j, s in sched.items():
                    for v, tt in s.items():
                        if tt == t:
                            pairs += [dq[v], aux[j]] if typ == 'Z' else [aux[j], dq[v]]
                for j, (q, fs) in fl.items():
                    if t in fs:
                        pairs += [q, aux[j]] if typ == 'Z' else [aux[j], q]
                if pairs:
                    c.append('CX', pairs)
                    c.append('DEPOLARIZE2', pairs, p)
                    idle(set(pairs))
                c.append('TICK')
            if noise != 'cnot':
                c.append(flip(typ), auxs, 5 * p if si else p)
                if flgs:
                    c.append('Z_ERROR' if typ == 'Z' else 'X_ERROR', flgs, 5 * p if si else p)
                idle(auxs + flgs, 2 * p if si else 0)
            c.append('M' if typ == 'Z' else 'MX', auxs)
            meas += [(rnd, typ, j) for j in range(len(plaq))]
            if flgs:
                c.append('MX' if typ == 'Z' else 'M', flgs)
                meas += [(rnd, typ, ('flag', j)) for j in fl]
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
            for j in fl:
                c.append('DETECTOR', [rec(mi[(rnd, typ, ('flag', j))])],
                         [plaq[j]['center'][0], plaq[j]['center'][1], rnd, 4 if typ == 'X' else 5])
    for j, p_ in enumerate(plaq):
        last = mi[(rounds - 1, basis, j)]
        c.append('DETECTOR', [rec(last)] + [rec(len(meas) + dq[v]) for v in p_['sup'].values()],
                 [p_['center'][0], p_['center'][1], rounds, 2])
    # logical: product over all data qubits (n odd, every stabilizer has even weight)
    c.append('OBSERVABLE_INCLUDE', [rec(len(meas) + i) for i in range(nd)], 0)
    return c, data, plaq, sched
