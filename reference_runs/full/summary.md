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
| learned_seed0 | 2.041683 | 10.69% | 30.27% |
| learned_seed1 | 2.024944 | 9.75% | 28.91% |
| learned_seed2 | 2.050581 | 11.64% | 25.78% |

## shift

| Method | Mean C2 | Mean relative regret | Oracle-match fraction |
|---|---:|---:|---:|
| reference | 6.519556 | 326.14% | 0.20% |
| best_fixed_train | 4.087717 | 123.30% | 5.27% |
| exhaustive_oracle | 2.214160 | 0.00% | 100.00% |
| random_search | 2.574281 | 22.58% | 18.36% |
| greedy_search | 2.802539 | 37.49% | 3.71% |
| learned_seed0 | 2.646416 | 22.57% | 19.92% |
| learned_seed1 | 2.681562 | 25.56% | 22.27% |
| learned_seed2 | 2.735637 | 28.57% | 20.31% |

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
| learned_first_seed | 0.005 | 3/250000 | 0.0000120 | [0.0000041, 0.0000353] |
| exhaustive_oracle | 0.005 | 3/250000 | 0.0000120 | [0.0000041, 0.0000353] |
| reference | 0.01 | 126/250000 | 0.0005040 | [0.0004234, 0.0006000] |
| best_fixed_train | 0.01 | 29/250000 | 0.0001160 | [0.0000808, 0.0001666] |
| learned_first_seed | 0.01 | 8/250000 | 0.0000320 | [0.0000162, 0.0000631] |
| exhaustive_oracle | 0.01 | 8/250000 | 0.0000320 | [0.0000162, 0.0000631] |
| reference | 0.02 | 469/250000 | 0.0018760 | [0.0017139, 0.0020534] |
| best_fixed_train | 0.02 | 98/250000 | 0.0003920 | [0.0003217, 0.0004777] |
| learned_first_seed | 0.02 | 40/250000 | 0.0001600 | [0.0001175, 0.0002179] |
| exhaustive_oracle | 0.02 | 40/250000 | 0.0001600 | [0.0001175, 0.0002179] |

These rows use only one predeclared noise context, not the entire test set.
