# Run summary

Scope: one flagged Z-check with a perfect final recovery oracle.
C2 is a second-order logical-failure coefficient, not a measured device error rate.

All selected circuits have the same six CNOT gates; this is not a gate-count reduction study.

## test

| Method | Mean C2 | Mean relative regret | Oracle-match fraction |
|---|---:|---:|---:|
| reference | 3.762938 | 118.62% | 0.00% |
| best_fixed_train | 2.645336 | 47.35% | 2.93% |
| exhaustive_oracle | 1.852582 | 0.00% | 100.00% |
| random_search | 2.080063 | 13.57% | 16.60% |
| greedy_search | 2.219723 | 22.33% | 4.30% |
| learned_seed0 | 2.044764 | 10.91% | 29.49% |
| learned_seed1 | 2.027704 | 10.03% | 29.10% |
| learned_seed2 | 2.025709 | 10.11% | 28.52% |

## shift

| Method | Mean C2 | Mean relative regret | Oracle-match fraction |
|---|---:|---:|---:|
| reference | 6.519556 | 326.14% | 0.20% |
| best_fixed_train | 4.087717 | 123.30% | 5.27% |
| exhaustive_oracle | 2.214160 | 0.00% | 100.00% |
| random_search | 2.574281 | 22.58% | 18.36% |
| greedy_search | 2.802539 | 37.49% | 3.71% |
| learned_seed0 | 2.655627 | 24.12% | 20.31% |
| learned_seed1 | 2.674237 | 24.68% | 23.44% |
| learned_seed2 | 2.660833 | 24.24% | 23.44% |

## Interpretation

Compare learned policies with best_fixed_train, random_search, greedy_search, and exhaustive_oracle.
Beating a fixed circuit is not the same as beating a search heuristic.
The oracle is exact only within the certified finite candidate library.
The learned policy is not supplied oracle argmin labels during training.
No novelty, full QEC-cycle fault tolerance, or hardware advantage is established by this run.

## Noisy component diagnostics

| Method | p | Failures/shots | Rate | Wilson 95% interval |
|---|---:|---:|---:|---:|
| reference | 0.005 | 29/250000 | 0.0001160 | [0.0000808, 0.0001666] |
| best_fixed_train | 0.005 | 11/250000 | 0.0000440 | [0.0000246, 0.0000788] |
| learned_first_seed | 0.005 | 5/250000 | 0.0000200 | [0.0000085, 0.0000468] |
| exhaustive_oracle | 0.005 | 1/250000 | 0.0000040 | [0.0000007, 0.0000227] |
| reference | 0.01 | 126/250000 | 0.0005040 | [0.0004234, 0.0006000] |
| best_fixed_train | 0.01 | 29/250000 | 0.0001160 | [0.0000808, 0.0001666] |
| learned_first_seed | 0.01 | 14/250000 | 0.0000560 | [0.0000334, 0.0000940] |
| exhaustive_oracle | 0.01 | 14/250000 | 0.0000560 | [0.0000334, 0.0000940] |
| reference | 0.02 | 469/250000 | 0.0018760 | [0.0017139, 0.0020534] |
| best_fixed_train | 0.02 | 98/250000 | 0.0003920 | [0.0003217, 0.0004777] |
| learned_first_seed | 0.02 | 53/250000 | 0.0002120 | [0.0001621, 0.0002773] |
| exhaustive_oracle | 0.02 | 53/250000 | 0.0002120 | [0.0001621, 0.0002773] |

These rows use only one predeclared noise context, not the entire test set.
