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

## Interpretation constraints

- Phase 10 parallelizes already-certified bridge-routed operations; it does not redesign stabilizer circuits or routing primitives.
- Prep, native-CX, and measurement operations have explicit durations. Same-check order is fixed; overlapping operations must use disjoint physical qubits.
- Data idling is derived from the actual parallel timeline at every event boundary.
- Resource-valid parallelism is not assumed fault tolerant. Every reported schedule is independently single-fault re-certified after reordering.
- The beam baseline searches static check-priority permutations, not arbitrary gate permutations and not a learned policy.
- Three-round logical diagnostics use the Phase-9 order-2 detector-hypergraph decoder and an ideal final memory-boundary syndrome.
- Hardware topology/calibrations remain synthetic; no crosstalk, leakage, pulse-level constraints, or real-backend calibration is modeled.

