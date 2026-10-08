"""Independent circuit-level check on Stim's detector error model.

Exact SAT ("is there an undetectable logical with at most w faults?") over the whole DEM is slow
beyond d = 5, so the check keeps only the memory basis' detectors and merges mechanisms with the
same remaining signature.  Dropping detectors only removes constraints, so "no logical with <= w
faults" in the reduced problem holds for the full circuit; a logical found in the reduced problem
is lifted back to the full DEM with a second SAT call restricted to its mechanisms.
"""
from __future__ import annotations


def _sat(nd, cols, w, threads=2):
    import pycryptosat
    from pysat.card import CardEnc, EncType
    n = len(cols)
    by_det = [[] for _ in range(nd)]
    obs = []
    for i, (dets, ob) in enumerate(cols):
        for x in dets:
            by_det[x].append(i + 1)
        if 0 in ob:
            obs.append(i + 1)
    s = pycryptosat.Solver(threads=threads)
    for vs in by_det:
        if vs:
            s.add_xor_clause(vs, False)
    s.add_xor_clause(obs, True)
    for cl in CardEnc.atmost(lits=list(range(1, n + 1)), bound=w, top_id=n, encoding=EncType.seqcounter).clauses:
        s.add_clause(cl)
    sat, model = s.solve()
    return [i for i in range(n) if model[i + 1]] if sat else None


def reduced(circuit, basis='Z'):
    dem = circuit.detector_error_model(decompose_errors=False)
    coords = dem.get_detector_coordinates()
    keep_types = {1, 2, 4} if basis == 'Z' else {0, 2, 5}      # 4/5: flags catching X/Z hooks
    keep = sorted(k for k, c in coords.items() if int(c[3]) in keep_types)
    idx = {k: i for i, k in enumerate(keep)}
    sig, full = {}, []
    for inst in dem.flattened():
        if inst.type != 'error':
            continue
        dets = [t.val for t in inst.targets_copy() if t.is_relative_detector_id()]
        obs = tuple(t.val for t in inst.targets_copy() if t.is_logical_observable_id())
        key = (tuple(sorted(idx[x] for x in dets if x in idx)), obs)
        if key[0] or key[1]:
            sig.setdefault(key, []).append(len(full))
        full.append((dets, obs))
    return len(keep), list(sig), sig, full


def logical_within(circuit, w, basis='Z'):
    """True / False: does the full circuit have an undetectable logical error of at most w faults?"""
    nd, cols, sig, full = reduced(circuit, basis)
    sol = _sat(nd, cols, w)
    if sol is None:
        return False
    mech = sorted({m for i in sol for m in sig[cols[i]]})
    dets = sorted({x for m in mech for x in full[m][0]})
    di = {x: i for i, x in enumerate(dets)}
    sub = [([di[x] for x in full[m][0]], full[m][1]) for m in mech]
    if _sat(len(dets), sub, w) is not None:
        return True
    raise RuntimeError('reduced logical did not lift; increase the search (inconclusive)')
