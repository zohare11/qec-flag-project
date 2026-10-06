# Phase 6 summary

Scope: explicit native-routed-CNOT fault validation of schedules selected by the Phase-5 hardware-aware search pipeline.

Every routed SWAP is expanded into native CNOTs and every native CNOT receives its own 15-outcome Pauli fault location. Data idle faults are explicit at route boundaries. Lower native small-p score is better.

- Validation reference p: 0.0002; native score = p*C1 + p^2*C2.
- Phase-5 bounded-search budget used to select candidates before native validation: 8.
- Phase 6 does not retrain the policy; it validates schedules proposed by saved Phase-5 models.

## hw_id

| Method | Surrogate C2 | Native C1 | Native C2 | Native small-p score | Single-fault FT pass | Native CX | Duration (us) |
|---|---:|---:|---:|---:|---:|---:|---:|
| reference | 9984.248616 | 12.744097 | 12953.783102 | 0.00306697 | 0.0% | 180.0 | 44.791 |
| local_greedy | 9583.505141 | 13.868428 | 14850.609049 | 0.00336771 | 0.0% | 180.0 | 45.115 |
| random_search | 25842.173584 | 14.464844 | 24487.814151 | 0.00387248 | 0.0% | 254.0 | 62.853 |
| coordinate_search | 9454.822104 | 14.390698 | 14866.253654 | 0.00347279 | 0.0% | 180.0 | 45.115 |
| policy_beam_seed0 | 23683.987776 | 14.385923 | 24554.837976 | 0.00385938 | 0.0% | 228.0 | 56.886 |
| policy_beam_seed1 | 12281.094755 | 11.258052 | 15409.024620 | 0.00286797 | 0.0% | 180.0 | 45.115 |
| policy_beam_seed2 | 76176.927610 | 33.633239 | 49265.627505 | 0.00869727 | 0.0% | 270.0 | 68.101 |

- Mean within-context Spearman rank correlation, surrogate C2 vs explicit native score: 0.643.
- Surrogate and native models select the same best listed method in 0.0% of contexts.
- Policy-seed mean vs coordinate: win fraction 0.0%; mean native-score change 48.05%.
- Policy-seed mean vs local greedy: win fraction 0.0%.
- Policy-seed mean vs random search: win fraction 0.0%.

## Explicit finite-p native diagnostics

These use the first fresh `hw_id` validation context. Faults are sampled directly at native CNOT, preparation/readout, and route-boundary idle locations.

| Method | p | failures/shots | logical failure rate | 95% interval | C1 | C2 |
|---|---:|---:|---:|---:|---:|---:|
| reference | 0.0002 | 2/1000 | 0.0020000 | [0.0005486, 0.0072628] | 12.744097 | 12953.783102 |
| local_greedy | 0.0002 | 3/1000 | 0.0030000 | [0.0010208, 0.0087830] | 13.868428 | 14850.609049 |
| coordinate_search | 0.0002 | 1/1000 | 0.0010000 | [0.0001765, 0.0056426] | 14.390698 | 14866.253654 |
| policy_beam_seed0 | 0.0002 | 5/1000 | 0.0050000 | [0.0021375, 0.0116510] | 14.385923 | 24554.837976 |

## Interpretation constraints

- The hardware graph and calibration families remain synthetic; this is not a named device calibration.
- Routing CNOT faults are now propagated gate by gate. This is the main Phase-6 upgrade over Phase 5.
- Idle faults are explicit once per route boundary for nonparticipating persistent data qubits, but continuous-time idling during each individual native sub-gate is still approximated.
- The native two-qubit Pauli channel on each routed CNOT reuses the corresponding logical-interaction 15-outcome profile, scaled by the physical-edge multiplier.
- The schedule-specific decoder still uses the noisy extraction record plus an ideal final memory-boundary syndrome.
- Any nonzero native C1 or failure of the single-fault checks means the routed implementation is not first-order fault tolerant under this model; C2 alone must not then be treated as the leading logical-failure term.
- Phase 6 is a validation study, not a new RL training phase.

