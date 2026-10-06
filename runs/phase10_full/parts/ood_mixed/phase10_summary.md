# Phase 10 summary

Scope: deterministic resource-constrained parallel scheduling of Phase-9 physically certified Steane extraction circuits.

The logical circuit and bridge routes are fixed before scheduling. Operations from different checks may overlap only when physical-qubit resources are disjoint, and every selected schedule is re-certified under its actual event order.

- Repeated extraction rounds for logical diagnostics: 3
- Phase-8/9 physical catalog size: 74
- Hard admissibility rule: ideal circuit preserved, C1=0, zero single-fault conflicts/failures, zero incoming-single-error failures.
- No learned policy is trained in Phase 10.

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

