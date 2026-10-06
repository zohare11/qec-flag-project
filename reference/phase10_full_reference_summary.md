# Phase 10 summary

Scope: deterministic resource-constrained parallel scheduling of Phase-9 physically certified Steane extraction circuits.

The logical circuit and bridge routes are fixed before scheduling. Operations from different checks may overlap only when physical-qubit resources are disjoint, and every selected schedule is re-certified under its actual event order.

- Repeated extraction rounds for logical diagnostics: 3
- Phase-8/9 physical catalog size: 74
- Hard admissibility rule: ideal circuit preserved, C1=0, zero single-fault conflicts/failures, zero incoming-single-error failures.
- No learned policy is trained in Phase 10.

## hw_id

| Method | Duration (us) | vs serial | Data idle (us) | Max parallel CX | C1 | FT pass |
|---|---:|---:|---:|---:|---:|---:|
| serialized | 39.543 | +0.00% | 265.928 | 1.00 | 0 | 100% |
| ancilla_overlap | 39.043 | -1.26% | 262.428 | 1.00 | 0 | 100% |
| asap | 26.155 | -33.86% | 172.212 | 3.00 | 7.97692 | 0% |
| shortest_greedy | 24.274 | -38.61% | 159.046 | 3.00 | 1.80326 | 0% |
| critical_greedy | 26.816 | -32.18% | 176.843 | 3.00 | 26.74 | 0% |
| noise_greedy | 24.929 | -36.96% | 163.631 | 3.00 | 6.29632 | 0% |
| css_block | 26.055 | -34.11% | 171.510 | 3.00 | 6.53226 | 0% |
| local_search | 25.253 | -36.14% | 165.896 | 3.00 | 14.2731 | 0% |
| beam_search | 25.078 | -36.58% | 164.676 | 4.00 | 3.3973 | 0% |

- FT-safe methods/context mean: 2.00 / 9.
- Aggressive schedules with native-CX concurrency that remained FT: 0 / 7.
- Best FT-safe mean duration: 39.043 us (1.26% faster than serialized).

### Repeated-round detector diagnostics

| Method | p | Mean logical failure rate |
|---|---:|---:|
| ancilla_overlap | 0.0002 | 0.0000000 |
| serialized | 0.0002 | 0.0000000 |

## ood_idle_hotspot

| Method | Duration (us) | vs serial | Data idle (us) | Max parallel CX | C1 | FT pass |
|---|---:|---:|---:|---:|---:|---:|
| serialized | 45.583 | +0.00% | 307.752 | 1.00 | 0 | 100% |
| ancilla_overlap | 45.172 | -0.90% | 304.876 | 1.00 | 0 | 100% |
| asap | 36.140 | -20.72% | 241.647 | 3.00 | 14.5833 | 0% |
| shortest_greedy | 32.186 | -29.39% | 213.973 | 3.00 | 27.8639 | 0% |
| critical_greedy | 31.291 | -31.35% | 207.704 | 3.00 | 89.9798 | 0% |
| noise_greedy | 32.828 | -27.98% | 218.464 | 3.00 | 18.0544 | 0% |
| css_block | 38.843 | -14.79% | 260.568 | 2.00 | 1.34187 | 0% |
| local_search | 32.986 | -27.64% | 219.570 | 3.00 | 16.0757 | 0% |
| beam_search | 33.292 | -26.96% | 221.712 | 3.00 | 9.33151 | 0% |

- FT-safe methods/context mean: 2.00 / 9.
- Aggressive schedules with native-CX concurrency that remained FT: 0 / 7.
- Best FT-safe mean duration: 45.172 us (0.90% faster than serialized).

### Repeated-round detector diagnostics

| Method | p | Mean logical failure rate |
|---|---:|---:|
| ancilla_overlap | 0.0002 | 0.0016000 |
| serialized | 0.0002 | 0.0022000 |

## ood_slow_link

| Method | Duration (us) | vs serial | Data idle (us) | Max parallel CX | C1 | FT pass |
|---|---:|---:|---:|---:|---:|---:|
| serialized | 41.491 | +0.00% | 280.002 | 1.00 | 0 | 100% |
| ancilla_overlap | 41.021 | -1.13% | 276.714 | 1.00 | 0 | 100% |
| asap | 29.208 | -29.60% | 194.024 | 3.00 | 9.90072 | 0% |
| shortest_greedy | 26.301 | -36.61% | 173.676 | 3.00 | 39.7244 | 0% |
| critical_greedy | 29.912 | -27.91% | 198.949 | 3.00 | 56.4142 | 0% |
| noise_greedy | 26.326 | -36.55% | 173.847 | 3.00 | 6.22013 | 0% |
| css_block | 33.281 | -19.79% | 222.532 | 3.00 | 1.01724 | 0% |
| local_search | 27.184 | -34.48% | 179.853 | 3.00 | 52.667 | 0% |
| beam_search | 27.184 | -34.48% | 179.853 | 3.00 | 52.667 | 0% |

- FT-safe methods/context mean: 2.00 / 9.
- Aggressive schedules with native-CX concurrency that remained FT: 0 / 7.
- Best FT-safe mean duration: 41.021 us (1.13% faster than serialized).

### Repeated-round detector diagnostics

| Method | p | Mean logical failure rate |
|---|---:|---:|
| ancilla_overlap | 0.0002 | 0.0004000 |
| serialized | 0.0002 | 0.0002000 |

## ood_logical_shift

| Method | Duration (us) | vs serial | Data idle (us) | Max parallel CX | C1 | FT pass |
|---|---:|---:|---:|---:|---:|---:|
| serialized | 38.510 | +0.00% | 258.675 | 1.00 | 0 | 100% |
| ancilla_overlap | 38.010 | -1.30% | 255.175 | 1.00 | 0 | 100% |
| asap | 25.964 | -32.58% | 170.852 | 3.00 | 0.0620109 | 0% |
| shortest_greedy | 25.907 | -32.73% | 170.457 | 3.00 | 7.42823 | 0% |
| critical_greedy | 25.231 | -34.48% | 165.724 | 3.00 | 71.8926 | 0% |
| noise_greedy | 26.750 | -30.54% | 176.355 | 3.00 | 0.958991 | 0% |
| css_block | 28.262 | -26.61% | 186.937 | 3.00 | 0.750413 | 0% |
| local_search | 22.288 | -42.12% | 145.125 | 3.00 | 0.435613 | 0% |
| beam_search | 22.288 | -42.12% | 145.125 | 3.00 | 0.435613 | 0% |

- FT-safe methods/context mean: 2.00 / 9.
- Aggressive schedules with native-CX concurrency that remained FT: 0 / 7.
- Best FT-safe mean duration: 38.010 us (1.30% faster than serialized).

### Repeated-round detector diagnostics

| Method | p | Mean logical failure rate |
|---|---:|---:|
| ancilla_overlap | 0.0002 | 0.0000000 |
| serialized | 0.0002 | 0.0000000 |

## ood_mixed

| Method | Duration (us) | vs serial | Data idle (us) | Max parallel CX | C1 | FT pass |
|---|---:|---:|---:|---:|---:|---:|
| serialized | 43.174 | +0.00% | 290.970 | 1.00 | 0 | 100% |
| ancilla_overlap | 42.674 | -1.16% | 287.470 | 1.00 | 0 | 100% |
| asap | 30.186 | -30.08% | 200.053 | 3.00 | 2.81075 | 0% |
| shortest_greedy | 30.112 | -30.25% | 199.538 | 3.00 | 2.31906 | 0% |
| critical_greedy | 30.501 | -29.35% | 202.261 | 3.00 | 171.404 | 0% |
| noise_greedy | 30.612 | -29.10% | 203.038 | 3.00 | 74.9874 | 0% |
| css_block | 30.904 | -28.42% | 205.077 | 3.00 | 3.73411 | 0% |
| local_search | 26.217 | -39.28% | 172.271 | 3.00 | 5.83358 | 0% |
| beam_search | 25.913 | -39.98% | 170.145 | 3.00 | 5.46473 | 0% |

- FT-safe methods/context mean: 2.00 / 9.
- Aggressive schedules with native-CX concurrency that remained FT: 0 / 7.
- Best FT-safe mean duration: 42.674 us (1.16% faster than serialized).

### Repeated-round detector diagnostics

| Method | p | Mean logical failure rate |
|---|---:|---:|
| ancilla_overlap | 0.0002 | 0.0020000 |
| serialized | 0.0002 | 0.0016000 |

## Interpretation constraints

- Phase 10 parallelizes already-certified bridge-routed operations; it does not redesign stabilizer circuits or routing primitives.
- Prep, native-CX, and measurement operations have explicit durations. Same-check order is fixed; overlapping operations must use disjoint physical qubits.
- Data idling is derived from the actual parallel timeline at every event boundary.
- Resource-valid parallelism is not assumed fault tolerant. Every reported schedule is independently single-fault re-certified after reordering.
- The beam baseline searches static check-priority permutations, not arbitrary gate permutations and not a learned policy.
- Three-round logical diagnostics use the Phase-9 order-2 detector-hypergraph decoder and an ideal final memory-boundary syndrome.
- Hardware topology/calibrations remain synthetic; no crosstalk, leakage, pulse-level constraints, or real-backend calibration is modeled.

