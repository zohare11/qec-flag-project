"""Flag-bridge check gadgets: data may couple to a flag instead of the syndrome qubit.

In the original family every data CNOT targets the syndrome qubit S and the flags
only touch S.  Hand-designed flag-bridge layouts (Lao & Almudever 2020;
Rodriguez-Blanco et al. 2025) also let data couple to a flag, so the flag
"bridges" data to the syndrome without remote gates.

Why that still measures the stabilizer: between its two CNOTs a flag F shares a
cat state with S, so parity collected on F is folded into S by F's second CNOT,
and F returns to a deterministic state.  (Z check: S=|0>, F=|+>, CX(F->S),
CX(d -> S or F), CX(F->S); measure S in Z and F in X.  X check: Hadamard dual.)
Correctness is not assumed: Stim refuses to build a detector error model if any
syndrome, flag or logical readout is non-deterministic, and every pattern is
single-fault checked.

A *pattern* for one check: tokens over '0'-'3' (support positions), 'A' and 'B'
(each flag's two CNOTs), plus per data token the qubit it couples to ('S', 'A' or
'B'; a flag only inside its own window).  *Roles* say which physical ancilla
plays S, A, B for that check; the four ancillas are reused with different roles.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations, permutations, product

from .core import CHECKS, LogicalRound, Noise, Op, PhysicalProgram, single_fault_check, to_stim

ANCILLAS = (7, 8, 9, 10)          # generic ancilla virtual ids (roles assigned per check)


@dataclass(frozen=True)
class Pattern:
    tokens: str                    # e.g. 'A01A23'
    couplers: str                  # per token: 'S'/'A'/'B' for data tokens, '-' for flag tokens

    @property
    def flags(self) -> tuple[str, ...]:
        return tuple(f for f in 'AB' if f in self.tokens)

    @property
    def n_cx(self) -> int:
        return len(self.tokens)

    def split(self) -> tuple[str, ...]:
        """Role each support position (0-3) couples to."""
        out = ['?'] * 4
        for t, c in zip(self.tokens, self.couplers):
            if t not in 'AB':
                out[int(t)] = c
        return tuple(out)


def build_round(spec: list[tuple[Pattern, dict]]) -> LogicalRound:
    """spec[c] = (pattern, roles) for the six checks X0..Z2; roles maps 'S','A','B' -> ancilla id."""
    ops: list[Op] = []; syn_keys = []; flag_keys = []
    for ci, ((ctype, support), (pat, roles)) in enumerate(zip(CHECKS, spec)):
        s = roles['S']
        syn_prep, flag_prep = ('R', 'RX') if ctype == 'Z' else ('RX', 'R')
        syn_meas, flag_meas = ('M', 'MX') if ctype == 'Z' else ('MX', 'M')
        ops.append(Op(syn_prep, (s,), tag=f'c{ci}'))
        for fl in pat.flags:
            ops.append(Op(flag_prep, (roles[fl],), tag=f'c{ci}'))
        for ri, (tok, cpl) in enumerate(zip(pat.tokens, pat.couplers)):
            if tok in 'AB':
                f = roles[tok]
                a, b = (f, s) if ctype == 'Z' else (s, f)
            else:
                d = support[int(tok)]; anc = roles[cpl]
                a, b = (d, anc) if ctype == 'Z' else (anc, d)
            ops.append(Op('CX', (a, b), tag=f'c{ci}.i{ri}', kind='direct'))
        ops.append(Op(syn_meas, (s,), tag=f'c{ci}', key=f'syn{ci}'))
        for fl in pat.flags:
            ops.append(Op(flag_meas, (roles[fl],), tag=f'c{ci}', key=f'flag{ci}{fl}'))
        syn_keys.append(f'syn{ci}'); flag_keys.append(tuple(f'flag{ci}{fl}' for fl in pat.flags))
    labels = tuple(p.tokens + '|' + p.couplers for p, _ in spec)
    return LogicalRound(ops, labels, tuple(r['S'] for _, r in spec), tuple(syn_keys), tuple(flag_keys))


def logical_program(lr: LogicalRound) -> PhysicalProgram:
    ident = {q: q for q in range(7)}
    return PhysicalProgram(list(lr.ops), 11, ident, dict(ident), lr.syn_keys, lr.flag_keys)


BASE = (None, None)
ROLES = {'S': 7, 'A': 9, 'B': 10}


def _isolated_ok(check: int, pat: Pattern) -> bool:
    """Valid measurement and single-fault FT counting only this check's faults (+ incoming)."""
    base = Pattern('A0123A', '-SSSS-')
    spec = [(base, ROLES)] * 6
    spec[check] = (pat, ROLES)
    lr = build_round(spec)
    keep = lambda tag: tag == 'incoming' or tag.endswith(f'c{check}') or f'c{check}.' in tag
    try:
        return single_fault_check(to_stim(logical_program(lr), Noise(), keep=keep), explain=False).passed
    except ValueError:            # Stim: non-deterministic detector/observable -> not a valid measurement
        return False


def _candidates(split: tuple[str, ...]):
    """Patterns realizing a split, most promising (widest flag windows) first."""
    flags = [f for f in 'AB' if f in split] or ['A']
    n = 4 + 2 * len(flags)
    pos_sets = []
    if len(flags) == 1:
        pos_sets = [((i, j),) for i, j in combinations(range(n), 2)]
    else:
        for i, j in combinations(range(n), 2):
            rest = [k for k in range(n) if k not in (i, j)]
            for k, l in combinations(rest, 2):
                pos_sets.append(((i, j), (k, l)))
    pos_sets.sort(key=lambda ps: -sum(b - a for a, b in ps))
    for ps in pos_sets:
        flag_at = {p: flags[fi] for fi, pair in enumerate(ps) for p in pair}
        slots = [k for k in range(n) if k not in flag_at]
        for order in permutations(range(4)):
            toks = [''] * n; cpl = [''] * n
            ok = True
            for k, f in flag_at.items():
                toks[k] = f; cpl[k] = '-'
            for slot, d in zip(slots, order):
                role = split[d]
                if role != 'S':
                    a, b = ps[flags.index(role)]
                    if not a < slot < b:
                        ok = False; break
                toks[slot] = str(d); cpl[slot] = role
            if ok:
                yield Pattern(''.join(toks), ''.join(cpl))


@lru_cache(maxsize=None)
def pattern_for(check: int, split: tuple[str, ...], max_tries: int = 400) -> Pattern | None:
    """A certified pattern realizing `split` (role per support position), or None."""
    for k, pat in enumerate(_candidates(split)):
        if k >= max_tries:
            return None
        if _isolated_ok(check, pat):
            return pat
    return None


def all_splits(two_flags: bool) -> list[tuple[str, ...]]:
    roles = 'SAB' if two_flags else 'SA'
    out = [s for s in product(roles, repeat=4)]
    return [s for s in out if (('B' in s) if two_flags else True)]


# --------------------------------------------------------------------------
# Layouts where every check gadget uses only nearest-neighbour CNOTs
# --------------------------------------------------------------------------
def check_options(placement: dict[int, int], adj, check: int, ancillas=ANCILLAS):
    """All direct (no routing) gadgets for one check under a placement:
    yields (n_cx, pattern, roles), cheapest first.  adj(u, v) -> bool on nodes."""
    from .core import CHECKS
    support = CHECKS[check][1]
    nd = lambda d, r: adj(placement[support[d]], placement[r])
    opts = []
    for s in ancillas:
        nbrs = [a for a in ancillas if a != s and adj(placement[s], placement[a])]
        for a in nbrs:                                     # one flag
            choices = [[r for r, q in (('S', s), ('A', a)) if nd(k, q)] for k in range(4)]
            for split in product(*choices):
                opts.append((6, split, {'S': s, 'A': a}))
        for a, b in permutations(nbrs, 2):                 # two flags
            choices = [[r for r, q in (('S', s), ('A', a), ('B', b)) if nd(k, q)] for k in range(4)]
            for split in product(*choices):
                if 'B' in split and 'A' in split:
                    opts.append((8, split, {'S': s, 'A': a, 'B': b}))
    out = []
    for n, split, roles in sorted(opts, key=lambda o: o[0]):
        pat = pattern_for(check, tuple(split))
        if pat is not None:
            out.append((n, pat, roles))
    return out


def direct_cost(placement, adj, ancillas=ANCILLAS):
    """Per-support cheapest direct gadget cost (X and Z checks share geometry), None if impossible."""
    from .core import CHECKS
    costs = []
    for c in range(3):
        support = CHECKS[c][1]
        best = None
        for s in ancillas:
            nbrs = [a for a in ancillas if a != s and adj(placement[s], placement[a])]
            for a in nbrs:
                if all(adj(placement[d], placement[s]) or adj(placement[d], placement[a]) for d in support):
                    best = 6; break
            if best == 6:
                break
            for a, b in permutations(nbrs, 2):
                if all(any(adj(placement[d], placement[x]) for x in (s, a, b)) for d in support):
                    best = 8 if best is None else min(best, 8)
        costs.append(best)
    return costs


def best_direct_round(placement, graph, ancillas=ANCILLAS, noise=None, max_tries=200):
    """Cheapest all-direct round under this placement that passes the full single-fault check
    (all six checks, idle noise, cross-check effects).  Returns (program, spec) or None."""
    import heapq
    from .compilers import compile_bridge
    from .core import Noise, check_program
    noise = noise or Noise()
    adj = lambda u, v: graph.g.has_edge(u, v)
    opts = [check_options(placement, adj, c, ancillas) for c in range(6)]
    if any(not o for o in opts):
        return None
    start = tuple(0 for _ in range(6))
    heap = [(sum(o[0][0] for o in opts), start)]
    seen = {start}; tries = 0
    while heap and tries < max_tries:
        cost, idx = heapq.heappop(heap); tries += 1
        spec = [(opts[c][i][1], opts[c][i][2]) for c, i in enumerate(idx)]
        prog = compile_bridge(build_round(spec), graph, 'shortest')
        if check_program(prog, noise, explain=False).passed:
            return prog, spec
        for c in range(6):
            if idx[c] + 1 < len(opts[c]):
                nxt = idx[:c] + (idx[c] + 1,) + idx[c + 1:]
                if nxt not in seen:
                    seen.add(nxt)
                    heapq.heappush(heap, (sum(opts[k][j][0] for k, j in enumerate(nxt)), nxt))
    return None


def optimal_direct_layout(rows: int, cols: int, n_anc: int, time_limit: float = 600.0):
    """Exact minimum-CNOT all-direct layout on a rows x cols grid (see optimal_direct_layout_on)."""
    from .core import grid_edges
    return optimal_direct_layout_on(grid_edges(rows, cols), n_anc, time_limit)


def optimal_direct_layout_on(edges, n_anc: int, time_limit: float = 600.0):
    """Exact minimum-CNOT all-direct layout on any coupling graph (CP-SAT).

    Every check costs 6 CNOTs with one flag (needs an adjacent ancilla pair whose
    neighbours cover the support) or 8 with two flags (a syndrome ancilla with two
    adjacent flag ancillas covering the support).  X and Z checks share supports, so
    the round costs 2 x sum over the three supports.  Returns
    (status, per-support costs, placement {virtual: node}) -- placement None if infeasible.
    """
    import networkx as nx
    from ortools.sat.python import cp_model
    from .core import CHECKS
    G = nx.Graph(list(edges)); N = sorted(G.nodes)
    anc = list(range(7, 7 + n_anc)); Q = list(range(7)) + anc
    m = cp_model.CpModel()
    x = {(q, n): m.NewBoolVar(f'x{q}_{n}') for q in Q for n in N}
    for q in Q:
        m.AddExactlyOne(x[q, n] for n in N)
    for n in N:
        m.AddAtMostOne(x[q, n] for q in Q)
    pos = {q: m.NewIntVar(0, len(N) - 1, f'p{q}') for q in anc}
    for q in anc:
        m.Add(pos[q] == sum(n * x[q, n] for n in N))
    for a, b in zip(anc, anc[1:]):                 # ancillas are interchangeable
        m.Add(pos[a] < pos[b])
    cache = {}

    def adj(u, v):
        k = (min(u, v), max(u, v))
        if k not in cache:
            terms = []
            for a_, b_ in G.edges:
                for n1, n2 in ((a_, b_), (b_, a_)):
                    t = m.NewBoolVar('')
                    m.AddBoolAnd([x[k[0], n1], x[k[1], n2]]).OnlyEnforceIf(t)
                    m.AddBoolOr([x[k[0], n1].Not(), x[k[1], n2].Not()]).OnlyEnforceIf(t.Not())
                    terms.append(t)
            z = m.NewBoolVar(f'adj{k}'); m.AddMaxEquality(z, terms); cache[k] = z
        return cache[k]

    cost_terms = []; picks = []
    for j in range(3):
        sup = CHECKS[j][1]; opts = []
        for s, a in combinations(anc, 2):
            y = m.NewBoolVar(f'one{j}_{s}_{a}'); opts.append((y, 6))
            m.AddImplication(y, adj(s, a))
            for d in sup:
                m.AddBoolOr([adj(d, s), adj(d, a)]).OnlyEnforceIf(y)
        for s in anc:
            for a, b in combinations([q for q in anc if q != s], 2):
                y = m.NewBoolVar(f'two{j}_{s}_{a}_{b}'); opts.append((y, 8))
                m.AddImplication(y, adj(s, a)); m.AddImplication(y, adj(s, b))
                for d in sup:
                    m.AddBoolOr([adj(d, s), adj(d, a), adj(d, b)]).OnlyEnforceIf(y)
        m.AddExactlyOne(y for y, _ in opts)
        cost_terms += [c * y for y, c in opts]; picks.append(opts)
    m.Minimize(sum(cost_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit; solver.parameters.num_workers = 2
    st = solver.Solve(m)
    name = solver.StatusName(st)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return name, None, None
    placement = {q: next(n for n in N if solver.Value(x[q, n])) for q in Q}
    costs = [next(c for y, c in opts if solver.Value(y)) for opts in picks]
    return name, costs, placement
