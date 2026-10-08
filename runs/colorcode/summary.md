# Color code syndrome extraction with one auxiliary per plaquette

Triangular 6.6.6 color code, one auxiliary qubit per plaquette, X block then Z block, 6 CNOT steps each (the setting of Kishony & Fowler, arXiv:2603.28852). Code: `colorcode/`.

## 1. Exact circuit distance from hook errors

For these circuits the circuit-level distance equals the hook distance: the fewest faults, counting a single data error or one hook (a schedule suffix) as one fault, that form a logical operator. The argument is in `colorcode/hooks.py`; it covers noisy-CNOT, SI1000 and uniform noise. Direct check on Stim's detector error model:

| d | Noise | Logical with d_circ - 1 faults | Logical with d_circ faults |
|---:|---|---|---|
| 3 | cnot | none | yes |
| 5 | cnot | none | yes |
| 5 | si1000 | none | yes |

## 2. Kishony & Fowler schedule

| d | Qubits | Circuit distance | Their formula d - floor((d+3)/6) | Hooks in a shortest logical |
|---:|---:|---:|---:|---:|
| 3 | 10 | 2 | 2 | 1 |
| 5 | 28 | 4 | 4 | 1 |
| 7 | 55 | 6 | 6 | 1 |
| 9 | 91 | 7 | 7 | 7 |
| 11 | 136 | 9 | 9 | 9 |

Their formula holds, and from d = 9 on the shortest logicals are chains of hooks along an edge (their "fractional hook errors"). The paper also says no single hook reduces the distance except at the corners. That does not hold for the trapezoids: at d = 11 the middle bottom trapezoid (centre (15, -3), order TR, L, R, TL) has the middle hook {R, TL}, and with only that hook the distance is already 10. It does not change their totals, because the hook chains cost more.

## 3. d - 1 is the ceiling for any single-auxiliary schedule

A weight-4 boundary plaquette always has a middle hook (two of its qubits). With that one hook and no others:

| d | Middle splits tried | Distance |
|---:|---:|---|
| 5 | 18 | 4 |
| 7 | 27 | 6 |
| 9 | 36 | 8 |

Two bottom-edge trapezoid hooks at d = 11 (no other hooks):

| Left trapezoid split | Right trapezoid split | Distance |
|---|---|---:|
| horizontal (L,R / TL,TR) | horizontal (L,R / TL,TR) | 9 |
| horizontal (L,R / TL,TR) | vertical (L,TL / R,TR) | 10 |
| horizontal (L,R / TL,TR) | diagonal (L,TR / R,TL) | 10 |
| vertical (L,TL / R,TR) | horizontal (L,R / TL,TR) | 10 |
| vertical (L,TL / R,TR) | vertical (L,TL / R,TR) | 10 |
| vertical (L,TL / R,TR) | diagonal (L,TR / R,TL) | 10 |
| diagonal (L,TR / R,TL) | horizontal (L,R / TL,TR) | 9 |
| diagonal (L,TR / R,TL) | vertical (L,TL / R,TR) | 10 |
| diagonal (L,TR / R,TL) | diagonal (L,TR / R,TL) | 10 |

## 4. Schedule search (CEGAR: CP-SAT master, SAT counterexamples)

| d | Target | Flag on every trapezoid | Result |
|---:|---:|---|---|
| 5 | 5 | no | infeasible |
| 5 | 5 | yes | infeasible |
| 7 | 7 | no | infeasible |
| 7 | 7 | yes | infeasible |

Stored d = 9 schedule (`colorcode/schedules/d9_distance8.json`): circuit distance 8, against 7 for Kishony & Fowler, same qubits and depth. Every plaquette has its own order.

Going from 7 to 8 does not change the leading order of the logical error rate (both fail at 4 faults); the gain is in the prefactor. A better exponent needs d - 1 for every d (Kishony & Fowler lose about d/6), which first pays off at d = 15. Families repeated along each edge with period 1 or 2 (plus corner cells) were infeasible for d = 9 and 11 together; d = 11 itself is still open.

Runtime: 241s.
