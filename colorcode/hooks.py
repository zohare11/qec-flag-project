"""Hook errors and the exact circuit distance of a single-auxiliary schedule.

A fault on a plaquette's auxiliary right after its j-th CNOT spreads to the data qubits that the
auxiliary touches later: a suffix of the schedule ("hook").  Generators: every single data
qubit, and every proper suffix of every plaquette (reduced modulo that plaquette's stabilizer).
`static_distance` is the fewest generators whose sum is a non-trivial logical operator.

Claim: for these circuits (X block then Z block each round, same schedule in both, any number of
rounds, and noisy-CNOT, SI1000 or uniform depolarizing noise) the circuit-level distance equals
`static_distance`.

*  Lower bound.  Take the Z-basis memory (the X basis is the same by self-duality).  The data part
   of any single fault's X component is a single qubit or one suffix: X-block faults on the
   auxiliary spread forward through CX(aux -> data); Z-block CNOTs have data as control, so data X
   errors stay where they are and auxiliary X errors stay on the auxiliary; measurement and reset
   faults leave no data X.  If no detector fires, the chain of Z detectors gives
   syndrome(final data X error) = last round = ... = first round = 0, and the observable flip says
   the final data X error is a non-trivial logical.  It is the sum of the faults' data parts, so
   the number of faults is at least `static_distance`.
*  Upper bound.  Put all the generators of a minimum solution into the X block of one round:
   auxiliary X faults after the right CNOTs give the suffixes, data X faults the singles.  They
   all happen before that round's Z block, no X detector sees them, and the Z syndrome of their
   sum is zero.

So the expensive search over Stim's detector error model is not needed; `verify.py` re-checks the
equality directly on the detector error model at small d.
"""
from __future__ import annotations

FLAGGED: set = set()      # plaquette indices whose middle hook is caught by a flag qubit (see search.flag)


def hook_sets(sched_p):
    order = [v for v, _ in sorted(sched_p.items(), key=lambda kv: kv[1])]
    return [frozenset(order[j:]) for j in range(1, len(order))]


def generators(data, plaq, sched, flagged=None):
    flagged = FLAGGED if flagged is None else flagged
    gens = [frozenset([v]) for v in data]
    seen = set(gens)
    src = [('data', v) for v in data]
    for i, p in enumerate(plaq):
        if i in flagged:
            continue
        sup = frozenset(p['sup'].values())
        for h in hook_sets(sched[i]):
            h2 = h if len(h) <= len(sup) - len(h) else sup - h
            if len(h2) >= 2 and h2 not in seen:
                seen.add(h2)
                gens.append(h2)
                src.append(('hook', i, tuple(sorted(h2))))
    return gens, src


def _solver(data, plaq, sched, w, threads=1):
    import pycryptosat
    from pysat.card import CardEnc, EncType
    gens, src = generators(data, plaq, sched)
    n = len(gens)
    s = pycryptosat.Solver(threads=threads)
    for p in plaq:
        sup = set(p['sup'].values())
        vs = [i + 1 for i, g in enumerate(gens) if len(g & sup) % 2]
        if vs:
            s.add_xor_clause(vs, False)
    # the logical Z on all data qubits anticommutes with odd-size X errors
    s.add_xor_clause([i + 1 for i, g in enumerate(gens) if len(g) % 2], True)
    for cl in CardEnc.atmost(lits=list(range(1, n + 1)), bound=w, top_id=n, encoding=EncType.seqcounter).clauses:
        s.add_clause(cl)
    return s, gens, src


def has_logical(data, plaq, sched, w, threads=1):
    """A logical made of at most w faults, as a list of generator sources, or None."""
    s, gens, src = _solver(data, plaq, sched, w, threads)
    sat, model = s.solve()
    return [src[i] for i in range(len(gens)) if model[i + 1]] if sat else None


def static_distance(data, plaq, sched, hi=None, lo=1, threads=1):
    """(circuit distance, one minimum logical as generator sources)."""
    for w in range(lo, (hi or len(data)) + 1):
        sol = has_logical(data, plaq, sched, w, threads)
        if sol is not None:
            return w, sol
    return None, None


def bad_logicals(data, plaq, sched, target, k=20, threads=1):
    """Up to k different hook sets, each part of a logical of fewer than `target` faults ([] = distance >= target)."""
    s, gens, src = _solver(data, plaq, sched, target - 1, threads)
    hook_idx = [i for i, x in enumerate(src) if x[0] == 'hook']
    out = []
    while len(out) < k:
        sat, model = s.solve()
        if not sat:
            break
        used = [i for i in hook_idx if model[i + 1]]
        out.append([src[i] for i in used])
        if not used:
            break
        s.add_clause([-(i + 1) for i in used])
    return out

