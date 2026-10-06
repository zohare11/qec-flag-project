"""Small exact weighted hitting-set utilities for counterexample-guided repair.

The scheduling repair problem has at most C(6,2)=15 pairwise precedence atoms,
so an exact branch over subsets is practical and preferable to another heuristic.
The solver is lexicographic: minimize number of edits first, then weighted cost.
"""
from __future__ import annotations
from itertools import combinations
from typing import Hashable, Iterable


def normalize_clauses(clauses: Iterable[Iterable[Hashable]]) -> tuple[frozenset, ...]:
    out = []
    seen = set()
    for clause in clauses:
        c = frozenset(clause)
        if not c:
            continue
        if c not in seen:
            seen.add(c); out.append(c)
    # Remove supersets: satisfying a subset clause automatically satisfies a superset.
    keep = []
    for i, c in enumerate(out):
        if any(d < c for j, d in enumerate(out) if i != j):
            continue
        keep.append(c)
    return tuple(sorted(keep, key=lambda x: (len(x), tuple(sorted(map(str, x))))))


def covers(solution: Iterable[Hashable], clauses: Iterable[Iterable[Hashable]]) -> bool:
    s = set(solution)
    return all(bool(s.intersection(c)) for c in clauses)


def minimum_weight_hitting_set(
    clauses: Iterable[Iterable[Hashable]],
    weights: dict[Hashable, float] | None = None,
    universe: Iterable[Hashable] | None = None,
    max_size: int | None = None,
    forbidden_solutions: Iterable[Iterable[Hashable]] = (),
) -> tuple[Hashable, ...] | None:
    """Return a lexicographically minimum-cardinality, then minimum-weight hit set.

    This intentionally uses exact subset enumeration because the Phase-10/repair
    scheduling universe contains only 15 check-pair atoms.  Deterministic ordering
    makes benchmark results reproducible.
    """
    cls = normalize_clauses(clauses)
    if not cls:
        return tuple()
    if universe is None:
        atoms = sorted(set().union(*cls), key=str)
    else:
        atoms = sorted(set(universe), key=str)
    weights = {} if weights is None else dict(weights)
    banned = {frozenset(x) for x in forbidden_solutions}
    limit = len(atoms) if max_size is None else min(int(max_size), len(atoms))

    best = None
    for k in range(1, limit + 1):
        candidates = []
        for combo in combinations(atoms, k):
            fs = frozenset(combo)
            if fs in banned or not covers(fs, cls):
                continue
            cost = sum(float(weights.get(a, 1.0)) for a in combo)
            candidates.append((cost, tuple(map(str, combo)), combo))
        if candidates:
            candidates.sort(key=lambda x: (x[0], x[1]))
            best = tuple(candidates[0][2])
            break
    return best
