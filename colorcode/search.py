"""CEGAR search for single-auxiliary schedules (one schedule per plaquette) with a target distance.

Master problem (CP-SAT): a time step per (plaquette, vertex); distinct within a plaquette; no data
qubit in two CNOTs at once.  Counterexamples (SAT, `hooks.bad_logicals`): logicals with fewer than
`target` faults.  Each one adds the cut "at least one of its hooks is absent", where a hook
(a set S of the plaquette's vertices, or its complement) is present iff every vertex outside S
comes before every vertex in S.

flag=True models a flag qubit on every weight-4 plaquette: its data CNOTs sit at steps {1|2}, 3,
4, {5|6} and the two free steps hold auxiliary-flag CNOTs that bracket the middle hook, so a
middle hook always fires the flag and costs two faults; those hooks are dropped from the model.
"""
from __future__ import annotations

import time

from . import hooks
from .lattice import lattice, schedule_from_colors


def search(d, free='all', target=None, steps=6, flag=False, max_iter=5000, time_per=60, k=30,
           seed_kf=True, verbose=True, fixed=None, workers=2):
    """free: 'all' | 'boundary' (weight-4 plaquettes only) | 'near' (also hexagons touching them);
    the rest keep the Kishony-Fowler schedule (or `fixed`)."""
    from ortools.sat.python import cp_model
    data, plaq = lattice(d)
    hooks.FLAGGED = {i for i, p in enumerate(plaq) if len(p['sup']) == 4} if flag else set()
    target = target or d
    base = fixed or schedule_from_colors(plaq)
    m = cp_model.CpModel()
    t = {}
    for i, p in enumerate(plaq):
        for v in p['sup'].values():
            t[(i, v)] = m.NewIntVar(1, steps, '')
        m.AddAllDifferent([t[(i, v)] for v in p['sup'].values()])
    by_v = {}
    for (i, v), var in t.items():
        by_v.setdefault(v, []).append(var)
    for vs in by_v.values():
        m.AddAllDifferent(vs)

    def is_free(i):
        p = plaq[i]
        if free == 'all' or len(p['sup']) < 6:
            return True
        if free == 'near':
            vs = set(p['sup'].values())
            return any(len(q['sup']) < 6 and vs & set(q['sup'].values()) for q in plaq)
        return False

    for i, p in enumerate(plaq):
        for v in p['sup'].values():
            if not is_free(i):
                m.Add(t[(i, v)] == base[i][v])
            elif seed_kf:
                m.AddHint(t[(i, v)], base[i][v])
    if flag:
        assert steps == 6
        for i, p in enumerate(plaq):
            if len(p['sup']) != 4:
                continue
            vs = [t[(i, v)] for v in p['sup'].values()]
            eq = {}
            for j, var in enumerate(vs):
                for s_ in range(1, 7):
                    b = m.NewBoolVar('')
                    m.Add(var == s_).OnlyEnforceIf(b)
                    m.Add(var != s_).OnlyEnforceIf(b.Not())
                    eq[(j, s_)] = b
            for group in ((3,), (4,), (1, 2), (5, 6)):
                m.Add(sum(eq[(j, s_)] for j in range(4) for s_ in group) == 1)
    before = {}
    for i, p in enumerate(plaq):
        vs = list(p['sup'].values())
        for u in vs:
            for w in vs:
                if u != w:
                    b = m.NewBoolVar('')
                    m.Add(t[(i, u)] < t[(i, w)]).OnlyEnforceIf(b)
                    m.Add(t[(i, u)] > t[(i, w)]).OnlyEnforceIf(b.Not())
                    before[(i, u, w)] = b
    cache = {}

    def present(i, h):
        if (i, h) in cache:
            return cache[(i, h)]
        sup = frozenset(plaq[i]['sup'].values())
        lits = []
        for S in (h, sup - h):
            if 0 < len(S) < len(sup):
                z = m.NewBoolVar('')
                conds = [before[(i, u, w)] for u in sup - S for w in S]
                m.AddBoolAnd(conds).OnlyEnforceIf(z)
                m.AddBoolOr([c.Not() for c in conds]).OnlyEnforceIf(z.Not())
                lits.append(z)
        y = m.NewBoolVar('')
        m.AddMaxEquality(y, lits)
        cache[(i, h)] = y
        return y

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_per
    solver.parameters.num_workers = workers
    t0 = time.time()
    for it in range(max_iter):
        st = solver.Solve(m)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return {'status': solver.StatusName(st), 'iterations': it, 'seconds': time.time() - t0}
        sched = {i: {v: solver.Value(t[(i, v)]) for v in p['sup'].values()} for i, p in enumerate(plaq)}
        bads = hooks.bad_logicals(data, plaq, sched, target, k=k)
        if verbose and it % 10 == 0:
            print(f'  iter {it}: {len(bads)} logicals below {target}', flush=True)
        if not bads:
            return {'status': 'FOUND', 'iterations': it, 'sched': sched, 'seconds': time.time() - t0}
        for hs in bads:
            assert hs, 'logical below target without hooks'
            m.AddBoolOr([present(h[1], frozenset(h[2])).Not() for h in hs])
    return {'status': 'ITERATION_LIMIT', 'iterations': max_iter, 'seconds': time.time() - t0}
