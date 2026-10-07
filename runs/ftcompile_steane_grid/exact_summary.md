# Exact repairability of bridge-path choices (Steane flag round, 3x4 grid)

For each logical round (template x hub) the oracle asks whether ANY assignment of physical paths to the logical CNOTs is single-fault FT. Path language: all simple paths up to shortest + 2 hops. Placement, hubs, templates and check order are fixed. Exact: a CP-SAT model built from per-route Stim fault signatures (each fault depends only on its own route, because a bridge is exactly a CNOT on its endpoints); every reported solution is re-verified with the full-circuit Stim check.

## Can the round be made fault-tolerant by changing paths only?

| | rounds |
|---|---:|
| FT path assignment exists | 57 |
| provably none (in this path language) | 39 |
| total | 96 |

By syndrome hub and flag type:

| hub | flags | FT possible | impossible |
|---|---|---:|---:|
| 0 | A | 0 | 16 |
| 0 | B | 16 | 0 |
| 0 | A+B | 8 | 8 |
| 1 | A | 9 | 7 |
| 1 | B | 12 | 4 |
| 1 | A+B | 12 | 4 |

All oracle solutions re-verified with the full Stim check: True.

## How small can the repair be?

| Starting compilation | min routes changed (median / max, over FT-possible rounds) |
|---|---:|
| shortest paths | 7 / 11 |
| ancilla-first (Phase-7 rule) | 0 / 3 |

Cheapest FT assignment vs shortest-path compilation: median +0 CNOTs (range +0 to +24).

## Greedy repair vs the oracle

| Start from | greedy repaired | FT possible but greedy failed | impossible (greedy could not succeed) |
|---|---:|---:|---:|
| shortest | 40/96 | 17 | 39 |
| ancilla_first | 25/64 | 0 | 39 |

When greedy (from shortest) succeeded it changed 0 more routes than necessary (median; max 0).

The 39 rounds neither the Phase-7 rule nor greedy repair made FT: 0 are repairable by paths, 39 are provably not.

## Why the impossible rounds are impossible

| smallest blocking set | rounds |
|---|---:|
| route_with_no_safe_path: c0.i3 | 7 |
| route_with_no_safe_path: c3.i2 | 5 |
| single_check: Z0 | 5 |
| route_with_no_safe_path: c0.i3, c1.i3, c2.i3 | 4 |
| route_with_no_safe_path: c0.i3, c1.i3, c2.i3, c3.i2 | 3 |
| route_with_no_safe_path: c3.i2, c4.i2, c5.i2 | 3 |
| route_with_no_safe_path: c2.i3, c3.i2, c4.i2, c5.i2 | 2 |
| route_with_no_safe_path: c2.i3 | 2 |
| route_with_no_safe_path: c0.i3, c3.i2, c4.i2, c5.i2 | 2 |
| route_with_no_safe_path: c0.i5, c1.i5, c2.i5 | 2 |
| route_with_no_safe_path: c0.i3, c5.i2 | 1 |
| route_with_no_safe_path: c0.i5, c1.i5, c2.i5, c3.i4 | 1 |
| route_with_no_safe_path: c3.i4, c4.i4, c5.i4 | 1 |
| route_with_no_safe_path: c0.i5 | 1 |

Geometry: 79 of 79 blocked routes end at a data qubit that is not next to the other endpoint and whose every neighbour is another data qubit or the check's own flag, so every bridge to it passes through a qubit that is in use. Corner data qubits on this grid have only two neighbours: node 0 -> {1 (data), 4 (flag A)}, node 8 -> {4 (flag A), 9 (data)}, node 11 -> {7 (flag B), 10 (data)}, node 3 -> {2 (free), 7 (flag B)}.

Allowing paths up to shortest + 4 hops: 0 of 39 become FT-possible (39 still impossible).

## Scope

- Only physical paths are decision variables. Moving the syndrome hub, the placement, or reordering checks could rescue "impossible" rounds; that is not tested here.
- Same code, graph, placement and noise model as the case study (`summary.md`).
- Runtime: 292s.
