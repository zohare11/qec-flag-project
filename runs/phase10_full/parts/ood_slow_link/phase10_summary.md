# Phase 10 summary

Scope: deterministic resource-constrained parallel scheduling of Phase-9 physically certified Steane extraction circuits.

The logical circuit and bridge routes are fixed before scheduling. Operations from different checks may overlap only when physical-qubit resources are disjoint, and every selected schedule is re-certified under its actual event order.

- Repeated extraction rounds for logical diagnostics: 3
- Phase-8/9 physical catalog size: 74
- Hard admissibility rule: ideal circuit preserved, C1=0, zero single-fault conflicts/failures, zero incoming-single-error failures.
- No learned policy is trained in Phase 10.

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

## Interpretation constraints

- Phase 10 parallelizes already-certified bridge-routed operations; it does not redesign stabilizer circuits or routing primitives.
- Prep, native-CX, and measurement operations have explicit durations. Same-check order is fixed; overlapping operations must use disjoint physical qubits.
- Data idling is derived from the actual parallel timeline at every event boundary.
- Resource-valid parallelism is not assumed fault tolerant. Every reported schedule is independently single-fault re-certified after reordering.
- The beam baseline searches static check-priority permutations, not arbitrary gate permutations and not a learned policy.
- Three-round logical diagnostics use the Phase-9 order-2 detector-hypergraph decoder and an ideal final memory-boundary syndrome.
- Hardware topology/calibrations remain synthetic; no crosstalk, leakage, pulse-level constraints, or real-backend calibration is modeled.

