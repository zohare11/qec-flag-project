# Phase 8 summary

Scope: gate-resolved serialized timing/idle validation of Phase-7 certified bridge circuits, followed by repeated-round Steane memory diagnostics.

Idle faults are explicit during every preparation block, native CNOT interval, and measurement block for each inactive persistent data qubit.

- Phase-7 source catalog: 74
- Still single-fault certified after gate-resolved idling: 74
- Repeated extraction rounds: 3
- Primary repeated-round decoder: minimum-weight fault-history decoder over full syndrome+flag history
- Baseline repeated-round decoder: temporal-majority syndrome + Steane minimum-weight correction

## Continuous-idle certification

- Rechecked circuits: 30
- Passed: 30
- Failed: 0

## hw_id

| Method | Mean round duration (us) | Mean native CX/round | p | Mean logical failure rate |
|---|---:|---:|---:|---:|
| certified_fixed | 43.137 | 150.0 | 0.0001 | 0.0000500 |
| certified_fixed | 43.137 | 150.0 | 0.0002 | 0.0003500 |
| certified_fixed | 43.137 | 150.0 | 0.0005 | 0.0029000 |
| certified_proxy | 42.392 | 146.0 | 0.0001 | 0.0001500 |
| certified_proxy | 42.392 | 146.0 | 0.0002 | 0.0004500 |
| certified_proxy | 42.392 | 146.0 | 0.0005 | 0.0043500 |
| certified_proxy_majority_baseline | 42.392 | 146.0 | 0.0001 | 0.0139000 |
| certified_proxy_majority_baseline | 42.392 | 146.0 | 0.0002 | 0.0271000 |
| certified_proxy_majority_baseline | 42.392 | 146.0 | 0.0005 | 0.0657500 |
| certified_random | 46.084 | 166.0 | 0.0001 | 0.0003500 |
| certified_random | 46.084 | 166.0 | 0.0002 | 0.0007500 |
| certified_random | 46.084 | 166.0 | 0.0005 | 0.0053500 |

## ood_idle_hotspot

| Method | Mean round duration (us) | Mean native CX/round | p | Mean logical failure rate |
|---|---:|---:|---:|---:|
| certified_fixed | 40.404 | 150.0 | 0.0001 | 0.0007000 |
| certified_fixed | 40.404 | 150.0 | 0.0002 | 0.0030000 |
| certified_fixed | 40.404 | 150.0 | 0.0005 | 0.0142500 |
| certified_proxy | 44.109 | 164.0 | 0.0001 | 0.0003500 |
| certified_proxy | 44.109 | 164.0 | 0.0002 | 0.0015000 |
| certified_proxy | 44.109 | 164.0 | 0.0005 | 0.0119000 |
| certified_proxy_majority_baseline | 44.109 | 164.0 | 0.0001 | 0.0258000 |
| certified_proxy_majority_baseline | 44.109 | 164.0 | 0.0002 | 0.0518500 |
| certified_proxy_majority_baseline | 44.109 | 164.0 | 0.0005 | 0.1259500 |
| certified_random | 38.125 | 142.0 | 0.0001 | 0.0005000 |
| certified_random | 38.125 | 142.0 | 0.0002 | 0.0026500 |
| certified_random | 38.125 | 142.0 | 0.0005 | 0.0143500 |

## ood_slow_link

| Method | Mean round duration (us) | Mean native CX/round | p | Mean logical failure rate |
|---|---:|---:|---:|---:|
| certified_fixed | 53.076 | 150.0 | 0.0001 | 0.0003000 |
| certified_fixed | 53.076 | 150.0 | 0.0002 | 0.0013500 |
| certified_fixed | 53.076 | 150.0 | 0.0005 | 0.0075500 |
| certified_proxy | 54.942 | 146.0 | 0.0001 | 0.0003000 |
| certified_proxy | 54.942 | 146.0 | 0.0002 | 0.0013000 |
| certified_proxy | 54.942 | 146.0 | 0.0005 | 0.0056500 |
| certified_proxy_majority_baseline | 54.942 | 146.0 | 0.0001 | 0.0155500 |
| certified_proxy_majority_baseline | 54.942 | 146.0 | 0.0002 | 0.0338000 |
| certified_proxy_majority_baseline | 54.942 | 146.0 | 0.0005 | 0.0806000 |
| certified_random | 54.005 | 142.0 | 0.0001 | 0.0004000 |
| certified_random | 54.005 | 142.0 | 0.0002 | 0.0013000 |
| certified_random | 54.005 | 142.0 | 0.0005 | 0.0064000 |

## ood_logical_shift

| Method | Mean round duration (us) | Mean native CX/round | p | Mean logical failure rate |
|---|---:|---:|---:|---:|
| certified_fixed | 40.440 | 150.0 | 0.0001 | 0.0001000 |
| certified_fixed | 40.440 | 150.0 | 0.0002 | 0.0011500 |
| certified_fixed | 40.440 | 150.0 | 0.0005 | 0.0050500 |
| certified_proxy | 40.440 | 150.0 | 0.0001 | 0.0002000 |
| certified_proxy | 40.440 | 150.0 | 0.0002 | 0.0010000 |
| certified_proxy | 40.440 | 150.0 | 0.0005 | 0.0048500 |
| certified_proxy_majority_baseline | 40.440 | 150.0 | 0.0001 | 0.0142500 |
| certified_proxy_majority_baseline | 40.440 | 150.0 | 0.0002 | 0.0289000 |
| certified_proxy_majority_baseline | 40.440 | 150.0 | 0.0005 | 0.0747500 |
| certified_random | 44.281 | 170.0 | 0.0001 | 0.0001000 |
| certified_random | 44.281 | 170.0 | 0.0002 | 0.0017000 |
| certified_random | 44.281 | 170.0 | 0.0005 | 0.0079000 |

## ood_mixed

| Method | Mean round duration (us) | Mean native CX/round | p | Mean logical failure rate |
|---|---:|---:|---:|---:|
| certified_fixed | 49.833 | 150.0 | 0.0001 | 0.0170000 |
| certified_fixed | 49.833 | 150.0 | 0.0002 | 0.0474500 |
| certified_fixed | 49.833 | 150.0 | 0.0005 | 0.1281500 |
| certified_proxy | 49.833 | 150.0 | 0.0001 | 0.0055500 |
| certified_proxy | 49.833 | 150.0 | 0.0002 | 0.0186500 |
| certified_proxy | 49.833 | 150.0 | 0.0005 | 0.0634500 |
| certified_proxy_majority_baseline | 49.833 | 150.0 | 0.0001 | 0.0795500 |
| certified_proxy_majority_baseline | 49.833 | 150.0 | 0.0002 | 0.1487000 |
| certified_proxy_majority_baseline | 49.833 | 150.0 | 0.0005 | 0.3502000 |
| certified_random | 46.491 | 142.0 | 0.0001 | 0.0057000 |
| certified_random | 46.491 | 142.0 | 0.0002 | 0.0171000 |
| certified_random | 46.491 | 142.0 | 0.0005 | 0.0720000 |

## Interpretation constraints

- The primary decoder is an exact small-code minimum-weight fault-history lookup over full syndrome+flag history; it is not MWPM/PyMatching.
- Temporal-majority Steane decoding is retained as a weaker recognizable baseline.
- This remains a synthetic 12-node hardware model; no named device calibration is used.
- Native bridge CNOT faults are explicit and data idling is now resolved at each serialized prep/CX/meas interval.
- Checks remain serialized; Phase 8 does not optimize parallel schedules or resource contention.
- Repeated rounds reuse the same routed extraction circuit without ideal recovery between rounds.
- The primary repeated-round decoder uses the complete noisy syndrome+flag history plus an ideal final memory-boundary syndrome; it is a small-code exact minimum-weight lookup, not MWPM/PyMatching.
- The repeated-round Monte Carlo superposes Pauli fault signatures, valid for this Clifford/Pauli model.
- A positive result here validates the Phase-7 physical catalog under a stronger idle/time model; it does not establish device-level fault tolerance.

