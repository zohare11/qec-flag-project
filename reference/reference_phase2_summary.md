# Phase 2 summary

Question: which learning paradigm works best for noise-conditioned selection, and does domain-randomized training improve robustness?

C2 is a second-order logical-failure coefficient for the same one-check model with perfect final recovery. Lower is better.

Supervised classifier and cost-regressor training use full offline 96-action oracle costs. REINFORCE does not receive oracle argmin labels.

## Training regime: narrow

### Test family: narrow

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 3.770681 | 118.31% |
| best_fixed_train | 2.679378 | 48.94% |
| random_search | 2.099245 | 13.59% |
| greedy_search | 2.237538 | 22.75% |
| exhaustive_oracle | 1.869927 | 0.00% |
| reinforce (seed mean) | 2.100698 | 13.76% |
| classifier (seed mean) | 2.006926 | 7.76% |
| cost_regressor (seed mean) | 1.959637 | 4.81% |

### Test family: broad_shift

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 6.108054 | 258.44% |
| best_fixed_train | 3.998641 | 121.86% |
| random_search | 2.532242 | 21.39% |
| greedy_search | 2.701071 | 33.56% |
| exhaustive_oracle | 2.153229 | 0.00% |
| reinforce (seed mean) | 2.695325 | 29.90% |
| classifier (seed mean) | 2.494816 | 19.41% |
| cost_regressor (seed mean) | 2.455302 | 14.88% |

### Test family: ood_edge_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 14.928559 | 92.61% |
| best_fixed_train | 12.705390 | 62.24% |
| random_search | 8.857850 | 9.88% |
| greedy_search | 8.928398 | 11.02% |
| exhaustive_oracle | 8.125927 | 0.00% |
| reinforce (seed mean) | 9.502888 | 18.18% |
| classifier (seed mean) | 9.121723 | 12.98% |
| cost_regressor (seed mean) | 9.061810 | 12.04% |

### Test family: ood_flag_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 114.848028 | 4863.07% |
| best_fixed_train | 6.757809 | 182.16% |
| random_search | 3.997834 | 58.92% |
| greedy_search | 5.421867 | 121.88% |
| exhaustive_oracle | 2.643187 | 0.00% |
| reinforce (seed mean) | 4.316824 | 72.15% |
| classifier (seed mean) | 3.601173 | 40.37% |
| cost_regressor (seed mean) | 3.426045 | 33.36% |

### Test family: ood_readout_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 7.645285 | 215.42% |
| best_fixed_train | 6.670878 | 171.75% |
| random_search | 3.122004 | 19.55% |
| greedy_search | 3.334546 | 29.02% |
| exhaustive_oracle | 2.671531 | 0.00% |
| reinforce (seed mean) | 3.694014 | 43.17% |
| classifier (seed mean) | 3.362680 | 29.09% |
| cost_regressor (seed mean) | 3.019407 | 13.34% |

### Test family: ood_pauli_sparse

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 4.959585 | 3674.26% |
| best_fixed_train | 3.068350 | 1710.53% |
| random_search | 1.107958 | 359.90% |
| greedy_search | 1.281389 | 135.88% |
| exhaustive_oracle | 0.928967 | 0.00% |
| reinforce (seed mean) | 1.712035 | 451.53% |
| classifier (seed mean) | 1.521614 | 196.18% |
| cost_regressor (seed mean) | 1.572846 | 190.14% |

## Training regime: domain_randomized

### Test family: narrow

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 3.770681 | 118.31% |
| best_fixed_train | 2.675901 | 49.41% |
| random_search | 2.099245 | 13.59% |
| greedy_search | 2.237538 | 22.75% |
| exhaustive_oracle | 1.869927 | 0.00% |
| reinforce (seed mean) | 2.127665 | 15.35% |
| classifier (seed mean) | 2.000076 | 7.19% |
| cost_regressor (seed mean) | 1.989791 | 6.08% |

### Test family: broad_shift

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 6.108054 | 258.44% |
| best_fixed_train | 3.901061 | 110.87% |
| random_search | 2.532242 | 21.39% |
| greedy_search | 2.701071 | 33.56% |
| exhaustive_oracle | 2.153229 | 0.00% |
| reinforce (seed mean) | 2.747376 | 34.47% |
| classifier (seed mean) | 2.519245 | 20.90% |
| cost_regressor (seed mean) | 2.505707 | 17.34% |

### Test family: ood_edge_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 14.928559 | 92.61% |
| best_fixed_train | 12.336450 | 59.54% |
| random_search | 8.857850 | 9.88% |
| greedy_search | 8.928398 | 11.02% |
| exhaustive_oracle | 8.125927 | 0.00% |
| reinforce (seed mean) | 9.508345 | 18.62% |
| classifier (seed mean) | 9.160893 | 13.39% |
| cost_regressor (seed mean) | 9.249791 | 14.65% |

### Test family: ood_flag_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 114.848028 | 4863.07% |
| best_fixed_train | 6.609222 | 171.65% |
| random_search | 3.997834 | 58.92% |
| greedy_search | 5.421867 | 121.88% |
| exhaustive_oracle | 2.643187 | 0.00% |
| reinforce (seed mean) | 4.612632 | 81.92% |
| classifier (seed mean) | 3.640928 | 41.51% |
| cost_regressor (seed mean) | 3.358479 | 29.94% |

### Test family: ood_readout_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 7.645285 | 215.42% |
| best_fixed_train | 6.692456 | 174.60% |
| random_search | 3.122004 | 19.55% |
| greedy_search | 3.334546 | 29.02% |
| exhaustive_oracle | 2.671531 | 0.00% |
| reinforce (seed mean) | 4.079238 | 59.15% |
| classifier (seed mean) | 3.346019 | 27.67% |
| cost_regressor (seed mean) | 2.999063 | 12.87% |

### Test family: ood_pauli_sparse

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 4.959585 | 3674.26% |
| best_fixed_train | 3.107730 | 1255.62% |
| random_search | 1.107958 | 359.90% |
| greedy_search | 1.281389 | 135.88% |
| exhaustive_oracle | 0.928967 | 0.00% |
| reinforce (seed mean) | 1.683451 | 373.76% |
| classifier (seed mean) | 1.498258 | 171.81% |
| cost_regressor (seed mean) | 1.573883 | 206.43% |

## Robustness macro-summary

| Learning method | Narrow-trained ID regret | Narrow-trained OOD regret | Domain-randomized ID regret | Domain-randomized OOD regret | OOD regret reduction from domain randomization |
|---|---:|---:|---:|---:|---:|
| reinforce | 13.76% | 122.99% | 15.35% | 113.58% | 9.40 pp |
| classifier | 7.76% | 59.61% | 7.19% | 55.06% | 4.55 pp |
| cost_regressor | 4.81% | 52.75% | 6.08% | 56.24% | -3.49 pp |

## Interpretation rules

- Supervised models have a stronger training-information advantage: their labels require offline evaluation of all 96 schedules.
- REINFORCE uses sampled-action feedback plus a fixed-reference control variate, so its training-information budget is different.
- Random and greedy search evaluate candidate schedules online; a learned model performs one policy inference plus the selected-circuit diagnostic.
- Exhaustive search is still cheap for this 96-circuit pilot and remains the exact oracle only within this finite library.
- OOD families are synthetic stress tests, not measured hardware distributions.
- This phase tests method choice and generalization; it does not establish unrestricted circuit synthesis, hardware advantage, or full QEC-cycle fault tolerance.

See `learning_curves_narrow.svg`, `learning_curves_domain_randomized.svg`, and `robustness.svg` for plots.
