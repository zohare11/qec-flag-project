# Phase 10 summary

Scope: deterministic resource-constrained parallel scheduling of Phase-9 physically certified Steane extraction circuits.

The logical circuit and bridge routes are fixed before scheduling. Operations from different checks may overlap only when physical-qubit resources are disjoint, and every selected schedule is re-certified under its actual event order.

- Repeated extraction rounds for logical diagnostics: 3
- Phase-8/9 physical catalog size: 74
- Hard admissibility rule: ideal circuit preserved, C1=0, zero single-fault conflicts/failures, zero incoming-single-error failures.
- No learned policy is trained in Phase 10.

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

## Interpretation constraints

- Phase 10 parallelizes already-certified bridge-routed operations; it does not redesign stabilizer circuits or routing primitives.
- Prep, native-CX, and measurement operations have explicit durations. Same-check order is fixed; overlapping operations must use disjoint physical qubits.
- Data idling is derived from the actual parallel timeline at every event boundary.
- Resource-valid parallelism is not assumed fault tolerant. Every reported schedule is independently single-fault re-certified after reordering.
- The beam baseline searches static check-priority permutations, not arbitrary gate permutations and not a learned policy.
- Three-round logical diagnostics use the Phase-9 order-2 detector-hypergraph decoder and an ideal final memory-boundary syndrome.
- Hardware topology/calibrations remain synthetic; no crosstalk, leakage, pulse-level constraints, or real-backend calibration is modeled.

