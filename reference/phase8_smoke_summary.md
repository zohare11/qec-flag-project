# Phase 8 summary

Scope: gate-resolved serialized timing/idle validation of Phase-7 certified bridge circuits, followed by repeated-round Steane memory diagnostics.

Idle faults are explicit during every preparation block, native CNOT interval, and measurement block for each inactive persistent data qubit.

- Phase-7 source catalog: 74
- Still single-fault certified after gate-resolved idling: 74
- Repeated extraction rounds: 3
- Primary repeated-round decoder: minimum-weight fault-history decoder over full syndrome+flag history
- Baseline repeated-round decoder: temporal-majority syndrome + Steane minimum-weight correction

## Continuous-idle certification

- Rechecked circuits: 6
- Passed: 6
- Failed: 0

## hw_id

| Method | Mean round duration (us) | Mean native CX/round | p | Mean logical failure rate |
|---|---:|---:|---:|---:|
| certified_fixed | 39.543 | 150.0 | 0.0002 | 0.0050000 |
| certified_proxy | 39.543 | 150.0 | 0.0002 | 0.0040000 |
| certified_proxy_majority_baseline | 39.543 | 150.0 | 0.0002 | 0.0965000 |
| certified_random | 37.456 | 142.0 | 0.0002 | 0.0055000 |

## ood_idle_hotspot

| Method | Mean round duration (us) | Mean native CX/round | p | Mean logical failure rate |
|---|---:|---:|---:|---:|
| certified_fixed | 42.536 | 150.0 | 0.0002 | 0.0035000 |
| certified_proxy | 42.536 | 150.0 | 0.0002 | 0.0030000 |
| certified_proxy_majority_baseline | 42.536 | 150.0 | 0.0002 | 0.0640000 |
| certified_random | 39.446 | 142.0 | 0.0002 | 0.0060000 |

## Interpretation constraints

- The primary decoder is an exact small-code minimum-weight fault-history lookup over full syndrome+flag history; it is not MWPM/PyMatching.
- Temporal-majority Steane decoding is retained as a weaker recognizable baseline.
- This remains a synthetic 12-node hardware model; no named device calibration is used.
- Native bridge CNOT faults are explicit and data idling is now resolved at each serialized prep/CX/meas interval.
- Checks remain serialized; Phase 8 does not optimize parallel schedules or resource contention.
- Repeated rounds reuse the same routed extraction circuit without ideal recovery between rounds.
- The primary repeated-round decoder is a simple temporal-majority Steane minimum-weight baseline, not PyMatching/MWPM and not a scalable general decoder.
- The repeated-round Monte Carlo superposes Pauli fault signatures, valid for this Clifford/Pauli model.
- A positive result here validates the Phase-7 physical catalog under a stronger idle/time model; it does not establish device-level fault tolerance.

