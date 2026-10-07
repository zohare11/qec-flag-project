# Where should the qubits go? Placement search on the 3x4 grid

A placement assigns the 7 Steane data qubits (d0-d6), the two syndrome hubs (H0, H1) and the two flags (FA, FB) to the 12 grid nodes (one node stays free, ".."). Its score is how many of the 96 logical rounds (48 certified flag templates x 2 hubs) can be routed single-fault FT by choosing bridge paths (all simple paths up to shortest + 2 hops). Each score is exact; every reported routing is re-verified with the full Stim check.

## Result

| Placement | FT-routable rounds | cheapest FT round (CNOTs) | median CNOTs over routable rounds | median extra CNOTs for FT vs shortest paths | all verified |
|---|---:|---:|---:|---:|---|
| current (Phase 5-7 layout) | 57/96 | 142 | 162 | +0 | True |
| every round FT-routable, cheapest found | 96/96 | 136 | 201 | +16 | True |
| cheapest single FT round found | 29/96 | 78 | 162 | +0 | True |
| random placements (200) | median 0, max 90 | | | | |

194 of 200 random placements make no round fault-tolerant at all.

current (Phase 5-7 layout):

```
d0 d4 .. d1
FA H0 H1 FB
d2 d6 d5 d3
```

every round FT-routable, cheapest found:

```
FB d4 d3 d6
d2 H0 .. FA
d1 H1 d0 d5
```

cheapest single FT round found:

```
H1 d5 d2 d1
d3 .. H0 FB
FA d4 d0 d6
```

On the 57 rounds routable with both, the full-coverage layout needs +24 CNOTs vs the current layout (median; range -22 to +108).

### Logical error rate of each layout's cheapest FT round

Cheapest FT routing of the layout's cheapest round; "unrouted" is the same template with all-to-all connectivity (no routing overhead). Order-2 lookup decoder, one round, ideal final read-out.

| Layout | template, hub | CNOTs | p = 0.001 | p = 0.0005 | unrouted p = 0.001 | unrouted p = 0.0005 |
|---|---|---:|---:|---:|---:|---:|
| current | B3201B, H1 | 142 | 6.44e-03 | 1.72e-03 | 5.90e-04 | 1.61e-04 |
| full_coverage | A3201A, H0 | 136 | 5.20e-03 | 1.34e-03 | 5.88e-04 | 1.62e-04 |
| cheapest_round | B3201B, H0 | 78 | 2.71e-03 | 5.80e-04 | 5.58e-04 | 1.61e-04 |

## Search

| objective | start | FT-routable rounds | mean cost proxy | cheapest-round proxy | placements evaluated |
|---|---|---:|---:|---:|---:|
| coverage | current layout | 96 | 208.7 | 142 | 18 |
| coverage | random | 94 | 255.9 | 174 | 289 |
| coverage | random | 96 | 201.7 | 142 | 115 |
| coverage | random | 89 | 249.8 | 186 | 293 |
| cost | best coverage layout | 96 | 194.7 | 136 | 352 |
| cost | best coverage layout | 96 | 194.7 | 130 | 362 |
| cost | best coverage layout | 96 | 194.7 | 130 | 351 |
| cost | best coverage layout | 96 | 194.7 | 136 | 348 |
| cheapest | current layout | 29 | 154.6 | 78 | 376 |
| cheapest | full-coverage layout | 8 | 81.0 | 78 | 375 |
| cheapest | random | 29 | 154.6 | 78 | 361 |
| cheapest | random | 33 | 147.8 | 78 | 372 |

Cost proxy of a round = sum over its logical CNOTs of the cheapest safe path (a lower bound on its cheapest FT routing).

## Scope

- One code (Steane, flagged six-check round), one 12-node grid, fixed check order; only placement and bridge paths vary.
- Rounds use the same flag template on all six checks; mixing templates per check is not explored.
- The search is heuristic (simulated annealing), so "best found" is not proven optimal; each score is exact.
- Runtime: 1768s.
