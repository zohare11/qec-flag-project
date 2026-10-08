"""CEGAR over schedule *families*: one schedule per plaquette class, shared by several distances.

Classes: bulk plaquettes by colour; plaquettes within `depth` lattice units of exactly one edge by
(edge, distance to the edge, position along the edge mod `period`, weight); plaquettes near two
edges by their offset from that corner.  A family that reaches d - 1 for several d at once is a
candidate for every d.
"""
from __future__ import annotations

import time

from .hooks import bad_logicals
from .lattice import lattice


def classify(d, plaq, depth, period=1):
    y0, a, b = -3, -1, 3 * d - 7
    corners = {'BL': (a - y0, y0), 'BR': (b - y0, y0), 'T': ((b - a) / 2, (a + b) / 2)}
    keys = []
    for p in plaq:
        cx, cy = p['center']
        dB, dL, dR = cy - y0, a - (cy - cx), b - (cy + cx)
        near = [e for e, dist in (('B', dB), ('L', dL), ('R', dR)) if dist <= depth]
        if len(near) == 3:
            keys.append(('middle', cx - corners['BL'][0], cy - corners['BL'][1], len(p['sup'])))
        elif len(near) == 2:
            corner = {'BL': 'BL', 'BR': 'BR', 'LR': 'T'}[''.join(sorted(near))]
            ox, oy = corners[corner]
            keys.append(('corner', corner, cx - ox, cy - oy, len(p['sup'])))
        elif near == ['B']:
            keys.append(('edge', 'B', dB, (cx // 6) % period, len(p['sup'])))
        elif near == ['L']:
            keys.append(('edge', 'L', dL, (cx // 3) % period, len(p['sup'])))
        elif near == ['R']:
            keys.append(('edge', 'R', dR, (cx // 3) % period, len(p['sup'])))
        else:
            keys.append(('bulk', p['color']))
    return keys


def schedules(ds, depth, period, val):
    """Expand a class assignment {(class, label): step} to per-d schedules."""
    out = {}
    for d in ds:
        data, plaq = lattice(d)
        keys = classify(d, plaq, depth, period)
        out[d] = {i: {v: val[(keys[i], lab)] for lab, v in p['sup'].items()} for i, p in enumerate(plaq)}
    return out


def run(ds, depth, period=1, offset=1, max_iter=3000, k=30, time_per=120, verbose=True):
    from ortools.sat.python import cp_model
    m = cp_model.CpModel()
    tv = {}
    lat = {}
    for d in ds:
        data, plaq = lattice(d)
        keys = classify(d, plaq, depth, period)
        lat[d] = (data, plaq, keys)
        for key, p in zip(keys, plaq):
            for lab in p['sup']:
                if (key, lab) not in tv:
                    tv[(key, lab)] = m.NewIntVar(1, 6, '')
    classes = {}
    for (key, lab) in tv:
        classes.setdefault(key, []).append(lab)
    for key, labs in classes.items():
        m.AddAllDifferent([tv[(key, l_)] for l_ in labs])
    added = set()
    for d, (data, plaq, keys) in lat.items():
        by_v = {}
        for key, p in zip(keys, plaq):
            for lab, v in p['sup'].items():
                by_v.setdefault(v, []).append((key, lab))
        for users in by_v.values():
            for i in range(len(users)):
                for j in range(i + 1, len(users)):
                    pair = tuple(sorted([users[i], users[j]]))
                    if pair not in added and users[i] != users[j]:
                        added.add(pair)
                        m.Add(tv[users[i]] != tv[users[j]])
    before = {}

    def bvar(key, u, w):
        if (key, u, w) not in before:
            bb = m.NewBoolVar('')
            m.Add(tv[(key, u)] < tv[(key, w)]).OnlyEnforceIf(bb)
            m.Add(tv[(key, u)] > tv[(key, w)]).OnlyEnforceIf(bb.Not())
            before[(key, u, w)] = bb
        return before[(key, u, w)]

    pres = {}

    def present(key, labset):
        labs = frozenset(classes[key])
        S = frozenset(labset)
        if (key, S) in pres:
            return pres[(key, S)]
        lits = []
        for T in (S, labs - S):
            if 0 < len(T) < len(labs):
                z = m.NewBoolVar('')
                conds = [bvar(key, u, w) for u in labs - T for w in T]
                m.AddBoolAnd(conds).OnlyEnforceIf(z)
                m.AddBoolOr([c.Not() for c in conds]).OnlyEnforceIf(z.Not())
                lits.append(z)
        y = m.NewBoolVar('')
        m.AddMaxEquality(y, lits)
        pres[(key, S)] = y
        return y

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_per
    solver.parameters.num_workers = 2
    t0 = time.time()
    for it in range(max_iter):
        st = solver.Solve(m)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return {'status': solver.StatusName(st), 'iterations': it, 'seconds': time.time() - t0}
        val = {kk: solver.Value(v) for kk, v in tv.items()}
        total = 0
        for d in ds:
            data, plaq, keys = lat[d]
            sched = {i: {v: val[(keys[i], lab)] for lab, v in p['sup'].items()} for i, p in enumerate(plaq)}
            bads = bad_logicals(data, plaq, sched, d - offset, k=k)
            total += len(bads)
            for hs in bads:
                assert hs, 'logical below target without hooks'
                lits = []
                for h in hs:
                    i = h[1]
                    inv = {v: lab for lab, v in plaq[i]['sup'].items()}
                    lits.append(present(keys[i], frozenset(inv[v] for v in h[2])).Not())
                m.AddBoolOr(lits)
        if verbose and it % 5 == 0:
            print(f'  iter {it}: {total} logicals below target', flush=True)
        if total == 0:
            return {'status': 'FOUND', 'iterations': it, 'val': val, 'seconds': time.time() - t0}
    return {'status': 'ITERATION_LIMIT', 'iterations': max_iter, 'seconds': time.time() - t0}
