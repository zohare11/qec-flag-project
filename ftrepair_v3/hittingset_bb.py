"""Deterministic branch-and-bound hitting set for the larger v3 atom universe."""
from __future__ import annotations
from typing import Hashable, Iterable
from ftrepair_v2.hittingset import normalize_clauses, covers


def minimum_weight_hitting_set_bb(clauses: Iterable[Iterable[Hashable]], *,
                                  weights: dict[Hashable, float] | None = None,
                                  max_size: int | None = None,
                                  forbidden_atoms: Iterable[Hashable] = ()):
    cls = normalize_clauses(clauses)
    if not cls:
        return tuple()
    banned = set(forbidden_atoms)
    cls = tuple(frozenset(a for a in c if a not in banned) for c in cls)
    if any(not c for c in cls):
        return None
    weights = {} if weights is None else dict(weights)
    atoms = sorted(set().union(*cls), key=str)
    limit = len(atoms) if max_size is None else min(int(max_size), len(atoms))
    best: tuple | None = None
    best_cost = float('inf')

    # Dominance map: if two atoms cover the same clause set, keep the cheaper one
    # for branching order but do not remove the other entirely because tie-breaking
    # and later exact verification may distinguish them physically.
    cover_map = {a: frozenset(i for i,c in enumerate(cls) if a in c) for a in atoms}

    def lower_bound(uncovered: set[int]) -> int:
        # Greedy packing of pairwise-disjoint clauses gives a valid cardinality LB.
        used_atoms = set(); lb = 0
        for i in sorted(uncovered, key=lambda j: (len(cls[j]), j)):
            c = cls[i]
            if c.isdisjoint(used_atoms):
                lb += 1; used_atoms.update(c)
        return lb

    def recurse(chosen: tuple, uncovered: set[int], cost: float):
        nonlocal best, best_cost
        if not uncovered:
            key = (len(chosen), cost, tuple(map(str, chosen)))
            if best is None or key < (len(best), best_cost, tuple(map(str,best))):
                best = tuple(sorted(chosen, key=str)); best_cost = cost
            return
        if len(chosen) >= limit:
            return
        if best is not None and len(chosen) + lower_bound(uncovered) > len(best):
            return
        # Branch on the smallest remaining clause.  Prefer atoms covering many
        # still-uncovered clauses and then lower synthesis penalty.
        ci = min(uncovered, key=lambda i: (len(cls[i]), i))
        branch = sorted(cls[ci], key=lambda a: (
            -len(cover_map[a].intersection(uncovered)), float(weights.get(a,1.0)), str(a)
        ))
        for a in branch:
            if a in chosen:
                continue
            nc = cost + float(weights.get(a,1.0))
            if best is not None and len(chosen)+1 == len(best) and nc > best_cost + 1e-15:
                continue
            new_uncovered = uncovered.difference(cover_map[a])
            recurse(chosen + (a,), new_uncovered, nc)

    recurse(tuple(), set(range(len(cls))), 0.0)
    return best

def greedy_weighted_hitting_set(clauses: Iterable[Iterable[Hashable]], *,
                                weights: dict[Hashable,float] | None=None,
                                max_size: int | None=None):
    cls=normalize_clauses(clauses)
    if not cls:return tuple()
    weights={} if weights is None else dict(weights)
    uncovered=set(range(len(cls)));sol=[]
    atoms=sorted(set().union(*cls),key=str)
    covers_by={a:set(i for i,c in enumerate(cls) if a in c) for a in atoms}
    while uncovered:
        cand=[]
        for a in atoms:
            if a in sol:continue
            cov=len(covers_by[a]&uncovered)
            if not cov:continue
            w=max(float(weights.get(a,1.0)),1e-12)
            cand.append((-cov/w,-cov,w,str(a),a))
        if not cand:return None
        cand.sort();a=cand[0][-1];sol.append(a);uncovered-=covers_by[a]
        if max_size is not None and len(sol)>int(max_size):return None
    # Clause-level deletion minimization.
    changed=True
    while changed:
        changed=False
        for a in list(sol):
            trial=[x for x in sol if x!=a]
            if covers(trial,cls):
                sol=trial;changed=True;break
    return tuple(sorted(sol,key=str))


def hybrid_hitting_set(clauses: Iterable[Iterable[Hashable]], *,
                       weights: dict[Hashable,float] | None=None,
                       max_size: int | None=None,
                       exact_atom_limit:int=28,
                       exact_clause_limit:int=18):
    cls=normalize_clauses(clauses)
    if not cls:return tuple()
    atoms=set().union(*cls)
    if len(atoms)<=int(exact_atom_limit) and len(cls)<=int(exact_clause_limit):
        return minimum_weight_hitting_set_bb(cls,weights=weights,max_size=max_size)
    return greedy_weighted_hitting_set(cls,weights=weights,max_size=max_size)
