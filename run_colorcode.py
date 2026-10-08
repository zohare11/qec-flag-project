#!/usr/bin/env python3
"""Color code syndrome extraction with one auxiliary per plaquette: exact circuit distances.

    python run_colorcode.py            # ~10 minutes
Writes runs/colorcode/summary.md and results.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from colorcode import hooks, search, verify  # noqa: E402
from colorcode.circuits import memory_circuit  # noqa: E402
from colorcode.lattice import lattice, schedule_from_colors, schedule_from_json  # noqa: E402


def kf_formula(d):
    return d - (d + 3) // 6


def main():
    out = ROOT / 'runs' / 'colorcode'
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    R = {}

    # A. Kishony & Fowler: exact circuit distance vs. their formula
    R['kf'] = []
    for d in (3, 5, 7, 9, 11):
        data, plaq = lattice(d)
        w, sol = hooks.static_distance(data, plaq, schedule_from_colors(plaq), lo=max(1, kf_formula(d) - 1))
        R['kf'].append({'d': d, 'qubits': len(data) + len(plaq), 'distance': w, 'formula': kf_formula(d),
                        'hooks_in_min_logical': sum(1 for s in sol if s[0] == 'hook')})
        print(f'[A] d={d}: {w} ({time.time() - t0:.0f}s)', flush=True)

    # B. the hook count equals the circuit distance: direct check on Stim's DEM
    R['dem'] = []
    for d, noise in ((3, 'cnot'), (5, 'cnot'), (5, 'si1000')):
        c, *_ = memory_circuit(d, noise=noise)
        w = kf_formula(d)
        R['dem'].append({'d': d, 'noise': noise, 'below': verify.logical_within(c, w - 1),
                         'at': verify.logical_within(c, w), 'w': w})
        print(f'[B] d={d} {noise}: {R["dem"][-1]} ({time.time() - t0:.0f}s)', flush=True)

    # C. every middle hook of a weight-4 plaquette costs one unit of distance on its own
    R['trapezoid'] = []
    for d in (5, 7, 9):
        data, plaq = lattice(d)
        res = []
        for i, p in enumerate(plaq):
            if len(p['sup']) != 4:
                continue
            labs = sorted(p['sup'])
            for b in labs[1:]:
                pair = frozenset({p['sup'][labs[0]], p['sup'][b]})
                res.append(_distance_with_hooks(data, plaq, [pair], d))
        R['trapezoid'].append({'d': d, 'splits': len(res), 'distance_with_one_hook': sorted(set(res))})
        print(f'[C] d={d}: {R["trapezoid"][-1]} ({time.time() - t0:.0f}s)', flush=True)

    # D. no single-auxiliary schedule reaches full distance; d - 1 at d = 7 and 9
    R['search'] = []
    for d, target in ((5, 5), (7, 7)):
        r = search.search(d, target=target, verbose=False)
        R['search'].append({'d': d, 'target': target, 'status': r['status'], 'iterations': r['iterations']})
        r = search.search(d, target=target, flag=True, verbose=False)
        R['search'].append({'d': d, 'target': target, 'flags': True, 'status': r['status'], 'iterations': r['iterations']})
        print(f'[D] d={d}: {R["search"][-2:]} ({time.time() - t0:.0f}s)', flush=True)
    d, data, plaq, sched = schedule_from_json((ROOT / 'colorcode' / 'schedules' / 'd9_distance8.json').read_text())
    w, _ = hooks.static_distance(data, plaq, sched, lo=7, hi=9)
    R['d9'] = {'distance': w, 'kf': kf_formula(9)}
    print(f'[D] d=9 stored schedule: {w} ({time.time() - t0:.0f}s)', flush=True)

    # E. which pairs of bottom-edge trapezoid hooks combine (d = 11, no other hooks)
    data, plaq = lattice(11)
    bottom = sorted((p for p in plaq if set(p['sup']) == {'L', 'R', 'TL', 'TR'}), key=lambda p: p['center'][0])
    A, B = bottom[1], bottom[3]
    splits = {'horizontal (L,R / TL,TR)': ('L', 'R'), 'vertical (L,TL / R,TR)': ('L', 'TL'),
              'diagonal (L,TR / R,TL)': ('L', 'TR')}
    R['pairs'] = []
    for na, a in splits.items():
        for nb, b in splits.items():
            hs = [frozenset(A['sup'][x] for x in a), frozenset(B['sup'][x] for x in b)]
            R['pairs'].append({'left': na, 'right': nb, 'distance': _distance_with_hooks(data, plaq, hs, 11)})
    print(f'[E] {R["pairs"]} ({time.time() - t0:.0f}s)', flush=True)

    # F. Kishony & Fowler's own mid-edge trapezoid hook, alone (d = 11)
    kf = schedule_from_colors(plaq)
    mid = bottom[len(bottom) // 2]
    i = plaq.index(mid)
    order = [k for k, _ in sorted(((k, kf[i][v]) for k, v in mid['sup'].items()), key=lambda kv: kv[1])]
    R['kf_mid_trapezoid'] = {'center': list(mid['center']), 'order': order, 'hook': order[2:],
                             'distance_with_only_this_hook': _distance_with_hooks(
                                 data, plaq, [frozenset(mid['sup'][k] for k in order[2:])], 11)}
    print(f'[F] {R["kf_mid_trapezoid"]} ({time.time() - t0:.0f}s)', flush=True)

    R['elapsed_seconds'] = time.time() - t0
    (out / 'results.json').write_text(json.dumps(R, indent=1))
    (out / 'summary.md').write_text(render(R))
    print((out / 'summary.md').read_text())


def render(R):
    L = ['# Color code syndrome extraction with one auxiliary per plaquette', '',
         'Triangular 6.6.6 color code, one auxiliary qubit per plaquette, X block then Z block, 6 CNOT steps each '
         '(the setting of Kishony & Fowler, arXiv:2603.28852). Code: `colorcode/`.', '',
         '## 1. Exact circuit distance from hook errors', '',
         'For these circuits the circuit-level distance equals the hook distance: the fewest faults, counting a '
         'single data error or one hook (a schedule suffix) as one fault, that form a logical operator. The '
         'argument is in `colorcode/hooks.py`; it covers noisy-CNOT, SI1000 and uniform noise. Direct check '
         'on Stim\'s detector error model:', '',
         '| d | Noise | Logical with d_circ - 1 faults | Logical with d_circ faults |', '|---:|---|---|---|']
    for r in R['dem']:
        L.append(f'| {r["d"]} | {r["noise"]} | {"yes" if r["below"] else "none"} | {"yes" if r["at"] else "none"} |')
    L += ['', '## 2. Kishony & Fowler schedule', '',
          '| d | Qubits | Circuit distance | Their formula d - floor((d+3)/6) | Hooks in a shortest logical |',
          '|---:|---:|---:|---:|---:|']
    for r in R['kf']:
        L.append(f'| {r["d"]} | {r["qubits"]} | {r["distance"]} | {r["formula"]} | {r["hooks_in_min_logical"]} |')
    m = R['kf_mid_trapezoid']
    L += ['', 'Their formula holds, and from d = 9 on the shortest logicals are chains of hooks along an edge (their '
          '"fractional hook errors"). The paper also says no single hook reduces the distance except at the corners. '
          f'That does not hold for the trapezoids: at d = 11 the middle bottom trapezoid (centre {tuple(m["center"])}, '
          f'order {", ".join(m["order"])}) has the middle hook {{{", ".join(m["hook"])}}}, and with only that hook the '
          f'distance is already {m["distance_with_only_this_hook"]}. It does not change their totals, because the '
          'hook chains cost more.', '',
          '## 3. d - 1 is the ceiling for any single-auxiliary schedule', '',
          'A weight-4 boundary plaquette always has a middle hook (two of its qubits). With that one hook and no '
          'others:', '', '| d | Middle splits tried | Distance |', '|---:|---:|---|']
    for r in R['trapezoid']:
        L.append(f'| {r["d"]} | {r["splits"]} | {", ".join(map(str, r["distance_with_one_hook"]))} |')
    L += ['', 'Two bottom-edge trapezoid hooks at d = 11 (no other hooks):', '',
          '| Left trapezoid split | Right trapezoid split | Distance |', '|---|---|---:|']
    for r in R['pairs']:
        L.append(f'| {r["left"]} | {r["right"]} | {r["distance"]} |')
    L += ['', '## 4. Schedule search (CEGAR: CP-SAT master, SAT counterexamples)', '',
          '| d | Target | Flag on every trapezoid | Result |', '|---:|---:|---|---|']
    for r in R['search']:
        L.append(f'| {r["d"]} | {r["target"]} | {"yes" if r.get("flags") else "no"} | {r["status"].lower()} |')
    L += ['', f'Stored d = 9 schedule (`colorcode/schedules/d9_distance8.json`): circuit distance {R["d9"]["distance"]}, '
          f'against {R["d9"]["kf"]} for Kishony & Fowler, same qubits and depth. Every plaquette has its own order.', '',
          'Going from 7 to 8 does not change the leading order of the logical error rate (both fail at 4 faults); '
          'the gain is in the prefactor. A better exponent needs d - 1 for every d (Kishony & Fowler lose about d/6), '
          'which first pays off at d = 15. Families repeated along each edge with period 1 or 2 (plus corner '
          'cells) were infeasible for d = 9 and 11 together; d = 11 itself is still open.', '',
          f'Runtime: {R["elapsed_seconds"]:.0f}s.']
    return '\n'.join(L) + '\n'


def _distance_with_hooks(data, plaq, extra, hi):
    """Distance when the only hooks are `extra` (sets of data vertices)."""
    import pycryptosat
    from pysat.card import CardEnc, EncType
    gens = [frozenset([v]) for v in data] + [frozenset(h) for h in extra]
    n = len(gens)
    for w in range(1, hi + 1):
        s = pycryptosat.Solver()
        for p in plaq:
            sup = set(p['sup'].values())
            vs = [i + 1 for i, g in enumerate(gens) if len(g & sup) % 2]
            if vs:
                s.add_xor_clause(vs, False)
        s.add_xor_clause([i + 1 for i, g in enumerate(gens) if len(g) % 2], True)
        for cl in CardEnc.atmost(lits=list(range(1, n + 1)), bound=w, top_id=n, encoding=EncType.seqcounter).clauses:
            s.add_clause(cl)
        if s.solve()[0]:
            return w
    return None


if __name__ == '__main__':
    main()
