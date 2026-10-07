"""Published hand-designed Steane flag-bridge rounds, rebuilt gate by gate.

Sources (circuits transcribed from the figures):

* Rodriguez-Blanco, Nguyen, Whaley, arXiv:2504.01083 (2025): 4x4 "citadel" layout,
  Fig. 2a (placement) and Fig. 2b (the three X-check circuits, one syndrome + two flags
  each).  Their Z checks "share the same connectivity"; we use the Hadamard dual.
* Lao & Almudever, arXiv:1909.07628 (PRA 2020), on the IBM-20 (Tokyo) coupling graph of
  their Fig. 6b:
    - Steane-c1-L2 (Fig. 8a): six serialized checks with the two-ancilla gadgets of
      Figs. 1c and 4a.  The figures fix the gadget gate order but not which data qubit
      plays a/b/c/d, so every reading consistent with the coupling graph is enumerated.
    - Steane-c3-L2 (Fig. 8c + Fig. 5b): all three Z (then X) checks measured at once by
      a four-ancilla flag-bridge block.  Fully determined by the figures; reading the
      data lines of Fig. 5b as qubits 1..7 gives exactly their stabilizers.

Every circuit is a list of blocks.  A block measures one or more stabilizers with its
own ancillas; gates are given in one convention ('X' check as drawn, or 'Z' check as
drawn) and the other type is the Hadamard dual (every CX reversed, |0>/|+> and Z/X
read-out swapped).  Paper data labels are mapped onto this project's Steane labelling
by matching the stabilizer supports.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

from .core import CHECKS, SUPPORTS, Op, PhysicalProgram, grid_edges


@dataclass(frozen=True)
class Block:
    checks: dict          # syndrome ancilla name -> stabilizer index (0, 1, 2 in the paper's numbering order)
    flags: tuple          # flag ancilla names
    gates: tuple          # ((control, target), ...) as drawn
    convention: str       # 'X' or 'Z': the check type the gates are drawn for


@dataclass(frozen=True)
class PublishedRound:
    name: str
    hardware: str
    edges: tuple          # coupling graph on node ids
    n_nodes: int
    layout: dict          # name ('d1'..'d7', ancilla names) -> node
    data_map: dict        # paper data label (int) -> project data index
    stab_map: dict        # paper stabilizer index -> project support index
    blocks: tuple         # measured for X then for Z

    @property
    def ancillas(self):
        return sorted(k for k in self.layout if not k.startswith('d'))


def _check_maps(paper_supports, data_map, stab_map):
    for i, sup in enumerate(paper_supports):
        assert tuple(sorted(data_map[q] for q in sup)) == SUPPORTS[stab_map[i]], (i, sup)


def build(pr: PublishedRound) -> PhysicalProgram:
    """Physical program: X-type blocks, then Z-type blocks; every CX must be a coupler."""
    E = {frozenset(e) for e in pr.edges}
    node = lambda n: pr.layout[n]
    ops: list[Op] = []
    syn_keys = [None] * 6; flag_keys = [()] * 6
    for ctype in ('X', 'Z'):
        base = 0 if ctype == 'X' else 3
        for blk in pr.blocks:
            cis = [base + pr.stab_map[k] for k in blk.checks.values()]
            ci0 = min(cis)
            syn_prep, flag_prep = ('RX', 'R') if ctype == 'X' else ('R', 'RX')
            syn_meas, flag_meas = ('MX', 'M') if ctype == 'X' else ('M', 'MX')
            for s in blk.checks:
                ops.append(Op(syn_prep, (node(s),), tag=f'c{ci0}'))
            for f in blk.flags:
                ops.append(Op(flag_prep, (node(f),), tag=f'c{ci0}'))
            for i, (a, b) in enumerate(blk.gates):
                if ctype != blk.convention:
                    a, b = b, a
                assert frozenset((node(a), node(b))) in E, f'{pr.name}: {a}-{b} is not a coupler'
                ops.append(Op('CX', (node(a), node(b)), tag=f'c{ci0}.i{i}', kind='direct'))
            for s, k in blk.checks.items():
                ci = base + pr.stab_map[k]
                ops.append(Op(syn_meas, (node(s),), tag=f'c{ci}', key=f'syn{ci}'))
                syn_keys[ci] = f'syn{ci}'
            fk = []
            for f in blk.flags:
                ops.append(Op(flag_meas, (node(f),), tag=f'c{ci0}', key=f'flag{ci0}{f}'))
                fk.append(f'flag{ci0}{f}')
            flag_keys[ci0] = flag_keys[ci0] + tuple(fk)
    data = {pr.data_map[int(k[1:])]: v for k, v in pr.layout.items() if k.startswith('d')}
    return PhysicalProgram(ops, pr.n_nodes, data, dict(data), tuple(syn_keys), tuple(flag_keys),
                           meta={'published': pr.name})


# --------------------------------------------------------------------------
# Rodriguez-Blanco et al. 2025, 4x4 citadel (Fig. 2)
# --------------------------------------------------------------------------
RB_SUPPORTS = ((1, 2, 3, 4), (2, 3, 5, 6), (3, 4, 6, 7))           # S1, S2, S3 (Eq. 2)
RB_DATA_MAP = {1: 3, 2: 1, 3: 0, 4: 2, 5: 5, 6: 4, 7: 6}
RB_STAB_MAP = {0: 0, 1: 1, 2: 2}
#   .  d3 d4  .
#   d2 a2 a3 d5
#   d1 a1 a4 d6
#   .  .  d7  .
RB_LAYOUT = {'d3': 1, 'd4': 2, 'd2': 4, 'a2': 5, 'a3': 6, 'd5': 7,
             'd1': 8, 'a1': 9, 'a4': 10, 'd6': 11, 'd7': 14}
RB_BLOCKS = (
    # S1: syndrome a2 (|+>), flags a1, a3; both flags opened by the syndrome (star)
    Block({'a2': 0}, ('a1', 'a3'), (('a2', 'a1'), ('a2', 'a3'), ('a2', 'd2'), ('a2', 'd3'),
                                     ('a1', 'd1'), ('a3', 'd4'), ('a2', 'a3'), ('a2', 'a1')), 'X'),
    # S2: syndrome a2, flag a3 opened by a2, flag a4 opened by a3 (chain)
    Block({'a2': 1}, ('a3', 'a4'), (('a2', 'a3'), ('a3', 'a4'), ('a2', 'd2'), ('a2', 'd3'),
                                     ('a3', 'd5'), ('a4', 'd6'), ('a3', 'a4'), ('a2', 'a3')), 'X'),
    # S3: syndrome a4, flag a3 opened by a4, flag a2 opened by a3 (chain)
    Block({'a4': 2}, ('a3', 'a2'), (('a4', 'a3'), ('a3', 'a2'), ('a4', 'd7'), ('a4', 'd6'),
                                     ('a2', 'd3'), ('a3', 'd4'), ('a3', 'a2'), ('a4', 'a3')), 'X'),
)
_check_maps(RB_SUPPORTS, RB_DATA_MAP, RB_STAB_MAP)

RB_CITADEL = PublishedRound('Rodriguez-Blanco et al. 2025, 4x4 citadel (Fig. 2)', '4x4 grid',
                            tuple(grid_edges(4, 4)), 16, RB_LAYOUT, RB_DATA_MAP, RB_STAB_MAP, RB_BLOCKS)

# Fig. 1b "Circuit 3" as drawn closes the flags in the same order it opens them
# (syndrome->flag1, then flag1->flag2).  Used for S2 this leaves flag 2 entangled with
# the syndrome qubit; Fig. 2b uses the correct reversed order.
RB_FIG1B_CIRCUIT3_S2 = Block({'a2': 1}, ('a3', 'a4'), (('a2', 'a3'), ('a2', 'd2'), ('a3', 'a4'), ('a2', 'd3'),
                                                        ('a3', 'd5'), ('a4', 'd6'), ('a2', 'a3'), ('a3', 'a4')), 'X')


def rb_with_fig1b_circuit3() -> PublishedRound:
    blocks = (RB_BLOCKS[0], RB_FIG1B_CIRCUIT3_S2, RB_BLOCKS[2])
    return PublishedRound('citadel with Fig. 1b Circuit 3 as drawn for S2', '4x4 grid', tuple(grid_edges(4, 4)),
                          16, RB_LAYOUT, RB_DATA_MAP, RB_STAB_MAP, blocks)


# --------------------------------------------------------------------------
# Lao & Almudever 2020 on IBM-20 (Fig. 6b): 4 x 5 grid plus crossed squares
# --------------------------------------------------------------------------
def ibm20_edges() -> tuple:
    e = set(grid_edges(4, 5))
    for r, c in ((0, 1), (0, 3), (1, 0), (1, 2), (2, 1), (2, 3)):       # squares with both diagonals
        e.add((r * 5 + c, (r + 1) * 5 + c + 1)); e.add((r * 5 + c + 1, (r + 1) * 5 + c))
    return tuple(sorted(tuple(sorted(x)) for x in e))


IBM20_EDGES = ibm20_edges()
LAO_SUPPORTS = ((1, 2, 4, 5), (1, 3, 4, 7), (4, 5, 6, 7))          # S1 green, S2 red, S3 blue (Fig. 2)
LAO_DATA_MAP = {1: 1, 2: 3, 3: 5, 4: 0, 5: 2, 6: 6, 7: 4}
LAO_STAB_MAP = {0: 0, 1: 1, 2: 2}
_check_maps(LAO_SUPPORTS, LAO_DATA_MAP, LAO_STAB_MAP)
N = lambda r, c: r * 5 + c

# Fig. 8c + Fig. 5b (Z checks as drawn; data lines are qubits 1..7 top to bottom)
LAO_C3_LAYOUT = {'d3': N(0, 1), 'd1': N(0, 2), 'd7': N(0, 3), 'd2': N(1, 0), 'd5': N(2, 1), 'd4': N(2, 3),
                 'd6': N(3, 2), 's1': N(1, 1), 's2': N(1, 2), 's3': N(1, 3), 'f': N(2, 2)}
LAO_C3_BLOCK = Block({'s1': 0, 's2': 1, 's3': 2}, ('f',),
                     (('f', 's3'), ('s3', 's2'), ('d6', 'f'), ('d3', 's2'), ('d7', 's3'), ('s2', 's1'),
                      ('d2', 's1'), ('d1', 's2'), ('d5', 's1'), ('d4', 's2'), ('d5', 'f'), ('s2', 's1'),
                      ('d4', 'f'), ('s3', 's2'), ('f', 's3')), 'Z')
LAO_C3 = PublishedRound('Lao & Almudever 2020, Steane-c3-L2 (Figs. 5b, 8c)', 'IBM-20', IBM20_EDGES, 20,
                        LAO_C3_LAYOUT, LAO_DATA_MAP, LAO_STAB_MAP, (LAO_C3_BLOCK,))

# Fig. 8a: serialized checks, two ancillas per plaquette (shared by its X and Z check)
LAO_C1_LAYOUT = {'d1': N(0, 1), 'd3': N(0, 2), 'd2': N(1, 0), 'd4': N(2, 2), 'd7': N(2, 3), 'd5': N(3, 1),
                 'd6': N(3, 4), 'g1': N(1, 1), 'g2': N(2, 1), 'r1': N(1, 2), 'r2': N(1, 3),
                 'b1': N(3, 2), 'b2': N(3, 3)}
LAO_C1_ANCILLAS = (('g1', 'g2'), ('r1', 'r2'), ('b1', 'b2'))      # green S1, red S2, blue S3
# Z-check gadgets as drawn (s syndrome |0>, f flag |+>; a..d the check's data qubits)
GADGET_1C = (('f', 's'), ('c', 'f'), ('a', 's'), ('d', 'f'), ('b', 's'), ('f', 's'))
GADGET_4A = (('f', 's'), ('d', 'f'), ('a', 's'), ('b', 's'), ('c', 's'), ('f', 's'))


def lao_c1_readings(stab: int) -> list[tuple[str, Block]]:
    """Every assignment of the gadgets of Figs. 1c / 4a to plaquette `stab` that the
    IBM-20 couplers allow (which ancilla is s, which data qubit is a, b, c, d)."""
    E = {frozenset(e) for e in IBM20_EDGES}
    adj = lambda x, y: frozenset((LAO_C1_LAYOUT[x], LAO_C1_LAYOUT[y])) in E
    sup = [f'd{q}' for q in LAO_SUPPORTS[stab]]
    out = []
    for s, f in permutations(LAO_C1_ANCILLAS[stab]):
        if not adj(s, f):
            continue
        for gname, gadget, flag_letters in (('1c', GADGET_1C, 'cd'), ('4a', GADGET_4A, 'd')):
            for perm in permutations(sup):
                letters = dict(zip('abcd', perm))
                if not all(adj(letters[x], f if x in flag_letters else s) for x in 'abcd'):
                    continue
                rename = {'s': s, 'f': f, **letters}
                gates = tuple((rename[a], rename[b]) for a, b in gadget)
                label = f'{gname} s={s} f={f} ' + ''.join(letters[x][1] for x in 'abcd')
                out.append((label, Block({s: stab}, (f,), gates, 'Z')))
    return out


def lao_c1(choice: tuple[int, int, int]) -> PublishedRound:
    blocks = tuple(lao_c1_readings(k)[i][1] for k, i in enumerate(choice))
    return PublishedRound(f'Lao & Almudever 2020, Steane-c1-L2 (Fig. 8a), reading {choice}', 'IBM-20',
                          IBM20_EDGES, 20, LAO_C1_LAYOUT, LAO_DATA_MAP, LAO_STAB_MAP, blocks)
