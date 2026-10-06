# Phase 6 summary

Scope: explicit native-routed-CNOT fault validation of schedules selected by the Phase-5 hardware-aware search pipeline.

Every routed SWAP is expanded into native CNOTs and every native CNOT receives its own 15-outcome Pauli fault location. Data idle faults are explicit at route boundaries. Lower native small-p score is better.

- Validation reference p: 0.0002; native score = p*C1 + p^2*C2.
- Phase-5 bounded-search budget used to select candidates before native validation: 8.
- Phase 6 does not retrain the policy; it validates schedules proposed by saved Phase-5 models.

## hw_id

| Method | Surrogate C2 | Native C1 | Native C2 | Native small-p score | Single-fault FT pass | Native CX | Duration (us) |
|---|---:|---:|---:|---:|---:|---:|---:|
| reference | 19270.272939 | 14.177969 | 33131.662926 | 0.00416086 | 0.0% | 180.0 | 45.090 |
| local_greedy | 14612.854587 | 6.394291 | 28223.542812 | 0.00240780 | 0.0% | 180.0 | 45.464 |
| random_search | 20876.883815 | 6.309916 | 37106.836446 | 0.00274626 | 0.0% | 230.0 | 58.605 |
| coordinate_search | 12777.689642 | 6.394291 | 24462.445074 | 0.00225736 | 0.0% | 180.0 | 45.464 |
| policy_beam_seed0 | 66694.362731 | 6.394291 | 61982.284939 | 0.00375815 | 0.0% | 228.0 | 57.670 |

- Mean within-context Spearman rank correlation, surrogate C2 vs explicit native score: 0.700.
- Surrogate and native models select the same best listed method in 100.0% of contexts.
- Policy-seed mean vs coordinate: win fraction 0.0%; mean native-score change 66.48%.
- Policy-seed mean vs local greedy: win fraction 0.0%.
- Policy-seed mean vs random search: win fraction 0.0%.

## Explicit finite-p native diagnostics

These use the first fresh `hw_id` validation context. Faults are sampled directly at native CNOT, preparation/readout, and route-boundary idle locations.

| Method | p | failures/shots | logical failure rate | 95% interval | C1 | C2 |
|---|---:|---:|---:|---:|---:|---:|
| reference | 0.0001 | 4/2000 | 0.0020000 | [0.0007780, 0.0051314] | 14.177969 | 33131.662926 |
| reference | 0.0002 | 10/2000 | 0.0050000 | [0.0027182, 0.0091797] | 14.177969 | 33131.662926 |
| local_greedy | 0.0001 | 4/2000 | 0.0020000 | [0.0007780, 0.0051314] | 6.394291 | 28223.542812 |
| local_greedy | 0.0002 | 5/2000 | 0.0025000 | [0.0010683, 0.0058392] | 6.394291 | 28223.542812 |
| coordinate_search | 0.0001 | 0/2000 | 0.0000000 | [0.0000000, 0.0019170] | 6.394291 | 24462.445074 |
| coordinate_search | 0.0002 | 4/2000 | 0.0020000 | [0.0007780, 0.0051314] | 6.394291 | 24462.445074 |
| policy_beam_seed0 | 0.0001 | 1/2000 | 0.0005000 | [0.0000883, 0.0028269] | 6.394291 | 61982.284939 |
| policy_beam_seed0 | 0.0002 | 9/2000 | 0.0045000 | [0.0023693, 0.0085305] | 6.394291 | 61982.284939 |

## Interpretation constraints

- The hardware graph and calibration families remain synthetic; this is not a named device calibration.
- Routing CNOT faults are now propagated gate by gate. This is the main Phase-6 upgrade over Phase 5.
- Idle faults are explicit once per route boundary for nonparticipating persistent data qubits, but continuous-time idling during each individual native sub-gate is still approximated.
- The native two-qubit Pauli channel on each routed CNOT reuses the corresponding logical-interaction 15-outcome profile, scaled by the physical-edge multiplier.
- The schedule-specific decoder still uses the noisy extraction record plus an ideal final memory-boundary syndrome.
- Any nonzero native C1 or failure of the single-fault checks means the routed implementation is not first-order fault tolerant under this model; C2 alone must not then be treated as the leading logical-failure term.
- Phase 6 is a validation study, not a new RL training phase.

