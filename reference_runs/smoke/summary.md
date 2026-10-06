# Run summary

Scope: one flagged Z-check with a perfect final recovery oracle.
C2 is a second-order logical-failure coefficient, not a measured device error rate.

All selected circuits have the same six CNOT gates; this is not a gate-count reduction study.

## test

| Method | Mean C2 | Mean relative regret | Oracle-match fraction |
|---|---:|---:|---:|
| reference | 3.863047 | 121.55% | 0.00% |
| best_fixed_train | 2.651162 | 51.09% | 2.08% |
| exhaustive_oracle | 1.849169 | 0.00% | 100.00% |
| random_search | 2.088299 | 14.03% | 15.62% |
| greedy_search | 2.227036 | 22.37% | 5.21% |
| learned_seed0 | 2.365187 | 32.82% | 8.33% |

## shift

| Method | Mean C2 | Mean relative regret | Oracle-match fraction |
|---|---:|---:|---:|
| reference | 6.448064 | 257.02% | 0.00% |
| best_fixed_train | 3.951562 | 111.17% | 8.33% |
| exhaustive_oracle | 2.191382 | 0.00% | 100.00% |
| random_search | 2.566697 | 20.28% | 15.62% |
| greedy_search | 2.834703 | 37.32% | 7.29% |
| learned_seed0 | 3.069790 | 55.04% | 13.54% |

## Interpretation

Compare learned policies with best_fixed_train, random_search, greedy_search, and exhaustive_oracle.
Beating a fixed circuit is not the same as beating a search heuristic.
The oracle is exact only within the certified finite candidate library.
The learned policy is not supplied oracle argmin labels during training.
No novelty, full QEC-cycle fault tolerance, or hardware advantage is established by this run.

## Noisy component diagnostics

| Method | p | Failures/shots | Rate | Wilson 95% interval |
|---|---:|---:|---:|---:|
| reference | 0.01 | 23/50000 | 0.0004600 | [0.0003066, 0.0006902] |
| best_fixed_train | 0.01 | 8/50000 | 0.0001600 | [0.0000811, 0.0003157] |
| learned_first_seed | 0.01 | 11/50000 | 0.0002200 | [0.0001229, 0.0003939] |
| exhaustive_oracle | 0.01 | 3/50000 | 0.0000600 | [0.0000204, 0.0001764] |
| reference | 0.02 | 92/50000 | 0.0018400 | [0.0015007, 0.0022558] |
| best_fixed_train | 0.02 | 28/50000 | 0.0005600 | [0.0003875, 0.0008092] |
| learned_first_seed | 0.02 | 34/50000 | 0.0006800 | [0.0004867, 0.0009500] |
| exhaustive_oracle | 0.02 | 16/50000 | 0.0003200 | [0.0001970, 0.0005198] |

These rows use only one predeclared noise context, not the entire test set.
