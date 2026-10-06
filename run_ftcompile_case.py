#!/usr/bin/env python3
"""Case study: Steane flag round on the 3x4 grid -- does ordinary compilation keep
single-fault tolerance, and can witness-guided path repair restore it?

    python run_ftcompile_case.py                   # full run (several minutes)
    python run_ftcompile_case.py --quick           # small smoke run
    python run_ftcompile_case.py --out runs/ftcompile_steane_grid_2

Writes <out>/summary.md and <out>/results.json.  Needs: stim, qiskit, networkx.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings('ignore')

from ftcompile.core import Noise, check_program, steane_flag_round, to_stim  # noqa: E402
from ftcompile.compilers import (Graph, compile_bridge, compile_qiskit, compile_unrouted)  # noqa: E402
from ftcompile.repair import repair_paths  # noqa: E402
from ftcompile.decode import logical_error_rate  # noqa: E402

NOISE = Noise(p=1e-3)   # p for CX/prep/meas/incoming, p/10 idle -- used for the FT check and C1


def c1(res) -> float:
    return res.first_order_failure / NOISE.p


def template_rounds():
    """48 certified local flag templates x 2 syndrome hubs, same template on all six checks."""
    table = json.loads((ROOT / 'cache' / 'phase4_action_table.json').read_text())
    return [((lab,) * 6, (hub,) * 6) for hub in (0, 1) for lab in table['labels']]


def showcase_round():
    meta = json.loads((ROOT / 'cache' / 'phase7_certified_bridge_catalog.json').read_text())['metadata']
    return tuple(meta['base_labels']), tuple(meta['base_hubs'])


def describe(prog, res) -> dict:
    return {'compiler': prog.meta.get('compiler'), 'cx': prog.n_cx, 'logical_cx_kept': prog.meta.get('logical_cx_kept'),
            'swaps': prog.meta.get('swaps'), 'ft_pass': res.passed, 'conflicts': res.n_conflicts, 'C1': c1(res)}


def sweep_one(args):
    labels, hubs, budget = args
    G = Graph(); lr = steane_flag_round(labels, hubs)
    out = {'labels': labels[0], 'hub': hubs[0]}
    for key, prog in (('sabre_opt1', compile_qiskit(lr, G, routed=True, seed=0, optimization_level=1)),
                      ('sabre_default', compile_qiskit(lr, G, routed=True, seed=0, optimization_level=None)),
                      ('bridge_shortest', compile_bridge(lr, G, 'shortest')),
                      ('bridge_ancilla_first', compile_bridge(lr, G, 'ancilla_first'))):
        out[key] = describe(prog, check_program(prog, NOISE, explain=False))
    for pol in ('shortest', 'ancilla_first'):
        if out[f'bridge_{pol}']['ft_pass']:
            continue
        rr = repair_paths(lr, G, pol, max_calls=budget, noise=NOISE)
        out[f'repair_{pol}'] = {'success': rr.success, 'calls': rr.verifier_calls, 'budget_hit': rr.verifier_calls >= budget,
                                'routes_changed': len(rr.changed_routes), 'cx_before': rr.start_cx, 'cx_after': rr.final_cx,
                                'conflicts_before': rr.start_conflicts, 'conflicts_after': rr.final_conflicts}
    return out


def slope(ps, rates):
    pts = [(math.log(p), math.log(r)) for p, r in zip(ps, rates) if r > 0]
    if len(pts) < 2:
        return float('nan')
    mx = statistics.fmean(x for x, _ in pts); my = statistics.fmean(y for _, y in pts)
    return sum((x - mx) * (y - my) for x, y in pts) / sum((x - mx) ** 2 for x, _ in pts)


def ler_adaptive(circuit, min_fail, max_shots, seed):
    r = logical_error_rate(circuit, max_shots, seed=seed, batch=100_000, min_failures=min_fail)
    return {'shots': r['shots'], 'failures': r['failures'], 'rate': r['rate']}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT / 'runs' / 'ftcompile_steane_grid')
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--workers', type=int, default=os.cpu_count() or 1)
    ap.add_argument('--budget', type=int, default=150, help='max verifier calls per repair')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); G = Graph()
    results = {'noise': NOISE.__dict__, 'graph_edges': G.edges, 'placement': G.placement}

    # ---------------- A. showcase round -----------------
    labels, hubs = showcase_round(); lr = steane_flag_round(labels, hubs)
    show = {'labels': labels, 'hubs': hubs, 'rows': []}
    progs = {'unrouted': compile_unrouted(lr, G),
             'qiskit_default_no_routing': compile_qiskit(lr, G, routed=False, optimization_level=None),
             'qiskit_opt1_no_routing': compile_qiskit(lr, G, routed=False, optimization_level=1)}
    for name, prog in progs.items():
        show['rows'].append({'name': name, **describe(prog, check_program(prog, NOISE, explain=False))})
    for lvl, tag in ((1, 'sabre_opt1'), (None, 'sabre_default')):
        runs = []
        for seed in range(5):
            prog = compile_qiskit(lr, G, routed=True, seed=seed, optimization_level=lvl)
            runs.append(describe(prog, check_program(prog, NOISE, explain=False)))
            if seed == 0:
                progs[tag] = prog
        show['rows'].append({'name': f'{tag} (5 seeds)', 'cx': [r['cx'] for r in runs],
                             'logical_cx_kept': runs[0]['logical_cx_kept'], 'ft_pass': sum(r['ft_pass'] for r in runs),
                             'conflicts': [r['conflicts'] for r in runs], 'C1': [round(r['C1'], 3) for r in runs]})
    for pol in ('shortest', 'ancilla_first'):
        prog = compile_bridge(lr, G, pol); res = check_program(prog, NOISE)
        progs[f'bridge_{pol}'] = prog
        show['rows'].append({'name': f'bridge_{pol}', **describe(prog, res)})
        if pol == 'shortest':
            w = res.witnesses[0]
            show['witness'] = {'detectors': w.detectors,
                               'events': [{'observables': e['observables'], 'locations': e['locations'][:3]} for e in w.events]}
    rr = repair_paths(lr, G, 'shortest', max_calls=args.budget, noise=NOISE)
    progs['bridge_shortest_repaired'] = rr.program
    show['rows'].append({'name': 'bridge_shortest + repair', **describe(rr.program, check_program(rr.program, NOISE, explain=False))})
    show['repair'] = {'success': rr.success, 'calls': rr.verifier_calls, 'first_suspects': rr.first_suspects[:8],
                      'changed_routes': {k: [list(a), list(b)] for k, (a, b) in rr.changed_routes.items()},
                      'cx_before': rr.start_cx, 'cx_after': rr.final_cx}
    print(f'[A] showcase compiled and repaired ({time.time()-t0:.0f}s)', flush=True)

    # Logical error rates vs p
    ps = [2e-3, 1e-3, 5e-4] if args.quick else [2e-3, 1e-3, 5e-4, 2.5e-4]
    min_fail, max_shots = (30, 200_000) if args.quick else (150, 4_000_000)
    ler = {}
    for name in ('unrouted', 'qiskit_default_no_routing', 'sabre_opt1', 'bridge_shortest', 'bridge_shortest_repaired'):
        rows = []
        for i, p in enumerate(ps):
            rows.append({'p': p, **ler_adaptive(to_stim(progs[name], Noise(p=p)), min_fail, max_shots, seed=1000 * i + 7)})
        ler[name] = {'rows': rows, 'slope': slope(ps, [r['rate'] for r in rows])}
        print(f'[A] LER {name}: slope {ler[name]["slope"]:.2f} ({time.time()-t0:.0f}s)', flush=True)
    show['ler'] = ler
    results['showcase'] = show

    # ---------------- B. sweep over template rounds -----------------
    rounds = template_rounds()
    if args.quick:
        rounds = rounds[::12]
    # 'spawn': forking after Qiskit has started its thread pool can hang the workers.
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context('spawn')) as ex:
        sweep = list(ex.map(sweep_one, [(l, h, args.budget) for l, h in rounds]))
    results['sweep'] = sweep
    results['elapsed_seconds'] = time.time() - t0
    (args.out / 'results.json').write_text(json.dumps(results, indent=1, default=str))
    (args.out / 'summary.md').write_text(render(results, args))
    print(f'DONE {args.out} ({time.time()-t0:.0f}s)')


def render(R, args) -> str:
    S = R['showcase']; sw = R['sweep']; n = len(sw)
    L = ['# Steane flag round on the 3x4 grid: compilation vs single-fault tolerance', '',
         'Verifier: Stim detector error model, exact check that no two single events (incl. no error) share a '
         'signature with different logical effect (= circuit distance >= 3, the project\'s C1 = 0 criterion). '
         f'Noise for the check and C1: p = {R["noise"]["p"]} on CX/prep/meas/incoming, p/10 idle on every other active qubit per CX. '
         'C1 = first-order logical failure probability / p under an optimal decoder.', '',
         f'## A. One round in detail: labels {S["labels"][0]} x6, hub {S["hubs"][0]}', '',
         '| Compiler | CNOTs | logical CNOTs kept (of 36) | single-fault FT | conflicting signatures | C1 |',
         '|---|---:|---:|---:|---:|---:|']
    for r in S['rows']:
        ft = r['ft_pass'] if isinstance(r['ft_pass'], bool) else f'{r["ft_pass"]}/5 seeds'
        c1v = r['C1'] if isinstance(r['C1'], list) else f'{r["C1"]:.3f}'
        L.append(f'| {r["name"]} | {r["cx"]} | {r.get("logical_cx_kept") or "36"} | {ft} | {r["conflicts"]} | {c1v} |')
    rp = S['repair']
    L += ['', f'Repair of bridge_shortest: success={rp["success"]}, {rp["calls"]} verifier calls, '
          f'{len(rp["changed_routes"])} routes changed, CNOTs {rp["cx_before"]} -> {rp["cx_after"]}.', '',
          '| Route (check.interaction) | path before | path after |', '|---|---|---|']
    for k, (a, b) in rp['changed_routes'].items():
        L.append(f'| {k} | {"-".join(map(str, a))} | {"-".join(map(str, b))} |')
    w = S['witness']
    L += ['', 'Example witness for bridge_shortest (two single events, same detectors, different logical effect):', '']
    for e in w['events']:
        L.append(f'- logical flip {e["observables"] or "none"}: ' + ', '.join(f'`{t} {p}`' for t, p in e['locations']))
    L += ['', '### Logical error rate after one round (order-2 lookup decoder)', '',
          '| Compiler | ' + ' | '.join(f'p={r["p"]:g}' for r in S['ler']['unrouted']['rows']) + ' | log-log slope |',
          '|---|' + '---:|' * (len(S['ler']['unrouted']['rows']) + 1)]
    for name, d in S['ler'].items():
        cells = [f'{r["rate"]:.2e} ({r["failures"]}/{r["shots"]})' for r in d['rows']]
        L.append(f'| {name} | ' + ' | '.join(cells) + f' | {d["slope"]:.2f} |')
    L += ['', 'Slope near 2 = second-order (fault-tolerant); near 1 = single faults cause logical errors.', '',
          f'## B. Sweep: {n} logical rounds (48 certified local templates x 2 hubs, same template on all checks)', '',
          '| Compiler | single-fault FT | median CNOTs |', '|---|---:|---:|']
    for key in ('sabre_opt1', 'sabre_default', 'bridge_shortest', 'bridge_ancilla_first'):
        L.append(f'| {key} | {sum(r[key]["ft_pass"] for r in sw)}/{n} | {statistics.median(r[key]["cx"] for r in sw):g} |')
    L += ['', f'Repair (only bridge path changes, budget {args.budget} verifier calls):', '',
          '| Start from | failing rounds | repaired | stuck (no single change helps) | budget exhausted | median calls (repaired) | CNOT change (repaired, median) |',
          '|---|---:|---:|---:|---:|---:|---:|']
    for pol in ('shortest', 'ancilla_first'):
        rs = [r[f'repair_{pol}'] for r in sw if f'repair_{pol}' in r]
        ok = [r for r in rs if r['success']]
        stuck = sum(1 for r in rs if not r['success'] and not r['budget_hit'])
        hit = sum(1 for r in rs if not r['success'] and r['budget_hit'])
        mc = statistics.median(r['calls'] for r in ok) if ok else float('nan')
        dc = statistics.median(r['cx_after'] - r['cx_before'] for r in ok) if ok else float('nan')
        L.append(f'| bridge_{pol} | {len(rs)} | {len(ok)} | {stuck} | {hit} | {mc:g} | {dc:+g} |')
    L += ['', '## Scope', '',
          '- One code (Steane, flag extraction, six serialized checks), one 12-node grid, one placement, one round with an ideal final read-out.',
          '- Repair only changes the physical path of each logical CNOT; placement, hubs, templates and check order are fixed. '
          '"Stuck" means no single path change lowers the first-order failure; it does not prove that no path assignment works.',
          '- Noise strengths are uniform and synthetic; the FT verdict itself does not depend on them.',
          f'- Runtime: {R["elapsed_seconds"]:.0f}s.']
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    main()
