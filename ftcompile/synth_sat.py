"""Exact synthesis of a parallel flag block as SAT with XOR clauses (CryptoMiniSat).

Same model as ftcompile.synth (read its docstring), encoded for a SAT solver that handles
parity natively, which is what this problem is made of.  For a fixed number of CNOT slots T
the solver either returns a block or proves none exists.

Symmetry breaking: two consecutive CNOTs on disjoint qubits are kept in a fixed order.  This
loses nothing: swapping them changes no fault's effect (a Z fault between them acts like a
fault before or after both, which are already counted).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import networkx as nx


class _Enc:
    def __init__(self):
        self.n = 0
        self.clauses: list[list[int]] = []
        self.xors: list[tuple[list[int], bool]] = []

    def var(self):
        self.n += 1
        return self.n

    def add(self, lits):
        self.clauses.append(list(lits))

    def AND(self, a, b):
        if _is_const(a):
            return b if a else _C(0)
        if _is_const(b):
            return a if b else _C(0)
        z = self.var()
        self.add([-z, a]); self.add([-z, b]); self.add([z, -a, -b])
        return z

    def XOR(self, terms):
        """Literal (or 0/1 constant) equal to the parity of positive literals and constants."""
        c = 0; vs = []
        for x in terms:
            if _is_const(x):
                c ^= x
            else:
                vs.append(x)
        if not vs:
            return _C(c)
        if len(vs) == 1 and c == 0:
            return vs[0]
        y = self.var()
        self.xors.append((vs + [y], bool(c)))           # XOR(vs) ^ y == c  <=>  y == XOR(vs) ^ c
        return y

    def OR(self, lits):
        lits = [x for x in lits if not (_is_const(x) and x == 0)]
        if any(_is_const(x) and x == 1 for x in lits):
            return _C(1)
        if not lits:
            return _C(0)
        if len(lits) == 1:
            return lits[0]
        y = self.var()
        self.add([-y] + lits)
        for x in lits:
            self.add([y, -x])
        return y

    def fix(self, x, val):
        if _is_const(x):
            if x != val:
                self.add([])
        else:
            self.add([x] if val else [-x])


class _C(int):
    """Boolean constant (distinguishable from variable ids)."""


def _is_const(x):
    return isinstance(x, _C)


def _neg(x):
    return _C(1 - x) if _is_const(x) else -x


@dataclass
class SatResult:
    status: str             # 'SAT' / 'UNSAT'
    slots: list
    data: dict              # data node -> 3-bit column
    readouts: tuple
    root: int
    anc: tuple
    seconds: float
    n_vars: int = 0
    n_clauses: int = 0

    @property
    def n_cx(self):
        return len(self.slots)


def encode(G: nx.Graph, anc, root, T: int, readouts=None, candidates=None, pairs=True, symmetry=True,
           choose_readouts=False):
    anc = tuple(anc); A = set(anc)
    nonroot = [a for a in anc if a != root]
    readouts = tuple(readouts) if readouts else tuple(nonroot[:3])
    zeros = [a for a in nonroot if a not in readouts]
    cand = tuple(sorted(candidates if candidates is not None else {n for a in anc for n in G[a] if n not in A}))
    E = _Enc()
    gates = [(u, v) for u in anc for v in anc if u != v and G.has_edge(u, v)]
    gates += [(n, a) for n in cand for a in anc if G.has_edge(n, a)]
    g = {(t, e): E.var() for t in range(T) for e in gates}
    for t in range(T):                                    # exactly one CNOT per slot
        lits = [g[(t, e)] for e in gates]
        E.add(lits)
        for i in range(len(lits)):
            for j in range(i + 1, len(lits)):
                E.add([-lits[i], -lits[j]])
    if symmetry:
        idx = {e: i for i, e in enumerate(gates)}
        for t in range(T - 1):
            for e1 in gates:
                for e2 in gates:
                    if idx[e1] > idx[e2] and not (set(e1) & set(e2)):
                        E.add([-g[(t, e1)], -g[(t + 1, e2)]])
    used = {n: E.var() for n in cand}
    for (t, e), v in g.items():
        if e[0] in used:
            E.add([-v, used[e[0]]])
    from pysat.card import CardEnc, EncType
    card = CardEnc.equals(lits=[used[n] for n in cand], bound=7, top_id=E.n, encoding=EncType.seqcounter)
    E.n = max(E.n, card.nv)
    for cl in card.clauses:
        E.add(cl)

    bits = ('r',) + cand
    S = {a: [_C(1) if (a == root and b == 'r') else _C(0) for b in bits] for a in anc}
    for t in range(T):
        new = {}
        for v in anc:
            vec = []
            for i, b in enumerate(bits):
                terms = [S[v][i]]
                for (c, w) in gates:
                    if w != v:
                        continue
                    if c in A:
                        terms.append(E.AND(g[(t, (c, w))], S[c][i]))
                    elif b == c:
                        terms.append(g[(t, (c, w))])
                vec.append(E.XOR(terms))
            new[v] = vec
        S = new
    for a in nonroot:
        E.fix(S[a][0], 0)
    if choose_readouts:
        # sel[a][j]: ancilla a reads row j; every other non-root ancilla must read 0
        sel = {a: [E.var() for _ in range(3)] for a in nonroot}
        for j in range(3):
            lits = [sel[a][j] for a in nonroot]
            E.add(lits)
            for x in range(len(lits)):
                for y in range(x + 1, len(lits)):
                    E.add([-lits[x], -lits[y]])
        for a in nonroot:
            for x in range(3):
                for y in range(x + 1, 3):
                    E.add([-sel[a][x], -sel[a][y]])
            for i in range(1, len(bits)):                       # unselected -> reads 0
                if not _is_const(S[a][i]):
                    E.add(sel[a] + [-S[a][i]])
                elif S[a][i]:
                    E.add(sel[a])
        col = {n: [E.OR([E.AND(sel[a][j], S[a][bits.index(n)]) for a in nonroot]) for j in range(3)] for n in cand}
    else:
        sel = None
        for a in zeros:
            for i in range(1, len(bits)):
                E.fix(S[a][i], 0)
        col = {n: [S[readouts[j]][bits.index(n)] for j in range(3)] for n in cand}
    for n in cand:
        if not any(_is_const(x) and x == 1 for x in col[n]):
            E.add([-used[n]] + [x for x in col[n] if not _is_const(x)])     # used -> non-zero column
        for x in col[n]:
            if _is_const(x):
                if x:
                    E.add([used[n]])
            else:
                E.add([used[n], -x])                                         # unused -> zero column
    cl = list(cand)
    for i in range(len(cl)):
        for j in range(i + 1, len(cl)):
            d = [E.XOR([col[cl[i]][k], col[cl[j]][k]]) for k in range(3)]
            lits = [-used[cl[i]], -used[cl[j]]]
            if any(_is_const(x) and x for x in d):
                continue
            E.add(lits + [x for x in d if not _is_const(x)])

    # backward Z propagation
    zb = anc + cand
    zi = {b: i for i, b in enumerate(zb)}
    Z = {a: [_C(1) if b == a else _C(0) for b in zb] for a in anc}
    hist = {T: Z}
    for t in range(T - 1, -1, -1):
        nxt = hist[t + 1]; cur = {}
        for v in anc:
            vec = []
            for i, b in enumerate(zb):
                terms = [nxt[v][i]]
                for (c, w) in gates:
                    if w != v:
                        continue
                    if c in A:
                        terms.append(E.AND(g[(t, (c, w))], nxt[c][i]))
                    elif b == c:
                        terms.append(g[(t, (c, w))])
                vec.append(E.XOR(terms))
            cur[v] = vec
        hist[t] = cur

    def syn_par(vec):
        par = E.XOR([vec[zi[n]] for n in cand])
        syn = [E.XOR([E.AND(vec[zi[n]], col[n][j]) for n in cand]) for j in range(3)]
        return syn, par

    info = {}
    for t in range(T + 1):
        for a in anc:
            syn, par = syn_par(hist[t][a])
            info[(t, a)] = (hist[t][a][zi[root]], syn, par)
    pi = [E.var() for _ in range(8)]
    E.add([-pi[0]])

    def constrain(flag, syn, par, cond=None):
        pre = [] if cond is None else [-cond]
        anyz = E.OR(syn)
        # unflagged: parity == (syndrome != 0)
        if not (_is_const(flag) and flag == 1):
            base = pre + ([] if _is_const(flag) else [flag])
            for a_, b_ in ((par, anyz), (anyz, par)):          # par -> anyz and anyz -> par
                cl_ = list(base)
                ok = False
                for lit in (_neg(a_), b_):
                    if _is_const(lit):
                        if lit == 1:
                            ok = True
                    else:
                        cl_.append(lit)
                if not ok:
                    E.add(cl_)
        # flagged: same syndrome -> same parity
        if not (_is_const(flag) and flag == 0):
            base = pre + ([] if _is_const(flag) else [-flag])
            for s in range(8):
                cl0 = list(base); dead = False
                for i in range(3):
                    lit = _neg(syn[i]) if (s >> i) & 1 else syn[i]      # literal true when syn_i differs from s_i
                    if _is_const(lit):
                        if lit == 1:
                            dead = True
                    else:
                        cl0.append(lit)
                if dead:
                    continue
                for a_, b_ in ((par, pi[s]), (pi[s], par)):
                    cl_ = list(cl0); ok = False
                    for lit in (_neg(a_), b_):
                        if _is_const(lit):
                            if lit == 1:
                                ok = True
                        else:
                            cl_.append(lit)
                    if not ok:
                        E.add(cl_)

    for (t, a), (flag, syn, par) in info.items():
        constrain(flag, syn, par)
    if pairs:
        for t in range(T):
            for (c, w) in gates:
                fw, sw, pw = info[(t + 1, w)]
                if c in A:
                    fc, sc, pc = info[(t + 1, c)]
                    constrain(E.XOR([fw, fc]), [E.XOR([sw[j], sc[j]]) for j in range(3)], E.XOR([pw, pc]),
                              g[(t, (c, w))])
                else:
                    constrain(fw, [E.XOR([sw[j], col[c][j]]) for j in range(3)], E.XOR([pw, _C(1)]), g[(t, (c, w))])
    return E, dict(g=g, used=used, col=col, gates=gates, cand=cand, readouts=readouts, sel=sel)


def solve(G, anc, root, T, readouts=None, candidates=None, threads=2, time_limit=None, assume=None, **kw):
    """assume: optional list of CNOTs (one per slot, None = free) to fix, e.g. to check a known block."""
    import pycryptosat
    t0 = time.time()
    E, h = encode(G, anc, root, T, readouts, candidates, **kw)
    s = pycryptosat.Solver(threads=threads, time_limit=time_limit) if time_limit else pycryptosat.Solver(threads=threads)
    for cl in E.clauses:
        s.add_clause(cl)
    for vs, rhs in E.xors:
        s.add_xor_clause(vs, rhs)
    lits = []
    for t, e in enumerate(assume or []):
        if e is not None:
            if (t, e) not in h['g']:
                return SatResult('UNSAT', [], {}, h['readouts'], root, tuple(anc), time.time() - t0, E.n, len(E.clauses))
            lits.append(h['g'][(t, e)])
    sat, model = s.solve(lits) if lits else s.solve()
    dt = time.time() - t0
    if sat is None:
        return SatResult('UNKNOWN', [], {}, h['readouts'], root, tuple(anc), dt, E.n, len(E.clauses))
    if not sat:
        return SatResult('UNSAT', [], {}, h['readouts'], root, tuple(anc), dt, E.n, len(E.clauses))
    val = lambda x: (x if _is_const(x) else model[x])
    slots = [e for t in range(T) for e in h['gates'] if model[h['g'][(t, e)]]]
    if h['sel']:
        h['readouts'] = tuple(next(a for a, v in h['sel'].items() if model[v[j]]) for j in range(3))
    data = {n: sum(int(bool(val(h['col'][n][j]))) << j for j in range(3)) for n in h['cand'] if model[h['used'][n]]}
    return SatResult('SAT', slots, data, h['readouts'], root, tuple(anc), dt, E.n, len(E.clauses))

def gate_order(G: nx.Graph, anc, candidates=None):
    """The gate list (and so the symmetry-breaking order) the encoder uses."""
    anc = tuple(anc); A = set(anc)
    cand = tuple(sorted(candidates if candidates is not None else {n for a in anc for n in G[a] if n not in A}))
    gates = [(u, v) for u in anc for v in anc if u != v and G.has_edge(u, v)]
    return gates + [(n, a) for n in cand for a in anc if G.has_edge(n, a)]


def canonical(slots, gates):
    """Reorder adjacent CNOTs on disjoint qubits into the encoder's canonical order (same block)."""
    idx = {e: i for i, e in enumerate(gates)}
    out = list(slots)
    changed = True
    while changed:
        changed = False
        for t in range(len(out) - 1):
            a, b = out[t], out[t + 1]
            if not (set(a) & set(b)) and idx[a] > idx[b]:
                out[t], out[t + 1] = b, a
                changed = True
    return out

