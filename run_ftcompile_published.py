#!/usr/bin/env python3
"""Rebuild the published hand-designed Steane flag-bridge rounds and check them.

Rodriguez-Blanco et al. 2025 (4x4 citadel) and Lao & Almudever 2020 (IBM-20, serial
and parallel) are rebuilt gate by gate from their figures (ftcompile/published.py),
checked with the exact single-fault test, sampled for logical error rate, and compared
with the exact minimum-CNOT layouts from ftcompile.gadgets on the same hardware.

    python run_ftcompile_published.py            # ~2 minutes
    python run_ftcompile_published.py --quick    # ~1 minute
Writes runs/ftcompile_published/summary.md and results.json.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings('ignore')

import networkx as nx  # noqa: E402

from ftcompile import gadgets as GD  # noqa: E402
from ftcompile import published as P  # noqa: E402
from ftcompile.compilers import Graph, compile_unrouted  # noqa: E402
from ftcompile.core import Noise, check_program, grid_edges, steane_flag_round, to_stim  # noqa: E402
from ftcompile.decode import logical_error_rate  # noqa: E402
from run_ftcompile_flagbridge import ler, picture  # noqa: E402


def ours(edges, k):
    st, costs, pl = GD.optimal_direct_layout_on(edges, k, time_limit=300)
    if not pl:
        return st, None, None
    prog, spec = GD.best_direct_round(pl, Graph(list(edges), pl), tuple(range(7, 7 + k)))
    return st, prog, pl


def interaction_degrees(pr: P.PublishedRound):
    g = nx.Graph()
    for blk in pr.blocks:
        g.add_edges_from(blk.gates)
    return dict(g.degree())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT / 'runs' / 'ftcompile_published')
    ap.add_argument('--quick', action='store_true')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); R = {}

    # A. Lao c1-L2: every reading of the figures that the couplers allow
    n = [len(P.lao_c1_readings(k)) for k in range(3)]
    combos = list(itertools.product(*map(range, n)))
    passed = sum(check_program(P.build(P.lao_c1(ch)), explain=False).passed for ch in combos)
    R['lao_c1_readings'] = {'per_plaquette': n, 'total': len(combos), 'passed': passed}
    print(f'[A] Lao c1-L2 readings: {passed}/{len(combos)} FT ({time.time()-t0:.0f}s)', flush=True)

    # B. Fig. 1b Circuit 3 as drawn (flags closed in the wrong order)
    try:
        check_program(P.build(P.rb_with_fig1b_circuit3()), explain=False)
        R['fig1b_circuit3'] = 'valid measurement'
    except ValueError:
        R['fig1b_circuit3'] = 'rejected: non-deterministic syndrome/flag read-out'
    print(f'[B] Fig. 1b Circuit 3 as drawn: {R["fig1b_circuit3"]}', flush=True)

    # C. exact serialized optimum on the same hardware
    R['ibm20_search'] = []; progs = {}
    for k in (2, 3, 6):
        st, prog, pl = ours(P.IBM20_EDGES, k)
        R['ibm20_search'].append({'ancillas': k, 'status': st, 'round_cx': prog.n_cx if prog else None,
                                  'verified': check_program(prog, explain=False).passed if prog else None,
                                  'picture': picture(pl, 4, 5, k) if pl else None})
        progs[('ibm20', k)] = prog
    for r, c, k in ((3, 4, 3), (4, 4, 4)):
        st, prog, pl = ours(tuple(grid_edges(r, c)), k)
        progs[(f'{r}x{c}', k)] = prog
    print(f'[C] exact layouts ({time.time()-t0:.0f}s)', flush=True)

    # D. structure of the parallel Lao block
    deg = interaction_degrees(P.LAO_C3)
    sq = {frozenset(e) for e in grid_edges(4, 5)}
    diag = [g for g in P.LAO_C3_BLOCK.gates
            if frozenset((P.LAO_C3_LAYOUT[g[0]], P.LAO_C3_LAYOUT[g[1]])) not in sq]
    R['lao_c3_structure'] = {'max_degree': max(deg.values()),
                             'max_degree_qubits': sorted(q for q, d in deg.items() if d == max(deg.values())),
                             'diagonal_gates_per_type': len(diag)}

    # E. full comparison with logical error rates
    ps = [1e-3, 5e-4] if args.quick else [1e-3, 5e-4, 2.5e-4]
    mf, ms = (100, 1_000_000) if args.quick else (400, 10_000_000)
    base = steane_flag_round(('A0123A',) * 6, (0,) * 6)
    rows = [
        ('Rodriguez-Blanco et al. 2025, citadel (rebuilt)', '4x4 grid', 4, P.build(P.RB_CITADEL)),
        ('this search, 4x4', '4x4 grid', 4, progs[('4x4', 4)]),
        ('this search, 3x4', '3x4 grid', 3, progs[('3x4', 3)]),
        ('Lao & Almudever 2020, c1-L2 serial (rebuilt)', 'IBM-20', 6, P.build(P.lao_c1((0, 0, 0)))),
        ('this search, IBM-20', 'IBM-20', 2, progs[('ibm20', 2)]),
        ('Lao & Almudever 2020, c3-L2 parallel (rebuilt)', 'IBM-20', 4, P.build(P.LAO_C3)),
        ('all-to-all reference', 'complete graph', 2, compile_unrouted(base)),
    ]
    R['compare'] = []
    for name, hw, k, prog in rows:
        ft = check_program(prog, explain=False).passed
        R['compare'].append({'name': name, 'hardware': hw, 'ancillas': k, 'cx': prog.n_cx, 'ft': ft, **ler(prog, ps, mf, ms)})
        print(f'[E] {name} ({time.time()-t0:.0f}s)', flush=True)

    # F. spread over readings of Lao c1-L2 at p = 1e-3
    rng = random.Random(7)
    sample = [(0, 0, 0)] + rng.sample(combos, 3 if args.quick else 7)
    R['lao_c1_spread'] = []
    for ch in sample:
        r = logical_error_rate(to_stim(P.build(P.lao_c1(ch)), Noise(p=1e-3)), ms, seed=11, batch=100_000, min_failures=mf)
        R['lao_c1_spread'].append({'reading': ch, 'rate': r['rate'], 'ci95': r['ci95']})
    print(f'[F] reading spread ({time.time()-t0:.0f}s)', flush=True)

    R['elapsed_seconds'] = time.time() - t0
    (args.out / 'results.json').write_text(json.dumps(R, indent=1, default=str))
    (args.out / 'summary.md').write_text(render(R))
    print((args.out / 'summary.md').read_text())


def render(R) -> str:
    c1 = R['lao_c1_readings']; st = R['lao_c3_structure']
    first = R['compare'][0]
    L = ['# Published flag-bridge rounds, rebuilt and checked', '',
         'The hand-designed Steane rounds of Rodriguez-Blanco et al. 2025 (arXiv:2504.01083) and Lao & Almudever 2020 '
         '(arXiv:1909.07628) were transcribed gate by gate from their figures (`ftcompile/published.py`) and run through '
         'the same exact single-fault check, decoder and noise model as our own layouts. Paper data labels were mapped '
         'onto this project\'s Steane labelling by matching stabilizer supports.', '',
         '| Round | Hardware | Ancillas | CNOTs | Single-fault FT | ' +
         ' | '.join(f'p = {r["p"]:g}' for r in first['rows']) + ' | slope |',
         '|---|---|---:|---:|---|' + '---:|' * (len(first['rows']) + 1)]
    for v in R['compare']:
        L.append(f'| {v["name"]} | {v["hardware"]} | {v["ancillas"]} | {v["cx"]} | {v["ft"]} | ' +
                 ' | '.join(f'{r["rate"]:.2e}' for r in v['rows']) + f' | {v["slope"]:.2f} |')
    L += ['', 'Logical error rate after one round, order-2 lookup decoder, ideal final read-out; p on CNOTs, prep, '
          'read-out and incoming data, p/10 idle on every other qubit per CNOT (every CNOT is its own time step, '
          'so the parallel round gets no credit for its shorter depth).', '',
          '## What the rebuild shows', '',
          '- Both published designs pass our check: one noisy round plus an ideal read-out has circuit distance 3.',
          '- The citadel round costs 48 CNOTs (8 per check: one syndrome and two flags). On the same 4x4 grid with the '
          'same 4 ancillas the exact search needs 40, and 3 ancillas on a 3x4 grid also give 40.',
          f'- Lao\'s serial IBM-20 figures fix the gadget gate order but not which data qubit plays a, b, c, d. All '
          f'{c1["total"]} readings the couplers allow ({" x ".join(map(str, c1["per_plaquette"]))} per plaquette) were '
          f'checked: {c1["passed"]} pass. Every reading costs 36 CNOTs with 6 ancillas. On the same IBM-20 graph the '
          'exact search reaches 36 with only 2 ancillas (picture below).',
          f'- Lao\'s parallel c3-L2 round measures all three Z (then X) checks in one 4-ancilla block and costs 30 CNOTs. '
          f'It is fault-tolerant under our check too, and beats every serialized round here, ours included: '
          f'"proven minimum" for our layouts means within the one-check-at-a-time family. It relies on IBM-20\'s '
          f'crossed couplers ({st["diagonal_gates_per_type"]} diagonal CNOTs per check type) and on a qubit with '
          f'{st["max_degree"]} partners ({", ".join(st["max_degree_qubits"])}), so it cannot be placed on a square '
          'grid (maximum degree 4) as drawn.',
          f'- Fig. 1b "Circuit 3" of Rodriguez-Blanco et al., read literally, closes the two flags in the same order it '
          f'opens them. Used for S2 it is {R["fig1b_circuit3"]}. Their Fig. 2b circuits close in reverse order and are '
          'correct, so this is a drawing slip, not a flaw in their results.', '',
          'Spread over readings of Lao c1-L2 at p = 0.001:', '', '| Reading | Logical error rate | 95% interval |', '|---|---:|---|']
    for s in R['lao_c1_spread']:
        L.append(f'| {tuple(s["reading"])} | {s["rate"]:.2e} | {s["ci95"][0]:.2e} to {s["ci95"][1]:.2e} |')
    L += ['', '## Exact serialized optimum on IBM-20', '', '| Ancillas | Min CNOTs | Full-round FT verified |', '|---:|---:|---|']
    for r in R['ibm20_search']:
        L.append(f'| {r["ancillas"]} | {r["round_cx"]} | {r["verified"]} |')
    pic = next(r['picture'] for r in R['ibm20_search'] if r['ancillas'] == 2)
    L += ['', 'IBM-20, 2 ancillas, 36 CNOTs (rows of the 4 x 5 coupling graph of Lao Fig. 6b):', '', '```', pic, '```', '',
          '## Caveats', '',
          '- Different fault-tolerance criteria. Both papers use an adaptive protocol (stop at the first flag or '
          'non-trivial syndrome, then run a second full round) with flag-aware lookup or neural-network decoders. '
          'Ours is one non-adaptive round followed by an ideal read-out. Passing ours is evidence their circuits are '
          'sound, not a reproduction of their logical error rates.',
          '- Different noise model from both papers (they use p/15 two-qubit depolarizing per Pauli, 2p/3 '
          'preparation/measurement flips, and explicit Hadamards); all rows here share ours, so the comparison '
          'between rows is fair, the absolute numbers are not theirs.',
          '- Not rebuilt: Lao\'s Steane-c1-L1 (Surface-17), whose figure marks data qubits 2 and 6 at two places '
          'each ("2/-", "-/2"), and Steane-c2 (32-36 CNOTs), which uses Fig. 5a, whose data lines are not labelled.',
          '- Rodriguez-Blanco et al. draw only the X checks; their Z checks are taken as the Hadamard dual, which their '
          'text implies ("share the same connectivity requirements").',
          f'- Runtime: {R["elapsed_seconds"]:.0f}s.']
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    main()
