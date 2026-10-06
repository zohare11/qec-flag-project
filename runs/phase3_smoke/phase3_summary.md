# Phase 3 summary

Scope: sequential synthesis of interaction schedules for one flagged Steane Z-check. This is not unrestricted circuit synthesis or a full noisy QEC cycle.

Lower C2 is better. Policy-greedy uses no online C2 search; policy-beam and random search use the stated finite exact-evaluation budget.

## Verification

- Phase 3A: 96 certified of 360 candidates.
- Phase 3B: 4896 certified of 10800 candidates.
- Phase 3B certified kinds: {'A_and_B': 4704, 'A_only': 96, 'B_only': 96}.

## Phase 3A — reconstruct the known one-flag family sequentially

### single_narrow

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 3.930467 | 134.00% | 0.00% |
| best_fixed_train | 2.725211 | 58.23% | 1.56% |
| random_search | 2.148922 | 25.04% | 9.38% |
| exhaustive_oracle | 1.762383 | 0.00% | 100.00% |
| policy_greedy (seed mean) | 2.494058 | 45.95% | 6.25% |
| policy_beam (seed mean) | 1.880476 | 7.34% | 40.62% |

### single_shift

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 9.061180 | 413.63% | 0.00% |
| best_fixed_train | 4.766009 | 99.94% | 6.25% |
| random_search | 3.705520 | 44.25% | 3.12% |
| exhaustive_oracle | 2.967416 | 0.00% | 100.00% |
| policy_greedy (seed mean) | 4.537731 | 93.91% | 6.25% |
| policy_beam (seed mean) | 3.269567 | 15.78% | 45.31% |

## Phase 3B — choose flag ancilla(s) and synthesize the schedule

### synthesis_id

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 16.126766 | 1430.27% | 0.00% |
| best_fixed_train | 5.665441 | 133.74% | 4.17% |
| random_search | 5.305933 | 106.90% | 0.00% |
| exhaustive_oracle | 3.204573 | 0.00% | 100.00% |
| one_flag_oracle | 3.204859 | 0.03% | 95.83% |
| policy_greedy (seed mean) | 4.089154 | 35.62% | 8.33% |
| policy_beam (seed mean) | 3.460894 | 11.65% | 31.25% |

Expanded-oracle circuit type: A_only=54.2%, B_only=41.7%, A_and_B=4.2%.
Two flags are oracle-selected in 4.2% of contexts; the expanded catalog strictly improves over the best one-flag schedule in 4.2%.

### ood_flagA_bad

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 274.908908 | 28307.64% | 0.00% |
| best_fixed_train | 19.575377 | 1615.15% | 0.00% |
| random_search | 11.192491 | 937.92% | 0.00% |
| exhaustive_oracle | 1.187319 | 0.00% | 100.00% |
| one_flag_oracle | 1.187319 | 0.00% | 100.00% |
| policy_greedy (seed mean) | 1.470928 | 26.26% | 8.33% |
| policy_beam (seed mean) | 1.259950 | 6.29% | 41.67% |

Expanded-oracle circuit type: A_only=0.0%, B_only=100.0%, A_and_B=0.0%.
Two flags are oracle-selected in 0.0% of contexts; the expanded catalog strictly improves over the best one-flag schedule in 0.0%.

### ood_both_flags_clean

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 1.381067 | 20.96% | 2.08% |
| best_fixed_train | 1.397628 | 23.08% | 0.00% |
| random_search | 1.298350 | 13.58% | 0.00% |
| exhaustive_oracle | 1.156759 | 0.00% | 100.00% |
| one_flag_oracle | 1.162613 | 0.59% | 54.17% |
| policy_greedy (seed mean) | 1.362531 | 20.29% | 0.00% |
| policy_beam (seed mean) | 1.243948 | 9.21% | 4.17% |

Expanded-oracle circuit type: A_only=25.0%, B_only=29.2%, A_and_B=45.8%.
Two flags are oracle-selected in 45.8% of contexts; the expanded catalog strictly improves over the best one-flag schedule in 45.8%.

## Finite-p diagnostics

These use one predeclared synthetic context per phase and ideal final recovery; they are component diagnostics only.

### Phase 3A

| Method | Schedule | Kind | p | failures/shots | rate | 95% interval |
|---|---|---|---:|---:|---:|---:|
| reference | 0A12A3 | A_only | 0.01 | 22/50000 | 0.0004400 | [0.0002906, 0.0006662] |
| learned_greedy | A3120A | A_only | 0.01 | 13/50000 | 0.0002600 | [0.0001520, 0.0004448] |
| oracle | A0321A | A_only | 0.01 | 10/50000 | 0.0002000 | [0.0001086, 0.0003681] |

### Phase 3B

| Method | Schedule | Kind | p | failures/shots | rate | 95% interval |
|---|---|---|---:|---:|---:|---:|
| reference | 0A12A3 | A_only | 0.005 | 3/50000 | 0.0000600 | [0.0000204, 0.0001764] |
| learned_greedy | B2103B | B_only | 0.005 | 1/50000 | 0.0000200 | [0.0000035, 0.0001133] |
| oracle | 2B03B1 | B_only | 0.005 | 0/50000 | 0.0000000 | [0.0000000, 0.0000768] |
| one_flag_oracle | 2B03B1 | B_only | 0.005 | 0/50000 | 0.0000000 | [0.0000000, 0.0000768] |

## Interpretation constraints

- The policy synthesizes an ordered interaction schedule inside a fixed grammar; it does not invent arbitrary gates.
- Exact exhaustive oracles are retained because both pilot spaces are still small enough to enumerate.
- Phase 3B adds a second available flag ancilla and variable one-flag/two-flag schedules; this is a real expansion of the candidate family.
- Synthetic noise families are controlled stress tests, not device calibration data.
- Certification assumes an ideal final syndrome and perfect recovery after this one check.
- A positive result here motivates larger synthesis spaces; it does not establish hardware or fault-tolerant quantum-computing advantage.
