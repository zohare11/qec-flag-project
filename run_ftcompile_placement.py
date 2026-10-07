#!/usr/bin/env python3
"""Placement study: where should the 7 data qubits, 2 syndrome hubs and 2 flags sit
on the 3x4 grid so that as many logical rounds as possible can be routed
single-fault FT (by choosing bridge paths)?

    python run_ftcompile_placement.py                 # search + report (~20-40 min)
    python run_ftcompile_placement.py --quick

Score of a placement = number of the 96 logical rounds (48 certified templates x
2 hubs) for which some bridge-path assignment is single-fault FT (exact, via
ftcompile.placement).  Search = simulated annealing over swaps of node contents.
Writes runs/ftcompile_placement/summary.md and results.json.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import os
import random
import statistics
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings('ignore')

from ftcompile import placement as PL  # noqa: E402
from ftcompile.compilers import Graph, bridge_cnots, compile_bridge  # noqa: E402
from ftcompile.core import GRID_EDGES, GRID_PLACEMENT, check_program, steane_flag_round  # noqa: E402
from run_ftcompile_case import NOISE, template_rounds  # noqa: E402

NAMES = {0: 'd0', 1: 'd1', 2: 'd2', 3: 'd3', 4: 'd4', 5: 'd5', 6: 'd6', 7: 'H0', 8: 'H1', 9: 'FA', 10: 'FB'}
_TB = None


def tables():
    global _TB
    if _TB is None:
        _TB = [PL.round_tables(steane_flag_round(l, h)) for l, h in template_rounds()]
    return _TB


def evaluate(pl: dict[int, int]) -> tuple[int, float, float, float]:
    """(number of FT-routable rounds, fraction of logical CNOTs with at least one safe path,
    cost proxy = mean over FT-routable rounds of the sum over CNOTs of the cheapest safe path;
    a lower bound on the cheapest FT routing)."""
    feas = 0; routable = 0; total = 0; cost = []
    for tb in tables():
        m = PL.build(tb, pl)
        routable += sum(1 for r in m.routes if m.allowed[r]); total += len(m.routes)
        if PL.solve(m)[0] == 'feasible':
            feas += 1
            cost.append(sum(min(len(bridge_cnots(m.candidates[r][i])) for i in m.allowed[r]) for r in m.routes))
    return feas, routable / total, (statistics.fmean(cost) if cost else float('inf')), (min(cost) if cost else float('inf'))


def to_pl(perm) -> dict[int, int]:
    return {q: perm[q] for q in range(11)}


def anneal(args):
    """mode 'coverage': maximize FT-routable rounds (plus a smooth tie-breaker);
    'cost': keep the start's coverage, minimize the mean cost proxy;
    'cheapest': minimize the cost proxy of the single cheapest FT-routable round."""
    seed, start, steps, mode = args
    rng = random.Random(seed)
    perm = list(start) if start else rng.sample(range(12), 12)
    cache = {}
    floor = evaluate(to_pl(perm))[0] if mode == 'cost' else None

    def score(p):
        k = tuple(p[:11])
        if k not in cache:
            f, s, c, cmin = evaluate(to_pl(p))
            if mode == 'coverage':
                key = f + s
            elif mode == 'cost':
                key = -c if f >= floor else -1e9
            else:
                key = -cmin if f else -1e9 + s
            cache[k] = (f, key, c, cmin)
        return cache[k]

    cur = score(perm); best = (cur, list(perm))
    t0, t1 = (3.0, 0.05) if mode == 'coverage' else (8.0, 0.2)
    for step in range(steps):
        T = t0 * (t1 / t0) ** (step / max(1, steps - 1))
        i, j = rng.sample(range(12), 2)
        perm[i], perm[j] = perm[j], perm[i]
        new = score(perm)
        if new[1] >= cur[1] or rng.random() < math.exp(max(-50.0, (new[1] - cur[1]) / T)):
            cur = new
            if new[1] > best[0][1]:
                best = (new, list(perm))
        else:
            perm[i], perm[j] = perm[j], perm[i]
        if mode == 'coverage' and best[0][0] == 96:
            break
    return {'seed': seed, 'mode': mode, 'best_feasible': best[0][0], 'cost_proxy': best[0][2],
            'cheapest_proxy': best[0][3], 'perm': best[1], 'evaluations': len(cache)}


def grid_picture(pl: dict[int, int]) -> str:
    inv = {n: v for v, n in pl.items()}
    rows = []
    for r in range(3):
        rows.append(' '.join(f'{NAMES.get(inv.get(r * 4 + c, -1), "..")}' for c in range(4)))
    return '\n'.join(rows)


def detail(pl: dict[int, int], verify: bool = True) -> dict:
    """Per-round exact status, cheapest FT CNOT count, and full Stim verification."""
    g = Graph(GRID_EDGES, pl); out = []
    for (labels, hubs), tb in zip(template_rounds(), tables()):
        m = PL.build(tb, pl)
        st, paths, cx = PL.solve(m, 'cx')
        row = {'labels': labels[0], 'hub': hubs[0], 'status': st, 'min_cx': cx,
               'shortest_cx': sum(min(len(bridge_cnots(p)) for p in m.candidates[r]) for r in m.routes),
               'blocked_routes': [r for r in m.routes if not m.allowed[r]]}
        if verify and paths:
            lr = steane_flag_round(labels, hubs)
            row['verified'] = check_program(compile_bridge(lr, g, 'shortest', overrides=paths), NOISE, explain=False).passed
        out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=ROOT / 'runs' / 'ftcompile_placement')
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--workers', type=int, default=os.cpu_count() or 1)
    ap.add_argument('--chains', type=int, default=6)
    ap.add_argument('--steps', type=int, default=500)
    ap.add_argument('--cost-chains', type=int, default=4)
    ap.add_argument('--cost-steps', type=int, default=400)
    ap.add_argument('--random-baseline', type=int, default=200)
    args = ap.parse_args()
    if args.quick:
        args.chains, args.steps, args.random_baseline, args.cost_chains, args.cost_steps = 2, 40, 20, 2, 30
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    current = [GRID_PLACEMENT[q] for q in range(11)]
    current += [n for n in range(12) if n not in current]
    ctx = multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=ctx) as ex:
        rng = random.Random(2026)
        baseline = list(ex.map(evaluate, [to_pl(rng.sample(range(12), 12)) for _ in range(args.random_baseline)]))
        print(f'random baseline done ({time.time()-t0:.0f}s)', flush=True)
        starts = [(1000 + k, current if k == 0 else None, args.steps, 'coverage') for k in range(args.chains)]
        chains = list(ex.map(anneal, starts))
        print(f'coverage search done ({time.time()-t0:.0f}s)', flush=True)
        top = sorted(chains, key=lambda c: (-c['best_feasible'], c['cost_proxy']))
        tops = [c for c in top if c['best_feasible'] == top[0]['best_feasible']]
        jobs = [(2000 + k, tops[k % len(tops)]['perm'], args.cost_steps, 'cost') for k in range(args.cost_chains)]
        jobs += [(3000 + k, [current, top[0]['perm']][k] if k < 2 else None, args.cost_steps, 'cheapest')
                 for k in range(args.cost_chains)]
        more = list(ex.map(anneal, jobs))
    print(f'cost searches done ({time.time()-t0:.0f}s)', flush=True)
    cost_chains = [c for c in more if c['mode'] == 'cost']
    cheap_chains = [c for c in more if c['mode'] == 'cheapest']
    full = max(cost_chains, key=lambda c: (c['best_feasible'], -c['cost_proxy']))
    single = min(cheap_chains, key=lambda c: c['cheapest_proxy'])
    layouts = {'current': current, 'full_coverage': full['perm'], 'cheapest_round': single['perm']}
    res = {'baseline': [b[0] for b in baseline], 'chains': chains + more, 'elapsed_seconds': None, 'args': vars(args)}
    for name, perm in layouts.items():
        res[name] = {'placement': to_pl(perm), 'rows': detail(to_pl(perm))}
    res['ler'] = ler_compare(res, shots=300_000 if args.quick else 3_000_000)
    res['elapsed_seconds'] = time.time() - t0
    (args.out / 'results.json').write_text(json.dumps(res, indent=1, default=str))
    (args.out / 'summary.md').write_text(render(res))
    print((args.out / 'summary.md').read_text())


def ler_compare(res: dict, shots: int) -> dict:
    """Logical error rate of each layout's cheapest FT round (cheapest FT routing), plus the
    same template unrouted (all-to-all) as a reference."""
    from ftcompile.compilers import compile_unrouted
    from ftcompile.core import Noise, to_stim
    from ftcompile.decode import logical_error_rate
    out = {}
    for name in ('current', 'full_coverage', 'cheapest_round'):
        pl = {int(a): b for a, b in res[name]['placement'].items()}
        rows = [r for r in res[name]['rows'] if r['status'] == 'feasible']
        if not rows:
            out[name] = None; continue
        r0 = min(rows, key=lambda r: r['min_cx'])
        labels, hubs = (r0['labels'],) * 6, (r0['hub'],) * 6
        lr = steane_flag_round(labels, hubs)
        st, paths, cx = PL.solve(PL.build(PL.round_tables(lr), pl), 'cx')
        g = Graph(GRID_EDGES, pl)
        progs = {'routed': compile_bridge(lr, g, 'shortest', overrides=paths), 'unrouted': None}
        from ftcompile.compilers import compile_unrouted as cu
        progs['unrouted'] = cu(lr, g)
        entry = {'template': r0['labels'], 'hub': r0['hub'], 'cx': progs['routed'].n_cx}
        for kind, prog in progs.items():
            entry[kind] = []
            for p in (1e-3, 5e-4):
                r = logical_error_rate(to_stim(prog, Noise(p=p)), shots, seed=17, batch=100_000, min_failures=200)
                entry[kind].append({'p': p, 'rate': r['rate'], 'failures': r['failures'], 'shots': r['shots']})
        out[name] = entry
    return out


def _stats(rows):
    f = [r for r in rows if r['status'] == 'feasible']
    med = lambda k: statistics.median(r[k] for r in f) if f else float('nan')
    return {'n': len(f), 'cx': med('min_cx'), 'short': med('shortest_cx'),
            'min': min((r['min_cx'] for r in f), default=float('nan')),
            'ft_cost': statistics.median(r['min_cx'] - r['shortest_cx'] for r in f) if f else float('nan'),
            'verified': all(r.get('verified') for r in f)}


def render(R) -> str:
    base = R['baseline']
    names = [('current', 'current (Phase 5-7 layout)'), ('full_coverage', 'every round FT-routable, cheapest found'),
             ('cheapest_round', 'cheapest single FT round found')]
    S = {k: _stats(R[k]['rows']) for k, _ in names}
    L = ['# Where should the qubits go? Placement search on the 3x4 grid', '',
         'A placement assigns the 7 Steane data qubits (d0-d6), the two syndrome hubs (H0, H1) and the two flags '
         '(FA, FB) to the 12 grid nodes (one node stays free, ".."). Its score is how many of the 96 logical rounds '
         '(48 certified flag templates x 2 hubs) can be routed single-fault FT by choosing bridge paths '
         '(all simple paths up to shortest + 2 hops). Each score is exact; every reported routing is re-verified with '
         'the full Stim check.', '',
         '## Result', '',
         '| Placement | FT-routable rounds | cheapest FT round (CNOTs) | median CNOTs over routable rounds | median extra CNOTs for FT vs shortest paths | all verified |',
         '|---|---:|---:|---:|---:|---|']
    for k, label in names:
        s = S[k]
        L.append(f'| {label} | {s["n"]}/96 | {s["min"]:g} | {s["cx"]:g} | {s["ft_cost"]:+g} | {s["verified"]} |')
    L += [f'| random placements ({len(base)}) | median {statistics.median(base):g}, max {max(base)} | | | | |', '',
          f'{sum(b == 0 for b in base)} of {len(base)} random placements make no round fault-tolerant at all.', '']
    for k, label in names:
        L += [f'{label}:', '', '```', grid_picture({int(a): b for a, b in R[k]['placement'].items()}), '```', '']
    cur, full = R['current']['rows'], R['full_coverage']['rows']
    both = [(c, b) for c, b in zip(cur, full) if c['status'] == b['status'] == 'feasible']
    if both:
        d = [b['min_cx'] - c['min_cx'] for c, b in both]
        L += [f'On the {len(both)} rounds routable with both, the full-coverage layout needs '
              f'{statistics.median(d):+g} CNOTs vs the current layout (median; range {min(d):+g} to {max(d):+g}).', '']
    ler = R.get('ler')
    if ler:
        L += ['### Logical error rate of each layout\'s cheapest FT round', '',
              'Cheapest FT routing of the layout\'s cheapest round; "unrouted" is the same template with all-to-all '
              'connectivity (no routing overhead). Order-2 lookup decoder, one round, ideal final read-out.', '',
              '| Layout | template, hub | CNOTs | p = 0.001 | p = 0.0005 | unrouted p = 0.001 | unrouted p = 0.0005 |',
              '|---|---|---:|---:|---:|---:|---:|']
        for k, v in ler.items():
            if v:
                cells = [f'{r["rate"]:.2e}' for r in v['routed']] + [f'{r["rate"]:.2e}' for r in v['unrouted']]
                L.append(f'| {k} | {v["template"]}, H{v["hub"]} | {v["cx"]} | ' + ' | '.join(cells) + ' |')
        L.append('')
    L += ['## Search', '', '| objective | start | FT-routable rounds | mean cost proxy | cheapest-round proxy | placements evaluated |',
          '|---|---|---:|---:|---:|---:|']
    for c in R['chains']:
        start = {1000: 'current layout', 3000: 'current layout', 3001: 'full-coverage layout'}.get(c['seed'],
                 'best coverage layout' if c['mode'] == 'cost' else 'random')
        L.append(f'| {c["mode"]} | {start} | {c["best_feasible"]} | {c["cost_proxy"]:.1f} | {c["cheapest_proxy"]:.0f} | {c["evaluations"]} |')
    L += ['', 'Cost proxy of a round = sum over its logical CNOTs of the cheapest safe path (a lower bound on its cheapest FT routing).', '',
          '## Scope', '',
          '- One code (Steane, flagged six-check round), one 12-node grid, fixed check order; only placement and bridge paths vary.',
          '- Rounds use the same flag template on all six checks; mixing templates per check is not explored.',
          '- The search is heuristic (simulated annealing), so "best found" is not proven optimal; each score is exact.',
          f'- Runtime: {R["elapsed_seconds"]:.0f}s.']
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    main()
