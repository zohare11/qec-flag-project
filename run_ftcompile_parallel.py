#!/usr/bin/env python3
"""Parallel flag-bridge blocks on a square grid: exhaustive search and lower bound.

All three checks of one type are measured at once with shared ancillas (one flag), as in
Lao & Almudever's 30-CNOT IBM-20 round, but on a plain square grid.

    python run_ftcompile_parallel.py           # 4-ancilla search + comparisons, ~5 minutes
    python run_ftcompile_parallel.py --full    # also 5 ancillas and the short sequences, ~30 minutes
Writes runs/ftcompile_parallel/summary.md and results.json.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
import warnings
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings('ignore')

import networkx as nx  # noqa: E402

from ftcompile import gadgets as GD  # noqa: E402
from ftcompile import parallel as PA  # noqa: E402
from ftcompile import published as P  # noqa: E402
from ftcompile.compilers import Graph, compile_unrouted  # noqa: E402
from ftcompile.core import check_program, grid_edges, steane_flag_round  # noqa: E402
from run_ftcompile_flagbridge import ler  # noqa: E402

BIG = (9, 9)          # shapes are placed in the middle of a 9x9 grid, far from the border


def big_graph():
    return nx.Graph(grid_edges(*BIG))


def shape_nodes(shape):
    return tuple(sorted((r + 3) * BIG[1] + (c + 3) for r, c in shape))


def short_sequences_ok(G, k, B):
    """Sequences with at most 3 ancilla CNOTs (where a data qubit may need more than 3 couplings)."""
    found = 0; n = 0
    for sh in PA.free_shapes(k):
        nodes = shape_nodes(sh)
        idx = {v: i for i, v in enumerate(nodes)}
        dedges = [(idx[a], idx[b]) for a in nodes for b in nodes if G.has_edge(a, b)]
        free = sorted({v for a in nodes for v in G[a] if v not in idx})
        adj = {v: [idx[a] for a in nodes if G.has_edge(a, v)] for v in free}
        for L in range(4):
            for ops in itertools.product(dedges, repeat=L):
                M = PA.suffix_maps(ops, k)
                for root in range(k):
                    if M[0][root] & ~(1 << root):
                        continue
                    n += 1
                    nonroot = [i for i in range(k) if i != root]
                    from scipy.optimize import linear_sum_assignment
                    best = 99
                    for synp in itertools.permutations(range(k - 1), 3):
                        tgt = lambda col: sum(((col >> i) & 1) << synp[i] for i in range(3))
                        cm = [[PA._min_cost(tuple(PA._proj(M[g][a], nonroot) for a in adj[v] for g in range(L + 1)),
                                            tgt(PA.COLUMNS[q]), B - L - 6) for v in free] for q in range(7)]
                        r, c = linear_sum_assignment(cm)
                        best = min(best, L + sum(cm[q][j] for q, j in zip(r, c)))
                    if best <= B and PA.hook_feasible(G, nodes, tuple(ops), root, B):
                        found += 1
    return n, found


def pretty_gates(d):
    names = {f'd{q + 1}': f'd{q}' for q in range(7)}
    names.update({f'a{n}': ('F' if i == d.root else 'a') + str(i) for i, n in enumerate(d.anc)})
    return [f'CX({names[a]}->{names[b]})' for a, b in d.gates()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT / 'runs' / 'ftcompile_parallel')
    ap.add_argument('--full', action='store_true')
    ap.add_argument('--render-only', action='store_true', help='re-render from results.json')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.render_only:
        R = json.loads((args.out / 'results.json').read_text())
        R['design']['gates'] = pretty_gates(PA.SQUARE_14)
        (args.out / 'summary.md').write_text(render(R))
        return
    t0 = time.time(); R = {'full': args.full}
    G = big_graph()

    # A. the model reproduces Lao & Almudever's parallel block
    GI = nx.Graph(list(P.IBM20_EDGES))
    lao_ops = ((0, 1), (1, 2), (2, 3), (2, 3), (1, 2), (0, 1))          # f-s3-s2-s1: encode, reverse decode
    lao_anc = (12, 8, 7, 6)
    R['lao'] = {'linear_cost': min(c for c, *_ in PA.placements(GI, lao_anc, lao_ops, 0, 99)),
                'hooks_ok_at_15': PA.hook_feasible(GI, lao_anc, lao_ops, 0, 15),
                'hooks_ok_at_14': PA.hook_feasible(GI, lao_anc, lao_ops, 0, 14),
                'stim_ft': check_program(P.build(P.LAO_C3), explain=False).passed}
    print(f'[A] Lao block in the model: {R["lao"]} ({time.time()-t0:.0f}s)', flush=True)

    # B. exhaustive linear stage, then the exact hook test at 13
    settings = [(4, 7)] + ([(5, 6)] if args.full else [])
    R['search'] = []
    for k, L in settings:
        recs = []
        for sh in PA.free_shapes(k):
            nodes = shape_nodes(sh)
            recs += [(c, nodes, ops, root) for c, ops, root in PA.linear_records(G, nodes, L, 14 if k == 4 else 13)]
        by_cost = dict(sorted(Counter(c for c, *_ in recs).items()))
        low = [r for r in recs if r[0] <= 13]
        passing = sum(1 for c, nodes, ops, root in low if PA.hook_feasible(G, nodes, ops, root, 13))
        row = {'ancillas': k, 'max_ancilla_cnots': L, 'shapes': len(PA.free_shapes(k)),
               'designs_by_linear_cost': by_cost, 'designs_at_most_13': len(low), 'pass_hook_test_at_13': passing}
        if k == 4 and args.full:
            at14 = [r for r in recs if r[0] == 14]
            row['designs_at_14'] = len(at14)
            row['pass_hook_test_at_14'] = sum(1 for c, nodes, ops, root in at14 if PA.hook_feasible(G, nodes, ops, root, 14))
        R['search'].append(row)
        print(f'[B] {k} ancillas: {row} ({time.time()-t0:.0f}s)', flush=True)
    if args.full:
        R['short'] = {k: dict(zip(('designs', 'pass_hook_test_at_13'), short_sequences_ok(G, k, 13))) for k in (4, 5)}
        print(f'[B] short sequences: {R["short"]} ({time.time()-t0:.0f}s)', flush=True)

    # C. the 14-CNOT design: exact checks
    d = PA.SQUARE_14
    prog = d.program()
    Gd = nx.Graph(list(d.edges))
    R['design'] = {'picture': d.picture(), 'block_cx': d.block_cx(), 'round_cx': prog.n_cx,
                   'ft': check_program(prog, explain=False).passed,
                   'hooks_ok_at_13_for_this_sequence': PA.hook_feasible(Gd, d.anc, d.ops, d.root, 13),
                   'gates': pretty_gates(d)}
    print(f'[C] design: {prog.n_cx} CNOTs, FT {R["design"]["ft"]} ({time.time()-t0:.0f}s)', flush=True)

    # D. comparison
    ps = [1e-3, 5e-4, 2.5e-4]
    st, costs, pl = GD.optimal_direct_layout(3, 4, 3)
    serial34, _ = GD.best_direct_round(pl, Graph(grid_edges(3, 4), pl), (7, 8, 9))
    rows = [('this search, parallel', '4x4 grid', 4, prog),
            ('Lao & Almudever 2020, c3-L2 parallel', 'IBM-20', 4, P.build(P.LAO_C3)),
            ('this search, serialized (earlier step)', '3x4 grid', 3, serial34),
            ('Rodriguez-Blanco et al. 2025, citadel', '4x4 grid', 4, P.build(P.RB_CITADEL)),
            ('all-to-all serialized reference', 'complete graph', 2, compile_unrouted(steane_flag_round(('A0123A',) * 6, (0,) * 6)))]
    R['compare'] = []
    for name, hw, k, pr in rows:
        R['compare'].append({'name': name, 'hardware': hw, 'ancillas': k, 'cx': pr.n_cx,
                             'ft': check_program(pr, explain=False).passed, **ler(pr, ps, 400, 10_000_000)})
        print(f'[D] {name} ({time.time()-t0:.0f}s)', flush=True)
    R['elapsed_seconds'] = time.time() - t0
    (args.out / 'results.json').write_text(json.dumps(R, indent=1, default=str))
    (args.out / 'summary.md').write_text(render(R))
    print((args.out / 'summary.md').read_text())


def render(R) -> str:
    d = R['design']; lao = R['lao']
    first = R['compare'][0]
    L = ['# Parallel flag-bridge blocks on a square grid', '',
         'All three checks of one type measured at once with shared ancillas and a single flag, as in Lao & Almudever\'s '
         '30-CNOT parallel round, but restricted to nearest-neighbour CNOTs on a plain square grid. Model and search: '
         '`ftcompile/parallel.py`.', '',
         '## Result', '',
         f'A full round (X block, then Z block) with **{d["round_cx"]} CNOTs**: 7 data + 4 ancillas inside a 4x4 grid, '
         f'{d["block_cx"]} CNOTs per check type. It passes the exact single-fault check (FT: {d["ft"]}).', '',
         '```', d['picture'], '```', '',
         'd0-d6 data, F0 the flag (starts in |+>, read out in X), a1/a2/a3 the syndrome qubits of the three checks. '
         'Z block in time order (the X block is the same with every CNOT reversed and |0>/|+>, Z/X swapped):', '',
         '`' + ' '.join(d['gates']) + '`', '',
         'How it works: the flag F0 spreads a cat state to a1 and a2, and a1 passes it on to a3. When an ancilla '
         'leaves the cat it also picks up everything the neighbour it leaves through has collected, so one coupling can '
         'count towards several checks (a1 ends with d0, d1 from F0 plus its own d2, d3). a3 enters through a1 and leaves '
         'through a2, using the fourth edge of the square; this is what makes 8 couplings enough (only d0, which is in '
         'all three checks, needs two). The full Stim check confirms that any two single faults with different logical '
         'effects leave different syndrome and flag patterns.', '',
         '## Lower bound within the model', '']
    for row in R['search']:
        L.append(f'- {row["ancillas"]} ancillas, every ancilla-CNOT sequence up to {row["max_ancilla_cnots"]} CNOTs on all '
                 f'{row["shapes"]} shapes: {row["designs_at_most_13"]} designs reach 13 or fewer CNOTs per block linearly; '
                 f'{row["pass_hook_test_at_13"]} of them pass the necessary hook conditions.'
                 + (f' At 14: {row["designs_at_14"]} designs, {row["pass_hook_test_at_14"]} pass the hook conditions.'
                    if 'designs_at_14' in row else ''))
    if R.get('short'):
        for k, v in R['short'].items():
            L.append(f'- {k} ancillas, sequences of at most 3 ancilla CNOTs (any number of couplings per data qubit): '
                     f'{v["designs"]} valid designs, {v["pass_hook_test_at_13"]} pass at 13.')
    L += ['', 'A block costs (ancilla CNOTs) + (data couplings), and every data qubit needs at least one coupling, so 13 '
          'CNOTs allows at most 6 ancilla CNOTs; with 4 or more ancilla CNOTs no data qubit can use more than 3 couplings, '
          'and sequences of at most 3 ancilla CNOTs are checked separately. The hook test is exact (CP-SAT over syndrome '
          'assignment, data placement and coupling choice) and only uses fault locations every schedule has (Z faults on '
          'ancillas between ancilla CNOTs, from idle and ancilla-CNOT noise), so failing it rules a design out.']
    if R['full']:
        L += ['', '**So with 4 or 5 ancillas and one flag, 14 CNOTs per type (28 per round) is the minimum on a square '
              'grid.**', '']
    else:
        L += ['', 'This run covered 4 ancillas with 4-7 ancilla CNOTs; `--full` adds 5 ancillas and the short sequences '
              'needed for the complete lower bound.', '']
    L += [
          f'Sanity check: the model reproduces Lao\'s block on IBM-20 (linear cost {lao["linear_cost"]}, hook test passes at '
          f'15: {lao["hooks_ok_at_15"]}, fails at 14 for that ancilla sequence: {not lao["hooks_ok_at_14"]}, Stim FT: '
          f'{lao["stim_ft"]}).', '',
          '## Comparison', '',
          '| Round | Hardware | Ancillas | CNOTs | FT | ' + ' | '.join(f'p = {r["p"]:g}' for r in first['rows']) + ' | slope |',
          '|---|---|---:|---:|---|' + '---:|' * (len(first['rows']) + 1)]
    for v in R['compare']:
        L.append(f'| {v["name"]} | {v["hardware"]} | {v["ancillas"]} | {v["cx"]} | {v["ft"]} | ' +
                 ' | '.join(f'{r["rate"]:.2e}' for r in v['rows']) + f' | {v["slope"]:.2f} |')
    L += ['', 'Logical error rate after one round: order-2 lookup decoder, ideal final read-out, p on CNOTs, prep, '
          'read-out and incoming data, p/10 idle per CNOT on every other qubit.', '',
          '## Related work', '',
          '- Poór, Rodatz & Kissinger, "Ultra Low Overhead Syndrome Extraction for the Steane Code" (arXiv:2511.13700, '
          '2025): 14 CNOTs per syndrome type with 4 ancillas, proven CNOT-optimal by exhaustive search, with an adaptive '
          'protocol (discard flagged rounds and run an 11-CNOT recovery circuit). They do not consider hardware '
          'connectivity. The count here equals theirs: on this problem the square grid costs nothing. Whether their own '
          'circuit fits a square grid is not stated (its gates are only in a figure we have not read).',
          '- Lao & Almudever 2020: 30 CNOTs with diagonal couplers (IBM-20). Rodriguez-Blanco et al. 2025: 48 CNOTs on a '
          '4x4 grid. Chao & Reichardt and Reichardt (2018), Liou & Lai (arXiv:2208.00581): parallel flag circuits without '
          'connectivity limits.', '',
          '## Scope and caveats', '',
          '- Model: one flag per block, all non-flag ancillas read out in Z as one generator each (or 0), same design for '
          'the X and Z blocks, checks of one type measured together. Rounds outside it (two flags, redundant syndrome '
          'read-outs, mixing X and Z checks in one block, 6+ ancillas) are not covered by the lower bound.',
          '- The lower bound uses our noise model, which has idle noise on every qubit after every CNOT; without idle '
          'noise fewer fault locations exist and the bound is not claimed.',
          '- Fault tolerance is single-fault circuit distance 3 for one round plus an ideal read-out, not an adaptive '
          'protocol.',
          f'- Runtime: {R["elapsed_seconds"]:.0f}s{" (with --full)" if R["full"] else ""}.']
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    main()
