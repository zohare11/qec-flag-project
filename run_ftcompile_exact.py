#!/usr/bin/env python3
"""Exact repairability oracle over the 96 logical rounds of the case study.

For every round: does any bridge-path assignment make it single-fault FT?
If so, how many routes must change at minimum (vs the shortest-path and the
ancilla-first compilations), and how many CNOTs does the cheapest FT assignment
need?  If not, which checks make it impossible, and do longer paths help?
Greedy-repair results are read from the case-study run for comparison.

    python run_ftcompile_exact.py                     # needs runs/ftcompile_steane_grid/results.json
    python run_ftcompile_exact.py --quick
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import statistics
import sys
import time
import warnings
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings('ignore')

from ftcompile.core import check_program, steane_flag_round  # noqa: E402
from ftcompile.compilers import Graph, bridge_cnots, compile_bridge  # noqa: E402
from ftcompile.exact import build_model, infeasible_core, solve  # noqa: E402
from run_ftcompile_case import NOISE, template_rounds  # noqa: E402

CHECK_NAMES = ('X0', 'X1', 'X2', 'Z0', 'Z1', 'Z2')


def cx_of(paths):
    return sum(len(bridge_cnots(p)) for p in paths.values())


def one_round(args):
    labels, hubs = args
    G = Graph(); lr = steane_flag_round(labels, hubs)
    t0 = time.time()
    m = build_model(lr, G, extra_hops=2, noise=NOISE)
    out = {'labels': labels[0], 'hub': hubs[0], 'routes': len(m.routes),
           'paths_in_language': sum(len(v) for v in m.candidates.values()),
           'unary': len(m.unary), 'binary': len(m.binary)}
    feas = solve(m)
    out['status'] = feas.status
    if feas.status == 'feasible':
        starts = {pol: compile_bridge(lr, G, pol).meta['paths'] for pol in ('shortest', 'ancilla_first')}
        for pol, start in starts.items():
            r = solve(m, 'edits', start=start)
            out[f'min_edits_from_{pol}'] = r.objective
            out[f'verified_{pol}'] = check_program(compile_bridge(lr, G, 'shortest', overrides=r.paths), NOISE,
                                                   explain=False).passed
        r = solve(m, 'cx')
        out['min_cx'] = r.objective
        out['start_cx'] = cx_of(starts['shortest'])
        out['verified_min_cx'] = check_program(compile_bridge(lr, G, 'shortest', overrides=r.paths), NOISE,
                                               explain=False).passed
    elif feas.status == 'infeasible':
        core = infeasible_core(m)
        if 'checks' in core:
            core['checks'] = [CHECK_NAMES[int(c[1:])] for c in core['checks']]
        out['core'] = core
        big = build_model(lr, G, extra_hops=4, noise=NOISE)
        rb = solve(big)
        out['status_longer_paths'] = rb.status
        if rb.status == 'feasible':
            out['verified_longer_paths'] = check_program(compile_bridge(lr, G, 'shortest', overrides=rb.paths), NOISE,
                                                         explain=False).passed
            out['cx_longer_paths'] = solve(big, 'cx').objective
    out['seconds'] = time.time() - t0
    return out


def entry_blocked(row) -> tuple[int, int]:
    """For routes with no safe path: how many end at a data qubit (not adjacent to the
    other endpoint) whose every neighbour is another data qubit or this check's own flag,
    so that any bridge must pass through a qubit that is in use."""
    if row.get('core', {}).get('kind') != 'route_with_no_safe_path':
        return 0, 0
    G = Graph(); lr = steane_flag_round((row['labels'],) * 6, (row['hub'],) * 6)
    data = set(G.data_nodes)
    own = {G.placement[v] for f, v in (('A', 9), ('B', 10)) if f in row['labels']}
    hits = 0
    for route in row['core']['routes']:
        a, b = (G.placement[q] for q in next(o for o in lr.ops if o.tag == route).qubits)
        d, other = (a, b) if a in data else (b, a)
        nb = set(G.g.neighbors(d))
        hits += other not in nb and all(n in data or n in own for n in nb)
    return hits, len(row['core']['routes'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', type=Path, default=ROOT / 'runs' / 'ftcompile_steane_grid')
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--workers', type=int, default=os.cpu_count() or 1)
    ap.add_argument('--render-only', action='store_true', help='re-render from exact_results.json')
    args = ap.parse_args()
    if args.render_only:
        out = json.loads((args.case / 'exact_results.json').read_text())
        (args.case / 'exact_summary.md').write_text(render(out)); print(render(out)); return
    t0 = time.time()
    rounds = template_rounds()
    if args.quick:
        rounds = rounds[::12]
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context('spawn')) as ex:
        rows = list(ex.map(one_round, rounds))
    greedy = {}
    rj = args.case / 'results.json'
    if rj.exists():
        for r in json.loads(rj.read_text())['sweep']:
            greedy[(r['labels'], r['hub'])] = r
    for row in rows:
        g = greedy.get((row['labels'], row['hub']))
        if g:
            row['ancilla_first_passes'] = g['bridge_ancilla_first']['ft_pass']
            for pol in ('shortest', 'ancilla_first'):
                rp = g.get(f'repair_{pol}')
                row[f'greedy_{pol}'] = None if rp is None else {
                    'success': rp['success'], 'routes_changed': rp['routes_changed'], 'budget_hit': rp['budget_hit']}
    out = {'rows': rows, 'elapsed_seconds': time.time() - t0, 'language': 'all simple paths up to shortest + 2 hops',
           'have_greedy': bool(greedy)}
    args.case.mkdir(parents=True, exist_ok=True)
    (args.case / 'exact_results.json').write_text(json.dumps(out, indent=1))
    (args.case / 'exact_summary.md').write_text(render(out))
    print((args.case / 'exact_summary.md').read_text())


def render(R) -> str:
    rows = R['rows']; n = len(rows)
    feas = [r for r in rows if r['status'] == 'feasible']
    inf = [r for r in rows if r['status'] == 'infeasible']
    unk = [r for r in rows if r['status'] not in ('feasible', 'infeasible')]
    L = ['# Exact repairability of bridge-path choices (Steane flag round, 3x4 grid)', '',
         'For each logical round (template x hub) the oracle asks whether ANY assignment of physical paths to the '
         f'logical CNOTs is single-fault FT. Path language: {R["language"]}. Placement, hubs, templates and check '
         'order are fixed. Exact: a CP-SAT model built from per-route Stim fault signatures (each fault depends only on '
         'its own route, because a bridge is exactly a CNOT on its endpoints); every reported solution is re-verified '
         'with the full-circuit Stim check.', '',
         '## Can the round be made fault-tolerant by changing paths only?', '',
         '| | rounds |', '|---|---:|',
         f'| FT path assignment exists | {len(feas)} |', f'| provably none (in this path language) | {len(inf)} |']
    if unk:
        L.append(f'| solver gave up | {len(unk)} |')
    L.append(f'| total | {n} |')
    L += ['', 'By syndrome hub and flag type:', '', '| hub | flags | FT possible | impossible |', '|---|---|---:|---:|']
    def kind(lab):
        return 'A+B' if ('A' in lab and 'B' in lab) else ('A' if 'A' in lab else 'B')
    for hub in (0, 1):
        for k in ('A', 'B', 'A+B'):
            sel = [r for r in rows if r['hub'] == hub and kind(r['labels']) == k]
            if sel:
                L.append(f'| {hub} | {k} | {sum(r["status"] == "feasible" for r in sel)} | '
                         f'{sum(r["status"] == "infeasible" for r in sel)} |')
    ver = all(r.get('verified_shortest') and r.get('verified_ancilla_first') and r.get('verified_min_cx') for r in feas)
    L += ['', f'All oracle solutions re-verified with the full Stim check: {ver}.']
    if feas:
        me_s = [r['min_edits_from_shortest'] for r in feas]; me_a = [r['min_edits_from_ancilla_first'] for r in feas]
        L += ['', '## How small can the repair be?', '',
              '| Starting compilation | min routes changed (median / max, over FT-possible rounds) |', '|---|---:|',
              f'| shortest paths | {statistics.median(me_s):g} / {max(me_s):g} |',
              f'| ancilla-first (Phase-7 rule) | {statistics.median(me_a):g} / {max(me_a):g} |', '',
              f'Cheapest FT assignment vs shortest-path compilation: median {statistics.median(r["min_cx"] - r["start_cx"] for r in feas):+g} CNOTs '
              f'(range {min(r["min_cx"] - r["start_cx"] for r in feas):+g} to {max(r["min_cx"] - r["start_cx"] for r in feas):+g}).']
    if R['have_greedy']:
        L += ['', '## Greedy repair vs the oracle', '',
              '| Start from | greedy repaired | FT possible but greedy failed | impossible (greedy could not succeed) |',
              '|---|---:|---:|---:|']
        for pol in ('shortest', 'ancilla_first'):
            tried = [r for r in rows if r.get(f'greedy_{pol}')]
            ok = [r for r in tried if r[f'greedy_{pol}']['success']]
            miss = [r for r in tried if not r[f'greedy_{pol}']['success'] and r['status'] == 'feasible']
            imp = [r for r in tried if not r[f'greedy_{pol}']['success'] and r['status'] == 'infeasible']
            L.append(f'| {pol} | {len(ok)}/{len(tried)} | {len(miss)} | {len(imp)} |')
        ok = [r for r in rows if (r.get('greedy_shortest') or {}).get('success')]
        if ok:
            extra = [r['greedy_shortest']['routes_changed'] - r['min_edits_from_shortest'] for r in ok]
            L.append('')
            L.append(f'When greedy (from shortest) succeeded it changed {statistics.median(extra):g} more routes than '
                     f'necessary (median; max {max(extra):g}).')
        nf = [r for r in rows if not r.get('ancilla_first_passes') and not any(
            (r.get(f'greedy_{p}') or {}).get('success') for p in ('shortest', 'ancilla_first'))]
        L.append('')
        L.append(f'The {len(nf)} rounds neither the Phase-7 rule nor greedy repair made FT: '
                 f'{sum(r["status"] == "feasible" for r in nf)} are repairable by paths, '
                 f'{sum(r["status"] == "infeasible" for r in nf)} are provably not.')
    if inf:
        cores = Counter()
        for r in inf:
            c = r.get('core', {})
            cores[(c.get('kind'), tuple(c.get('checks', c.get('routes', []))))] += 1
        L += ['', '## Why the impossible rounds are impossible', '', '| smallest blocking set | rounds |', '|---|---:|']
        for (k, items), cnt in cores.most_common():
            L.append(f'| {k}: {", ".join(items)} | {cnt} |')
        eb = [entry_blocked(r) for r in inf]
        hit, tot = sum(h for h, _ in eb), sum(t for _, t in eb)
        if tot:
            L += ['', f'Geometry: {hit} of {tot} blocked routes end at a data qubit that is not next to the other endpoint and whose '
                  'every neighbour is another data qubit or the check\'s own flag, so every bridge to it passes through a qubit '
                  'that is in use. Corner data qubits on this grid have only two neighbours: '
                  'node 0 -> {1 (data), 4 (flag A)}, node 8 -> {4 (flag A), 9 (data)}, node 11 -> {7 (flag B), 10 (data)}, node 3 -> {2 (free), 7 (flag B)}.']
        lp = Counter(r.get('status_longer_paths') for r in inf)
        L += ['', f'Allowing paths up to shortest + 4 hops: {lp.get("feasible", 0)} of {len(inf)} become FT-possible '
              f'({lp.get("infeasible", 0)} still impossible).']
    L += ['', '## Scope', '',
          '- Only physical paths are decision variables. Moving the syndrome hub, the placement, or reordering checks '
          'could rescue "impossible" rounds; that is not tested here.',
          '- Same code, graph, placement and noise model as the case study (`summary.md`).',
          f'- Runtime: {R["elapsed_seconds"]:.0f}s.']
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    main()
