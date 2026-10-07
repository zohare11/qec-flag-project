#!/usr/bin/env python3
"""Flag-bridge gadgets vs hand-designed layouts.

Let data couple to a flag as well as to the syndrome qubit (the "flag-bridge"
idea of Lao & Almudever 2020 and Rodriguez-Blanco et al. 2025), find the
exact minimum-CNOT layout on several grids with CP-SAT, verify every round with
the full Stim single-fault check, and compare logical error rates with the
earlier routed rounds.

    python run_ftcompile_flagbridge.py            # ~5 minutes
    python run_ftcompile_flagbridge.py --big      # also 6x6 with 5 ancillas (~+3 minutes)
Writes runs/ftcompile_flagbridge/summary.md and results.json.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings('ignore')

from ftcompile import gadgets as GD  # noqa: E402
from ftcompile import placement as PL  # noqa: E402
from ftcompile.compilers import Graph, compile_bridge, compile_unrouted  # noqa: E402
from ftcompile.core import (CHECKS, GRID_EDGES, GRID_PLACEMENT, Noise, check_program, grid_edges,  # noqa: E402
                            steane_flag_round, to_stim)
from ftcompile.decode import logical_error_rate  # noqa: E402

CHECK_NAMES = ('X0', 'X1', 'X2', 'Z0', 'Z1', 'Z2')
# Earlier routed rounds (data couple only to the syndrome qubit), see runs/ftcompile_placement/summary.md
OLD_CURRENT = (GRID_PLACEMENT, ('B3201B',) * 6, (1,) * 6)
OLD_BEST = ({0: 10, 1: 3, 2: 2, 3: 4, 4: 9, 5: 1, 6: 11, 7: 6, 8: 0, 9: 8, 10: 7}, ('B3201B',) * 6, (0,) * 6)


def picture(pl, rows, cols, n_anc):
    names = {q: f'd{q}' for q in range(7)}
    names.update({7 + i: f'a{i}' for i in range(n_anc)})
    inv = {n: q for q, n in pl.items()}
    return '\n'.join(' '.join(names.get(inv.get(r * cols + c, -1), '..') for c in range(cols)) for r in range(rows))


def routed_old(pl, labels, hubs):
    lr = steane_flag_round(labels, hubs)
    st, paths, cx = PL.solve(PL.build(PL.round_tables(lr), pl), 'cx')
    assert st == 'feasible'
    return compile_bridge(lr, Graph(GRID_EDGES, pl), 'shortest', overrides=paths)


def ler(prog, ps, min_fail, max_shots):
    rows = []
    for i, p in enumerate(ps):
        r = logical_error_rate(to_stim(prog, Noise(p=p)), max_shots, seed=100 + i, batch=100_000, min_failures=min_fail)
        rows.append({'p': p, 'rate': r['rate'], 'failures': r['failures'], 'shots': r['shots']})
    pts = [(math.log(r['p']), math.log(r['rate'])) for r in rows if r['rate'] > 0]
    mx = statistics.fmean(a for a, _ in pts); my = statistics.fmean(b for _, b in pts)
    slope = sum((a - mx) * (b - my) for a, b in pts) / sum((a - mx) ** 2 for a, _ in pts)
    return {'rows': rows, 'slope': slope}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT / 'runs' / 'ftcompile_flagbridge')
    ap.add_argument('--big', action='store_true')
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--render-only', action='store_true', help='re-render from results.json')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.render_only:
        (args.out / 'summary.md').write_text(render(json.loads((args.out / 'results.json').read_text())))
        return
    t0 = time.time(); R = {}

    # A. which splits of a support between syndrome and flags have a certified pattern
    R['splits'] = {CHECK_NAMES[c]: {'one_flag': sum(GD.pattern_for(c, s) is not None for s in GD.all_splits(False)),
                                     'two_flags': sum(GD.pattern_for(c, s) is not None for s in GD.all_splits(True))}
                   for c in range(6)}
    print(f'[A] certified splits ({time.time()-t0:.0f}s)', flush=True)

    # B. exact minimum-CNOT all-direct layouts
    settings = [(2, 5, 3), (3, 4, 3), (3, 4, 4), (4, 4, 4), (4, 4, 6), (4, 5, 5), (5, 5, 5), (4, 5, 6), (5, 5, 6)] \
        + ([(6, 6, 5)] if args.big else [])
    if args.quick:
        settings = [(3, 4, 3), (5, 5, 6)]
    R['layouts'] = []; progs = {}
    for r, c, k in settings:
        st, costs, pl = GD.optimal_direct_layout(r, c, k)
        row = {'grid': f'{r}x{c}', 'ancillas': k, 'status': st, 'support_costs': costs}
        if pl:
            res = GD.best_direct_round(pl, Graph(grid_edges(r, c), pl), tuple(range(7, 7 + k)))
            prog, spec = res
            row.update({'round_cx': prog.n_cx, 'verified': check_program(prog, explain=False).passed,
                        'placement': pl, 'picture': picture(pl, r, c, k),
                        'gadgets': [{'check': CHECK_NAMES[i], 'tokens': p.tokens, 'couplers': p.couplers,
                                     'roles': {kk: f'a{v - 7}' for kk, v in roles.items()}} for i, (p, roles) in enumerate(spec)]})
            progs[(r, c, k)] = prog
        R['layouts'].append(row)
        print(f'[B] {r}x{c}, {k} ancillas: {row.get("round_cx")} CNOTs ({time.time()-t0:.0f}s)', flush=True)

    # C. logical error rates
    ps = [1e-3, 5e-4] if args.quick else [1e-3, 5e-4, 2.5e-4]
    mf, ms = (100, 1_000_000) if args.quick else (200, 6_000_000)
    base = steane_flag_round(('A0123A',) * 6, (0,) * 6)
    cases = {'routed, current layout (3x4)': routed_old(*OLD_CURRENT),
             'routed, best placement (3x4)': routed_old(*OLD_BEST),
             'flag-bridge, 3x4, 3 ancillas': progs.get((3, 4, 3)),
             'flag-bridge, 5x5, 6 ancillas': progs.get((5, 5, 6)),
             'no routing needed (all-to-all reference)': compile_unrouted(base)}
    R['ler'] = {}
    for name, prog in cases.items():
        if prog is None:
            continue
        R['ler'][name] = {'cx': prog.n_cx, 'ft': check_program(prog, explain=False).passed, **ler(prog, ps, mf, ms)}
        print(f'[C] {name} ({time.time()-t0:.0f}s)', flush=True)
    R['elapsed_seconds'] = time.time() - t0
    (args.out / 'results.json').write_text(json.dumps(R, indent=1, default=str))
    (args.out / 'summary.md').write_text(render(R))
    print((args.out / 'summary.md').read_text())


def render(R) -> str:
    L = ['# Flag-bridge gadgets: matching hand-designed layouts automatically', '',
         'Change from the earlier family: a data CNOT may target a flag (inside that flag\'s window) instead of the '
         'syndrome qubit, so flags double as bridges, as in Lao & Almudever (2020) and Rodriguez-Blanco et al. (2025). '
         'The four (or more) ancillas are generic: each check picks which one is its syndrome qubit and which are its flags. '
         'No remote CNOTs are used. Every round below passes the exact full-round single-fault check '
         '(circuit distance >= 3, idle noise included).', '',
         '## Every split of a support between syndrome and flags is realizable', '']
    sp = R['splits']
    L.append('For each check, every way of assigning its four data qubits to the syndrome qubit or a flag has a '
             f'certified pattern: one flag {sp["X0"]["one_flag"]}/16 splits, two flags {sp["X0"]["two_flags"]}/65 '
             f'(all six checks: {all(v["one_flag"] == 16 and v["two_flags"] == 65 for v in sp.values())}). '
             'So whether a check can be done without routing is pure geometry: one flag needs an adjacent ancilla pair '
             'whose neighbours cover the support (6 CNOTs); two flags need a syndrome ancilla with two adjacent flag '
             'ancillas covering it (8 CNOTs).')
    L += ['', '## Exact minimum CNOTs per round (CP-SAT over all placements)', '',
          '| Grid | Ancillas | Min CNOTs per round | Gadgets per support (flags) | Full-round FT verified |',
          '|---|---:|---:|---|---|']
    for row in R['layouts']:
        g = ', '.join({6: '1', 8: '2'}[c] for c in row['support_costs']) if row['support_costs'] else '-'
        L.append(f'| {row["grid"]} | {row["ancillas"]} | {row.get("round_cx", "infeasible")} | {g} | {row.get("verified", "-")} |')
    L += ['', 'Why these are optimal for the family: each check costs 6 CNOTs only with one flag and no routing; '
          'otherwise at least 8 (a second flag) or 9 (any bridge replaces 1 CNOT by at least 4). X and Z checks share '
          'their support, so a support that cannot be done with one flag costs at least 2 x 2 extra. For every row with '
          '40, CP-SAT proves that no placement gives all three supports a one-flag gadget, so 40 is the minimum there. '
          '36 appears only with 6 ancillas on a large enough grid (not on 4x4); 3 ancillas already reach 40 on 3x4. '
          'Two-row grids cannot avoid routing at all.', '']
    for row in R['layouts']:
        if (row['grid'], row['ancillas']) in (('3x4', 3), ('5x5', 6)) and row.get('picture'):
            L += [f'{row["grid"]}, {row["ancillas"]} ancillas ({row["round_cx"]} CNOTs):', '', '```', row['picture'], '```', '']
    g3 = next((r for r in R['layouts'] if r['grid'] == '3x4' and r['ancillas'] == 3), None)
    if g3 and g3.get('gadgets'):
        L += ['Gadgets of the 3x4 round (tokens: digits = support positions, A/B = flag CNOTs; couplers: which ancilla each data CNOT uses):', '',
              '| Check | Syndrome | Flags | Tokens | Couplers |', '|---|---|---|---|---|']
        for gd in g3['gadgets']:
            fl = ', '.join(v for k, v in gd['roles'].items() if k != 'S')
            L.append(f'| {gd["check"]} | {gd["roles"]["S"]} | {fl} | `{gd["tokens"]}` | `{gd["couplers"]}` |')
        L.append('')
    L += ['## Logical error rate after one round', '', 'Order-2 lookup decoder, ideal final read-out; same noise model as before (p on CNOTs, prep, readout and incoming data; p/10 idle).', '']
    first = next(iter(R['ler'].values()))
    L += ['| Round | CNOTs | FT | ' + ' | '.join(f'p = {r["p"]:g}' for r in first['rows']) + ' | slope |',
          '|---|---:|---|' + '---:|' * (len(first['rows']) + 1)]
    for name, v in R['ler'].items():
        L.append(f'| {name} | {v["cx"]} | {v["ft"]} | ' + ' | '.join(f'{r["rate"]:.2e}' for r in v['rows']) + f' | {v["slope"]:.2f} |')
    L += ['', '## Comparison with the hand-designed layouts', '',
          '| Layout | Hardware | Ancillas | CNOTs per round | Source |', '|---|---|---:|---:|---|',
          '| Rodriguez-Blanco et al. 2025, citadel | 4x4 grid | 4 | 48 | rebuilt from their Fig. 2, FT verified |',
          '| this search | 4x4 grid | 4 | 40 | above |',
          '| this search | 3x4 grid | 3 | 40 | above |',
          '| Lao & Almudever 2020, Steane-c1-L2 (serial) | IBM-20 | 6 | 36 | rebuilt from their Figs. 1c, 4a, 8a, FT verified |',
          '| this search | IBM-20 | 2 | 36 | `run_ftcompile_published.py` |',
          '| this search | 5x5 grid | 6 | 36 | above |',
          '| Lao & Almudever 2020, Steane-c3-L2 (parallel) | IBM-20 | 4 | 30 | rebuilt from their Figs. 5b, 8c, FT verified |', '',
          'Details, logical error rates and caveats: `runs/ftcompile_published/summary.md`. The minima above are for '
          'one check at a time; Lao\'s parallel block, which measures three checks with shared ancillas, needs fewer '
          'CNOTs than any serialized round (it uses IBM-20\'s diagonal couplers and a degree-5 ancilla).', '',
          '## Scope', '',
          '- Steane code, six serialized checks, square grids, one or two flags per check.',
          f'- Runtime: {R["elapsed_seconds"]:.0f}s.']
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    main()
