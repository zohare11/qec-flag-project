# Phase 10 summary

Scope: deterministic resource-constrained parallel scheduling of Phase-9 physically certified Steane extraction circuits.

The logical circuit and bridge routes are fixed before scheduling. Operations from different checks may overlap only when physical-qubit resources are disjoint, and every selected schedule is re-certified under its actual event order.

- Repeated extraction rounds for logical diagnostics: 3
- Phase-8/9 physical catalog size: 74
- Hard admissibility rule: ideal circuit preserved, C1=0, zero single-fault conflicts/failures, zero incoming-single-error failures.
- No learned policy is trained in Phase 10.

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

## Interpretation constraints

- Phase 10 parallelizes already-certified bridge-routed operations; it does not redesign stabilizer circuits or routing primitives.
- Prep, native-CX, and measurement operations have explicit durations. Same-check order is fixed; overlapping operations must use disjoint physical qubits.
- Data idling is derived from the actual parallel timeline at every event boundary.
- Resource-valid parallelism is not assumed fault tolerant. Every reported schedule is independently single-fault re-certified after reordering.
- The beam baseline searches static check-priority permutations, not arbitrary gate permutations and not a learned policy.
- Three-round logical diagnostics use the Phase-9 order-2 detector-hypergraph decoder and an ideal final memory-boundary syndrome.
- Hardware topology/calibrations remain synthetic; no crosstalk, leakage, pulse-level constraints, or real-backend calibration is modeled.

