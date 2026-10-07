"""Parallel flag-bridge blocks: the three checks of one type measured at once.

Model (written for the Z checks; the X block is the Hadamard dual on the same qubits)
-----------------------------------------------------------------------------------
* k ancillas.  One of them, the root, starts in |+> and is read out in X: it is the
  only flag.  The others start in |0> and are read out in Z.  Three of them are the
  syndrome qubits of the three checks; any others must read 0.
* Any sequence of CNOTs between neighbouring ancillas, and data couplings CX(d -> a)
  in any gap of that sequence (data are always controls).
* The block is a valid measurement iff the root's |+> ends up on the root alone.

Lao & Almudever's Fig. 5b block is one instance (path f-s3-s2-s1, encode then
reverse decode).  Rodriguez-Blanco's and our serialized gadgets are one-check special
cases.

Everything except fault tolerance is linear over GF(2).  If a bit is injected at
ancilla a in gap g, the rest of the sequence carries it to a fixed set of Z read-outs
(its *offered vector*).  Each data qubit needs a set of offered vectors, at ancillas
next to it, that XOR to its column (which checks contain it).  So:

1. ``linear_records``: enumerate every ancilla-CNOT sequence up to length L (built
   backwards, so each step updates one column of the suffix map), and for every root
   the cheapest data placement (assignment problem).  Exhaustive: no symmetry pruning
   inside a sequence, because swapping two commuting CNOTs changes the gap between them.
2. ``hook_feasible``: an exact CP-SAT test of necessary fault-tolerance conditions.  A
   Z fault on an ancilla at a gap boundary (idle or ancilla-CNOT noise) spreads to a
   fixed set of data qubits and either reaches the root (flagged) or not.  Unflagged,
   the data error must be correctable from its syndrome alone; flagged, errors with the
   same syndrome must share a logical class.  If no syndrome assignment, placement and
   coupling choice within the CNOT budget satisfies this, no fault-tolerant block exists.
3. ``certify``: build the full round (X block, then Z block) and run the exact Stim
   single-fault check, searching coupling choices and orders.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from functools import lru_cache

import networkx as nx

from .core import SUPPORT_MASKS, SUPPORTS, check_program, grid_edges
from .published import Block, PublishedRound, build

COLUMNS = tuple(sum(1 << i for i in range(3) if q in SUPPORTS[i]) for q in range(7))   # bit i: q in check i


# --------------------------------------------------------------------------
# Shapes, maps, fault propagation
# --------------------------------------------------------------------------
def free_shapes(k: int) -> list[tuple]:
    """Connected k-cell shapes on the square grid up to rotation and reflection."""
    shapes = {frozenset([(0, 0)])}
    for _ in range(k - 1):
        shapes = {s | {(r + dr, c + dc)} for s in shapes for (r, c) in s
                  for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)) if (r + dr, c + dc) not in s}

    def norm(s):
        mr = min(r for r, _ in s); mc = min(c for _, c in s)
        return tuple(sorted((r - mr, c - mc) for r, c in s))
    out = set()
    for s in shapes:
        forms = []
        for f in range(8):
            t = s
            if f & 1: t = {(r, -c) for r, c in t}
            if f & 2: t = {(-r, c) for r, c in t}
            if f & 4: t = {(c, r) for r, c in t}
            forms.append(norm(t))
        out.add(min(forms))
    return sorted(out)


def connected_subsets(G: nx.Graph, k: int, within=None) -> list[tuple]:
    """All connected k-node subsets of G (optionally only using nodes in `within`)."""
    allowed = set(within if within is not None else G.nodes)
    out = set()
    for s in sorted(allowed):
        frontier = {frozenset([s])}
        for _ in range(k - 1):
            frontier = {S | {w} for S in frontier for v in S for w in G[v]
                        if w in allowed and w not in S and w > s}
        out |= frontier
    return sorted(tuple(sorted(S)) for S in out)


def suffix_maps(ops, k):
    """M[g][a]: ancilla bitmask that a bit injected at ancilla a in gap g ends on."""
    L = len(ops); M = [None] * (L + 1)
    cur = [1 << i for i in range(k)]; M[L] = tuple(cur)
    for g in range(L - 1, -1, -1):
        p, c = ops[g]; cur = list(cur); cur[p] ^= cur[c]; M[g] = tuple(cur)
    return M


def z_propagation(ops, k):
    """For a Z fault on ancilla a at the start of gap g: {g': ancilla bitmask carrying Z at gap g'}."""
    L = len(ops); out = {}
    for a in range(k):
        for g in range(L + 1):
            P = 1 << a; seq = {g: P}
            for gg in range(g, L):
                p, c = ops[gg]
                if (P >> c) & 1:          # Z on a CNOT target spreads to its control
                    P ^= 1 << p
                seq[gg + 1] = P
            out[(a, g)] = seq
    return out


def _syn(D): return tuple(bin(D & m).count('1') & 1 for m in SUPPORT_MASKS)
def _par(D): return bin(D).count('1') & 1


def harmless(D: int) -> bool:
    """A data Z error (bitmask) the syndrome alone decodes correctly: equivalent to weight <= 1."""
    return _par(D) == (_syn(D) != (0, 0, 0))


@lru_cache(maxsize=None)
def _min_cost(vecs, target, maxr):
    vecs = tuple(sorted(set(v for v in vecs if v)))
    for r in range(1, maxr + 1):
        for c in itertools.combinations(vecs, r):
            x = 0
            for v in c:
                x ^= v
            if x == target:
                return r
    return 99


def _proj(v, nonroot):
    return sum(((v >> j) & 1) << t for t, j in enumerate(nonroot))


def readout_bases(m: int) -> list[tuple]:
    """Images (t0, t1, t2) of the three check syndromes in the read-out space GF(2)^m of the m
    non-flag ancillas: read-out j measures the product of the checks i with bit j of t_i set.

    Read-outs may be any stabilizer products (as in Poor, Rodatz & Kissinger's circuit) as long as
    the syndrome can be recovered.  Only their 3-dimensional image W matters: a change of basis
    inside W is a linear map T on syndromes, and every T in GL(3,2) is induced by an automorphism of
    the Steane code (the data permutation sending column c(q) to T c(q)).  Data placement is already
    optimized over all permutations, and the linear targets and hook conditions transform covariantly,
    so one basis per W covers every case: m = 3 has one W, m = 4 has 15 (one or more read-outs are
    then redundant or always 0)."""
    if m == 3:
        return [(1, 2, 4)]
    out = []
    for u in range(1, 1 << m):
        W = [x for x in range(1, 1 << m) if bin(x & u).count('1') % 2 == 0]
        basis, span = [], {0}
        for x in W:
            if x not in span:
                basis.append(x); span |= {y ^ x for y in span}
            if len(basis) == 3:
                break
        out.append(tuple(basis))
    return out


def _target(T, col):
    x = 0
    for i in range(3):
        if (col >> i) & 1:
            x ^= T[i]
    return x


# --------------------------------------------------------------------------
# 1. Linear stage
# --------------------------------------------------------------------------
def linear_records(G: nx.Graph, anc_nodes, L: int, B: int):
    """Every (cost, ops, root) with an ancilla-CNOT sequence of length <= L whose cheapest
    data placement gives a block of at most B CNOTs (data needing <= 3 couplings each)."""
    from scipy.optimize import linear_sum_assignment
    k = len(anc_nodes)
    idx = {n: i for i, n in enumerate(anc_nodes)}
    dedges = [(idx[a], idx[b]) for a in anc_nodes for b in anc_nodes if G.has_edge(a, b)]
    free = sorted({n for a in anc_nodes for n in G[a] if n not in idx})
    adj = {n: tuple(idx[a] for a in anc_nodes if G.has_edge(a, n)) for n in free}
    cache = {}; recs = []

    def cost_of(root, hist):
        if len(free) < 7:                     # not enough neighbours for the data
            return 99
        nonroot = [i for i in range(k) if i != root]
        offered = tuple(frozenset(_proj(v, nonroot) for v in hist[i]) for i in range(k))
        key = (root, offered)
        if key not in cache:
            best = 99
            for T in readout_bases(len(nonroot)):
                cm = [[_min_cost(tuple(v for a in adj[n] for v in offered[a]), _target(T, COLUMNS[q]), 3)
                       for n in free] for q in range(7)]
                r, c = linear_sum_assignment(cm)
                best = min(best, sum(cm[q][j] for q, j in zip(r, c)))
            cache[key] = best
        return cache[key]

    def dfs(M, hist, seq, depth):
        if seq:
            for root in range(k):
                if M[root] & ~(1 << root):
                    continue
                c = len(seq) + cost_of(root, hist)
                if c <= B:
                    recs.append((c, seq, root))
        if depth == L:
            return
        for p, c in dedges:                   # prepend CX(p -> c)
            M2 = list(M); M2[p] = M[p] ^ M[c]; M2 = tuple(M2)
            hist2 = tuple(h | {M2[i]} if i == p else h for i, h in enumerate(hist))
            dfs(M2, hist2, ((p, c),) + seq, depth + 1)

    M = tuple(1 << i for i in range(k))
    dfs(M, tuple(frozenset([M[i]]) for i in range(k)), (), 0)
    return recs


def _slot_combos(slots, target, maxr):
    items = [x for x in slots if x[1]]
    out = []
    for r in range(1, maxr + 1):
        for c in itertools.combinations(items, r):
            x = 0
            for _, v in c:
                x ^= v
            if x == target:
                out.append(tuple(s for s, _ in c))
    return out


# --------------------------------------------------------------------------
# 2. Exact test of necessary fault-tolerance conditions
# --------------------------------------------------------------------------
def hook_feasible(G: nx.Graph, anc_nodes, ops, root: int, B: int, return_solution=False):
    """Is there a read-out assignment, data placement and coupling choice with at most B CNOTs
    in the block that passes the gap-boundary hook conditions?  CP-SAT, exact."""
    from ortools.sat.python import cp_model
    k = len(anc_nodes); L = len(ops); budget = B - L
    if budget < 7:
        return False
    M = suffix_maps(ops, k)
    if M[0][root] & ~(1 << root):
        return False
    Z = z_propagation(ops, k)
    nonroot = [i for i in range(k) if i != root]
    free = sorted({n for a in anc_nodes for n in G[a] if n not in anc_nodes})
    adj = {n: [i for i, a in enumerate(anc_nodes) if G.has_edge(a, n)] for n in free}
    positions = sorted(Z)
    flagged = {pos: (Z[pos][L] >> root) & 1 for pos in positions}
    maxr = budget - 6
    for T in readout_bases(len(nonroot)):
        tgt = lambda col: _target(T, col)
        opts = []
        for n in free:
            slots = [((a, g), _proj(M[g][a], nonroot)) for a in adj[n] for g in range(L + 1)]
            for q in range(7):
                for cs in _slot_combos(slots, tgt(COLUMNS[q]), maxr):
                    opts.append((q, n, cs))
        if any(not any(o[0] == q for o in opts) for q in range(7)):
            continue
        m = cp_model.CpModel()
        y = [m.NewBoolVar('') for _ in opts]
        for q in range(7):
            m.AddExactlyOne(y[i] for i, o in enumerate(opts) if o[0] == q)
        for n in free:
            m.AddAtMostOne(y[i] for i, o in enumerate(opts) if o[1] == n)
        m.Add(sum(len(o[2]) * y[i] for i, o in enumerate(opts)) <= budget)
        pi = {s: m.NewBoolVar('') for s in range(8)}
        m.Add(pi[0] == 0)

        def xor_of(terms):
            b = m.NewBoolVar(''); t = m.NewIntVar(0, 7, '')
            m.Add(sum(terms) == 2 * t + b)
            return b
        for (a, g) in positions:
            P = Z[(a, g)]
            d = []
            for q in range(7):
                terms = []
                for i, o in enumerate(opts):
                    if o[0] == q and sum(1 for (b, gg) in o[2] if gg >= g and (P[gg] >> b) & 1) % 2:
                        terms.append(y[i])
                d.append(terms)
            par = xor_of([t for q in range(7) for t in d[q]])
            syn = [xor_of([t for q in range(7) if (SUPPORT_MASKS[i] >> q) & 1 for t in d[q]]) for i in range(3)]
            if not flagged[(a, g)]:
                m.AddMaxEquality(par, syn)           # parity odd exactly when the syndrome is non-zero
            else:
                for s in range(8):
                    e = m.NewBoolVar('')
                    lits = [syn[i] if (s >> i) & 1 else syn[i].Not() for i in range(3)]
                    m.AddBoolAnd(lits).OnlyEnforceIf(e)
                    m.AddBoolOr([lit.Not() for lit in lits]).OnlyEnforceIf(e.Not())
                    m.Add(par == pi[s]).OnlyEnforceIf(e)
        solver = cp_model.CpSolver(); solver.parameters.num_workers = 2
        solver.parameters.max_time_in_seconds = 300
        st = solver.Solve(m)
        if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if not return_solution:
                return True
            choice = {}; place = {}
            for i, o in enumerate(opts):
                if solver.Value(y[i]):
                    choice[o[0]] = o[2]; place[o[0]] = o[1]
            return T, place, choice
        if st == cp_model.UNKNOWN:
            raise RuntimeError('CP-SAT timed out')
    return False


# --------------------------------------------------------------------------
# 3. Circuits and the full Stim check
# --------------------------------------------------------------------------
@dataclass
class ParallelDesign:
    rows: int
    cols: int
    anc: tuple                  # ancilla nodes (index order used by ops)
    root: int                   # index into anc
    ops: tuple                  # ((control idx, target idx), ...) ancilla CNOTs in time order
    basis: tuple                # read-out basis (see readout_bases): non-root ancilla j reads the checks i with bit j of basis[i]
    place: dict                 # data index -> node
    choice: dict                # data index -> ((anc idx, gap), ...)
    order: dict = field(default_factory=dict)   # (anc idx, gap) -> data order there

    @property
    def edges(self):
        return tuple(grid_edges(self.rows, self.cols))

    def block_cx(self):
        return len(self.ops) + sum(len(v) for v in self.choice.values())

    def gates(self):
        per = {}
        for q, slots in sorted(self.choice.items()):
            for s in slots:
                per.setdefault(s, []).append(q)
        out = []
        for g in range(len(self.ops) + 1):
            for a in range(len(self.anc)):
                for q in self.order.get((a, g), per.get((a, g), [])):
                    out.append((f'd{q + 1}', f'a{self.anc[a]}'))
            if g < len(self.ops):
                p, c = self.ops[g]
                out.append((f'a{self.anc[p]}', f'a{self.anc[c]}'))
        return tuple(out)

    def to_round(self, name='parallel block') -> PublishedRound:
        k = len(self.anc)
        nonroot = [i for i in range(k) if i != self.root]
        if k - 1 != 3:
            raise NotImplementedError('only designs whose non-root ancillas are all syndrome qubits')
        layout = {f'd{q + 1}': n for q, n in self.place.items()}
        layout.update({f'a{n}': n for n in self.anc})
        checks = {}
        for j in range(3):
            combo = tuple(i for i in range(3) if (self.basis[i] >> j) & 1)
            checks[f'a{self.anc[nonroot[j]]}'] = combo[0] if len(combo) == 1 else combo
        blk = Block(checks, (f'a{self.anc[self.root]}',), self.gates(), 'Z')
        return PublishedRound(name, f'{self.rows}x{self.cols} grid', self.edges, self.rows * self.cols, layout,
                              {q + 1: q for q in range(7)}, {0: 0, 1: 1, 2: 2}, (blk,))

    def program(self):
        return build(self.to_round())

    def picture(self):
        names = {n: f'd{q}' for q, n in self.place.items()}
        names.update({n: ('F' if i == self.root else 'a') + str(i) for i, n in enumerate(self.anc)})
        return '\n'.join(' '.join(f'{names.get(r * self.cols + c, ".."):>3}' for c in range(self.cols))
                         for r in range(self.rows))

    def compact(self):
        """Same design on the smallest grid holding it."""
        nodes = list(self.anc) + list(self.place.values())
        C0 = self.cols
        rs = [n // C0 for n in nodes]; cs = [n % C0 for n in nodes]
        r0, c0 = min(rs), min(cs); R, C = max(rs) - r0 + 1, max(cs) - c0 + 1
        f = lambda n: (n // C0 - r0) * C + (n % C0 - c0)
        return ParallelDesign(R, C, tuple(f(n) for n in self.anc), self.root, self.ops, self.basis,
                              {q: f(n) for q, n in self.place.items()}, self.choice, self.order)


def certify(design: ParallelDesign, options: dict, tries: int = 60, max_choice: int = 3000, seed: int = 0):
    """Search coupling choices (options[q] = candidate slot sets) and orders for a design that passes
    the full-round Stim check.  Choices are screened with the gap-boundary hook conditions first."""
    rng = random.Random(seed)
    k = len(design.anc); L = len(design.ops)
    Z = z_propagation(design.ops, k)
    total = 1
    for q in range(7):
        total *= len(options[q])
    pool = (itertools.product(*[options[q] for q in range(7)]) if total <= max_choice else
            (tuple(rng.choice(options[q]) for q in range(7)) for _ in range(max_choice)))
    good = []
    for ch in pool:
        choice = dict(enumerate(ch))
        if _hooks_ok(Z, L, design.root, choice):
            good.append(choice)
    for t in range(tries if good else 0):
        choice = good[t] if t < len(good) else rng.choice(good)
        per = {}
        for q, slots in choice.items():
            for s in slots:
                per.setdefault(s, []).append(q)
        d = ParallelDesign(design.rows, design.cols, design.anc, design.root, design.ops, design.basis,
                           design.place, choice, {s: rng.sample(v, len(v)) for s, v in per.items()})
        try:
            if check_program(d.program(), explain=False).passed:
                return d, len(good)
        except ValueError:
            continue
    return None, len(good)


def _hooks_ok(Z, L, root, choice):
    flagged = {}
    for (a, g), P in Z.items():
        D = 0
        for q, slots in choice.items():
            if sum(1 for (b, gg) in slots if gg >= g and (P[gg] >> b) & 1) % 2:
                D |= 1 << q
        if not (P[L] >> root) & 1:
            if not harmless(D):
                return False
        elif flagged.setdefault(_syn(D), _par(D)) != _par(D):
            return False
    return flagged.get((0, 0, 0), 0) == 0


def placements(G: nx.Graph, anc_nodes, ops, root: int, B: int):
    """Cheapest data placement per syndrome assignment with block cost <= B:
    [(cost, basis, place, options)] where options[q] lists the minimal slot sets."""
    from scipy.optimize import linear_sum_assignment
    k = len(anc_nodes); L = len(ops); M = suffix_maps(ops, k)
    if M[0][root] & ~(1 << root):
        return []
    nonroot = [i for i in range(k) if i != root]
    free = sorted({n for a in anc_nodes for n in G[a] if n not in anc_nodes})
    adj = {n: [i for i, a in enumerate(anc_nodes) if G.has_edge(a, n)] for n in free}
    out = []
    if len(free) < 7:
        return out
    for T in readout_bases(len(nonroot)):
        tgt = lambda col: _target(T, col)
        cost = []; opts = {}
        for q in range(7):
            row = []
            for n in free:
                slots = [((a, g), _proj(M[g][a], nonroot)) for a in adj[n] for g in range(L + 1)]
                found = []
                for r in range(1, 4):
                    found = _slot_combos(slots, tgt(COLUMNS[q]), r)
                    found = [f for f in found if len(f) == r]
                    if found:
                        break
                row.append(len(found[0]) if found else 99); opts[(q, n)] = found
            cost.append(row)
        rr, cc = linear_sum_assignment(cost)
        tot = L + sum(cost[q][j] for q, j in zip(rr, cc))
        if tot <= B:
            place = {int(q): free[j] for q, j in zip(rr, cc)}
            out.append((tot, T, place, {q: opts[(q, place[q])] for q in range(7)}))
    return out


# --------------------------------------------------------------------------
# Found by the search (run_ftcompile_parallel.py): 14 CNOTs per block on a 4x4 grid
# --------------------------------------------------------------------------
#   .  d0 d2  .
#   d1 F0 a1 d3        F0 = root (flag), a1/a2/a3 = syndrome qubits of checks 0/1/2
#   d4 a2 a3 d6
#   .  d5  .  .
SQUARE_14 = ParallelDesign(
    rows=4, cols=4, anc=(5, 6, 9, 10), root=0,
    ops=((0, 1), (0, 2), (1, 3), (0, 1), (2, 3), (0, 2)),
    basis=(1, 2, 4),
    place={0: 1, 1: 4, 2: 2, 3: 7, 4: 8, 5: 13, 6: 11},
    choice={0: ((0, 1), (0, 5)), 1: ((0, 3),), 2: ((1, 0),), 3: ((1, 5),), 4: ((2, 4),), 5: ((2, 6),), 6: ((3, 3),)},
    order={})
