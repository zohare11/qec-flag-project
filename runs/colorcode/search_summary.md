# Long schedule searches (run_colorcode_search.py)

Run on a MacBook Pro, 4 CP-SAT threads each, Oct 8 2026.

| Search | Question | Result | Rounds | Time |
|---|---|---|---:|---:|
| `--d 11 --target 10` | any single-auxiliary, 6-step schedule with circuit distance 10 at d = 11? | infeasible | 1174 | 3.2 h |
| `--family 11,13 --depth 4 --period 1` | one edge-repeated family with d - 1 at d = 11 and 13? | infeasible | 213 | 0.9 h |

Infeasible is a proof (CP-SAT exhausted every schedule; each cut removes only schedules that
contain a logical below the target), so at d = 11 the best circuit distance is 9, which the
Kishony & Fowler schedule already reaches. The family result follows from the first.

Best circuit distance with one auxiliary per plaquette and 6 CNOT steps per block (X block then
Z block; the X and Z distances depend only on their own block's order, so using the same order in
both loses nothing):

| d | Best possible | Kishony & Fowler | How the best was settled |
|---:|---:|---:|---|
| 5 | 4 | 4 | 5 infeasible |
| 7 | 6 | 6 | 7 infeasible |
| 9 | 8 | 7 | 9 infeasible (trapezoid hooks); 8 found (`colorcode/schedules/d9_distance8.json`) |
| 11 | 9 | 9 | 10 infeasible (this run) |

These four values fit d - floor((d+1)/6), against d - floor((d+3)/6) for Kishony & Fowler; the two
differ only for d = 3 mod 6 (d = 9, 15, 21, ...). If that pattern holds, both lose about d/6 and
Kishony & Fowler's construction is optimal up to one unit. The pattern is a guess from four points.
