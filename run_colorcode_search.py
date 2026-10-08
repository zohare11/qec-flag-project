#!/usr/bin/env python3
"""Long schedule searches for the color code (hours; run in the background).

    # one schedule per plaquette: can d = 11 reach circuit distance 10?
    python run_colorcode_search.py --d 11 --target 10

    # one family repeated along each edge: d - 1 for d = 11 and 13 at once
    python run_colorcode_search.py --family 11,13 --depth 4 --period 1

Progress goes to stdout; a schedule that reaches the target is written to
colorcode/schedules/ as JSON (one file per d) and re-checked with the exact distance.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from colorcode import hooks, search, structured  # noqa: E402
from colorcode.lattice import check_schedule, lattice, schedule_to_json  # noqa: E402

OUT = ROOT / 'colorcode' / 'schedules'


def save(d, sched, target, how):
    data, plaq = lattice(d)
    check_schedule(plaq, sched)
    below = hooks.has_logical(data, plaq, sched, target - 1)
    assert below is None, f'd={d}: found a logical below {target}'
    path = OUT / f'd{d}_distance{target}_{how}.json'
    path.write_text(schedule_to_json(d, plaq, sched, circuit_distance_at_least=target, found_by=how))
    print(f'saved {path.relative_to(ROOT)} (no logical below {target})', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--d', type=int, help='single distance, one schedule per plaquette')
    ap.add_argument('--target', type=int, help='target circuit distance (default d - 1)')
    ap.add_argument('--family', help='comma-separated distances that share one edge-repeated family')
    ap.add_argument('--depth', type=int, default=4)
    ap.add_argument('--period', type=int, default=1)
    ap.add_argument('--workers', type=int, default=4, help='CP-SAT threads')
    a = ap.parse_args()
    t0 = time.time()
    if a.family:
        ds = tuple(int(x) for x in a.family.split(','))
        r = structured.run(ds, a.depth, a.period, time_per=3600, workers=a.workers)
        print('result', r['status'], 'iterations', r['iterations'], f'{time.time() - t0:.0f}s', flush=True)
        if r['status'] == 'FOUND':
            for d, sched in structured.schedules(ds, a.depth, a.period, r['val']).items():
                save(d, sched, d - 1, f'family_depth{a.depth}_period{a.period}')
    else:
        target = a.target or a.d - 1
        r = search.search(a.d, target=target, time_per=3600, workers=a.workers)
        print('result', r['status'], 'iterations', r['iterations'], f'{time.time() - t0:.0f}s', flush=True)
        if r['status'] == 'FOUND':
            save(a.d, r['sched'], target, 'search')


if __name__ == '__main__':
    main()
