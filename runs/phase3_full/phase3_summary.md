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
| reference | 3.908133 | 134.62% | 0.00% |
| best_fixed_train | 2.653506 | 59.62% | 1.04% |
| random_search | 1.951800 | 14.54% | 11.46% |
| exhaustive_oracle | 1.715042 | 0.00% | 100.00% |
| policy_greedy (seed mean) | 2.417782 | 43.37% | 6.60% |
| policy_beam (seed mean) | 1.779047 | 3.66% | 64.93% |

### single_shift

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 8.062917 | 421.81% | 0.00% |
| best_fixed_train | 5.144407 | 136.72% | 5.21% |
| random_search | 3.260293 | 24.47% | 13.54% |
| exhaustive_oracle | 2.827801 | 0.00% | 100.00% |
| policy_greedy (seed mean) | 4.567036 | 102.36% | 6.25% |
| policy_beam (seed mean) | 3.006614 | 9.41% | 56.25% |

## Phase 3B — choose flag ancilla(s) and synthesize the schedule

### synthesis_id

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 16.126766 | 1430.27% | 0.00% |
| best_fixed_train | 6.234036 | 287.69% | 0.00% |
| random_search | 4.628894 | 82.22% | 0.00% |
| exhaustive_oracle | 3.204573 | 0.00% | 100.00% |
| one_flag_oracle | 3.204859 | 0.03% | 95.83% |
| policy_greedy (seed mean) | 4.220006 | 42.19% | 2.78% |
| policy_beam (seed mean) | 3.429258 | 7.81% | 40.28% |

Expanded-oracle circuit type: A_only=54.2%, B_only=41.7%, A_and_B=4.2%.
Two flags are oracle-selected in 4.2% of contexts; the expanded catalog strictly improves over the best one-flag schedule in 4.2%.

### ood_flagA_bad

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 274.908908 | 28307.64% | 0.00% |
| best_fixed_train | 1.611337 | 41.80% | 2.08% |
| random_search | 5.876672 | 410.52% | 0.00% |
| exhaustive_oracle | 1.187319 | 0.00% | 100.00% |
| one_flag_oracle | 1.187319 | 0.00% | 100.00% |
| policy_greedy (seed mean) | 1.526947 | 30.85% | 2.78% |
| policy_beam (seed mean) | 1.223804 | 3.28% | 54.17% |

Expanded-oracle circuit type: A_only=0.0%, B_only=100.0%, A_and_B=0.0%.
Two flags are oracle-selected in 0.0% of contexts; the expanded catalog strictly improves over the best one-flag schedule in 0.0%.

### ood_flagB_bad

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 1.981597 | 51.04% | 0.00% |
| best_fixed_train | 19.003842 | 1570.61% | 0.00% |
| random_search | 6.313467 | 446.33% | 0.00% |
| exhaustive_oracle | 1.342098 | 0.00% | 100.00% |
| one_flag_oracle | 1.342098 | 0.00% | 100.00% |
| policy_greedy (seed mean) | 1.707019 | 27.78% | 6.94% |
| policy_beam (seed mean) | 1.382038 | 2.95% | 54.86% |

Expanded-oracle circuit type: A_only=100.0%, B_only=0.0%, A_and_B=0.0%.
Two flags are oracle-selected in 0.0% of contexts; the expanded catalog strictly improves over the best one-flag schedule in 0.0%.

### ood_both_flags_clean

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 1.381067 | 20.96% | 2.08% |
| best_fixed_train | 1.388327 | 20.77% | 0.00% |
| random_search | 1.264813 | 10.87% | 0.00% |
| exhaustive_oracle | 1.156759 | 0.00% | 100.00% |
| one_flag_oracle | 1.162613 | 0.59% | 54.17% |
| policy_greedy (seed mean) | 1.380627 | 20.55% | 1.39% |
| policy_beam (seed mean) | 1.221699 | 6.69% | 4.17% |

Expanded-oracle circuit type: A_only=25.0%, B_only=29.2%, A_and_B=45.8%.
Two flags are oracle-selected in 45.8% of contexts; the expanded catalog strictly improves over the best one-flag schedule in 45.8%.

### ood_data_hotspot

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 24.539716 | 118.53% | 0.00% |
| best_fixed_train | 20.345538 | 79.52% | 0.00% |
| random_search | 14.036073 | 22.77% | 0.00% |
| exhaustive_oracle | 11.541854 | 0.00% | 100.00% |
| one_flag_oracle | 11.541854 | 0.00% | 100.00% |
| policy_greedy (seed mean) | 15.513804 | 35.12% | 0.69% |
| policy_beam (seed mean) | 12.395835 | 7.87% | 11.81% |

Expanded-oracle circuit type: A_only=37.5%, B_only=62.5%, A_and_B=0.0%.
Two flags are oracle-selected in 0.0% of contexts; the expanded catalog strictly improves over the best one-flag schedule in 0.0%.

### ood_readout_hotspot

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 7.951780 | 229.14% | 0.00% |
| best_fixed_train | 7.083375 | 182.14% | 2.08% |
| random_search | 5.633074 | 114.21% | 0.00% |
| exhaustive_oracle | 2.633773 | 0.00% | 100.00% |
| one_flag_oracle | 2.633773 | 0.00% | 100.00% |
| policy_greedy (seed mean) | 5.988300 | 142.13% | 2.78% |
| policy_beam (seed mean) | 2.940454 | 12.59% | 35.42% |

Expanded-oracle circuit type: A_only=47.9%, B_only=52.1%, A_and_B=0.0%.
Two flags are oracle-selected in 0.0% of contexts; the expanded catalog strictly improves over the best one-flag schedule in 0.0%.

### ood_pauli_sparse

| Method | Mean C2 | Mean relative regret | Oracle match |
|---|---:|---:|---:|
| reference | 5.576831 | 6440.89% | 0.00% |
| best_fixed_train | 2.980990 | 5931.32% | 0.00% |
| random_search | 1.687249 | 292.26% | 2.08% |
| exhaustive_oracle | 1.272305 | 0.00% | 100.00% |
| one_flag_oracle | 1.272451 | 0.10% | 93.75% |
| policy_greedy (seed mean) | 3.283459 | 2720.98% | 1.39% |
| policy_beam (seed mean) | 1.343990 | 97.81% | 20.83% |

Expanded-oracle circuit type: A_only=58.3%, B_only=35.4%, A_and_B=6.2%.
Two flags are oracle-selected in 6.2% of contexts; the expanded catalog strictly improves over the best one-flag schedule in 6.2%.

## Finite-p diagnostics

These use one predeclared synthetic context per phase and ideal final recovery; they are component diagnostics only.

### Phase 3A

| Method | Schedule | Kind | p | failures/shots | rate | 95% interval |
|---|---|---|---:|---:|---:|---:|
| reference | 0A12A3 | A_only | 0.005 | 3/75000 | 0.0000400 | [0.0000136, 0.0001176] |
| reference | 0A12A3 | A_only | 0.01 | 35/75000 | 0.0004667 | [0.0003356, 0.0006489] |
| reference | 0A12A3 | A_only | 0.02 | 120/75000 | 0.0016000 | [0.0013384, 0.0019127] |
| learned_greedy | A0123A | A_only | 0.005 | 3/75000 | 0.0000400 | [0.0000136, 0.0001176] |
| learned_greedy | A0123A | A_only | 0.01 | 19/75000 | 0.0002533 | [0.0001622, 0.0003957] |
| learned_greedy | A0123A | A_only | 0.02 | 69/75000 | 0.0009200 | [0.0007271, 0.0011640] |
| oracle | A0321A | A_only | 0.005 | 2/75000 | 0.0000267 | [0.0000073, 0.0000972] |
| oracle | A0321A | A_only | 0.01 | 11/75000 | 0.0001467 | [0.0000819, 0.0002626] |
| oracle | A0321A | A_only | 0.02 | 62/75000 | 0.0008267 | [0.0006450, 0.0010595] |

### Phase 3B

| Method | Schedule | Kind | p | failures/shots | rate | 95% interval |
|---|---|---|---:|---:|---:|---:|
| reference | 0A12A3 | A_only | 0.002 | 0/75000 | 0.0000000 | [0.0000000, 0.0000512] |
| reference | 0A12A3 | A_only | 0.005 | 5/75000 | 0.0000667 | [0.0000285, 0.0001561] |
| reference | 0A12A3 | A_only | 0.01 | 15/75000 | 0.0002000 | [0.0001212, 0.0003300] |
| learned_greedy | A0123A | A_only | 0.002 | 0/75000 | 0.0000000 | [0.0000000, 0.0000512] |
| learned_greedy | A0123A | A_only | 0.005 | 2/75000 | 0.0000267 | [0.0000073, 0.0000972] |
| learned_greedy | A0123A | A_only | 0.01 | 15/75000 | 0.0002000 | [0.0001212, 0.0003300] |
| oracle | 2B03B1 | B_only | 0.002 | 0/75000 | 0.0000000 | [0.0000000, 0.0000512] |
| oracle | 2B03B1 | B_only | 0.005 | 0/75000 | 0.0000000 | [0.0000000, 0.0000512] |
| oracle | 2B03B1 | B_only | 0.01 | 12/75000 | 0.0001600 | [0.0000915, 0.0002797] |
| one_flag_oracle | 2B03B1 | B_only | 0.002 | 0/75000 | 0.0000000 | [0.0000000, 0.0000512] |
| one_flag_oracle | 2B03B1 | B_only | 0.005 | 0/75000 | 0.0000000 | [0.0000000, 0.0000512] |
| one_flag_oracle | 2B03B1 | B_only | 0.01 | 12/75000 | 0.0001600 | [0.0000915, 0.0002797] |

## Interpretation constraints

- The policy synthesizes an ordered interaction schedule inside a fixed grammar; it does not invent arbitrary gates.
- Exact exhaustive oracles are retained because both pilot spaces are still small enough to enumerate.
- Phase 3B adds a second available flag ancilla and variable one-flag/two-flag schedules; this is a real expansion of the candidate family.
- Synthetic noise families are controlled stress tests, not device calibration data.
- Certification assumes an ideal final syndrome and perfect recovery after this one check.
- A positive result here motivates larger synthesis spaces; it does not establish hardware or fault-tolerant quantum-computing advantage.
