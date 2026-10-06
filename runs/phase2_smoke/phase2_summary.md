# Phase 2 summary

Question: which learning paradigm works best for noise-conditioned selection, and does domain-randomized training improve robustness?

C2 is a second-order logical-failure coefficient for the same one-check model with perfect final recovery. Lower is better.

Supervised classifier and cost-regressor training use full offline 96-action oracle costs. REINFORCE does not receive oracle argmin labels.

## Training regime: narrow

### Test family: narrow

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 3.486215 | 118.97% |
| best_fixed_train | 2.679377 | 57.04% |
| random_search | 1.992424 | 13.74% |
| greedy_search | 2.075907 | 20.80% |
| exhaustive_oracle | 1.774800 | 0.00% |
| reinforce (seed mean) | 2.190996 | 27.30% |
| classifier (seed mean) | 2.044596 | 17.75% |
| cost_regressor (seed mean) | 1.879826 | 6.94% |

### Test family: broad_shift

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 6.676981 | 294.71% |
| best_fixed_train | 3.912587 | 105.15% |
| random_search | 2.705862 | 23.87% |
| greedy_search | 2.893879 | 40.62% |
| exhaustive_oracle | 2.251329 | 0.00% |
| reinforce (seed mean) | 3.241196 | 63.66% |
| classifier (seed mean) | 3.046140 | 40.37% |
| cost_regressor (seed mean) | 2.729192 | 26.35% |

### Test family: ood_edge_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 15.443171 | 101.88% |
| best_fixed_train | 12.506286 | 63.87% |
| random_search | 8.950264 | 8.94% |
| greedy_search | 9.122201 | 10.94% |
| exhaustive_oracle | 8.274660 | 0.00% |
| reinforce (seed mean) | 9.974369 | 23.49% |
| classifier (seed mean) | 9.881225 | 21.24% |
| cost_regressor (seed mean) | 9.522216 | 17.25% |

### Test family: ood_flag_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 100.708265 | 4160.52% |
| best_fixed_train | 6.650592 | 164.31% |
| random_search | 4.094373 | 51.05% |
| greedy_search | 5.617494 | 116.28% |
| exhaustive_oracle | 2.734071 | 0.00% |
| reinforce (seed mean) | 5.771795 | 126.44% |
| classifier (seed mean) | 5.137294 | 92.29% |
| cost_regressor (seed mean) | 4.124623 | 56.51% |

### Test family: ood_readout_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 7.744177 | 221.46% |
| best_fixed_train | 5.800674 | 136.32% |
| random_search | 3.090852 | 22.19% |
| greedy_search | 3.326442 | 32.84% |
| exhaustive_oracle | 2.590119 | 0.00% |
| reinforce (seed mean) | 5.078353 | 108.03% |
| classifier (seed mean) | 4.456474 | 80.41% |
| cost_regressor (seed mean) | 3.463460 | 35.72% |

### Test family: ood_pauli_sparse

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 5.426730 | 4294.18% |
| best_fixed_train | 3.567188 | 6270.03% |
| random_search | 1.411934 | 77.13% |
| greedy_search | 1.490250 | 114.46% |
| exhaustive_oracle | 1.162302 | 0.00% |
| reinforce (seed mean) | 2.548477 | 576.25% |
| classifier (seed mean) | 2.240641 | 839.12% |
| cost_regressor (seed mean) | 2.047265 | 192.88% |

## Training regime: domain_randomized

### Test family: narrow

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 3.486215 | 118.97% |
| best_fixed_train | 2.670856 | 57.48% |
| random_search | 1.992424 | 13.74% |
| greedy_search | 2.075907 | 20.80% |
| exhaustive_oracle | 1.774800 | 0.00% |
| reinforce (seed mean) | 2.370382 | 40.29% |
| classifier (seed mean) | 2.078996 | 19.35% |
| cost_regressor (seed mean) | 1.978464 | 11.89% |

### Test family: broad_shift

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 6.676981 | 294.71% |
| best_fixed_train | 4.197899 | 128.22% |
| random_search | 2.705862 | 23.87% |
| greedy_search | 2.893879 | 40.62% |
| exhaustive_oracle | 2.251329 | 0.00% |
| reinforce (seed mean) | 3.534989 | 79.97% |
| classifier (seed mean) | 3.067363 | 48.48% |
| cost_regressor (seed mean) | 2.793102 | 24.57% |

### Test family: ood_edge_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 15.443171 | 101.88% |
| best_fixed_train | 13.406546 | 74.04% |
| random_search | 8.950264 | 8.94% |
| greedy_search | 9.122201 | 10.94% |
| exhaustive_oracle | 8.274660 | 0.00% |
| reinforce (seed mean) | 10.107401 | 26.69% |
| classifier (seed mean) | 9.739447 | 21.73% |
| cost_regressor (seed mean) | 9.675060 | 18.66% |

### Test family: ood_flag_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 100.708265 | 4160.52% |
| best_fixed_train | 6.683681 | 167.49% |
| random_search | 4.094373 | 51.05% |
| greedy_search | 5.617494 | 116.28% |
| exhaustive_oracle | 2.734071 | 0.00% |
| reinforce (seed mean) | 6.015774 | 127.44% |
| classifier (seed mean) | 4.863202 | 88.13% |
| cost_regressor (seed mean) | 3.957334 | 53.73% |

### Test family: ood_readout_hotspot

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 7.744177 | 221.46% |
| best_fixed_train | 6.719459 | 175.03% |
| random_search | 3.090852 | 22.19% |
| greedy_search | 3.326442 | 32.84% |
| exhaustive_oracle | 2.590119 | 0.00% |
| reinforce (seed mean) | 5.721301 | 140.97% |
| classifier (seed mean) | 4.004947 | 61.61% |
| cost_regressor (seed mean) | 3.262113 | 27.26% |

### Test family: ood_pauli_sparse

| Method | Mean C2 | Mean relative regret |
|---|---:|---:|
| reference | 5.426730 | 4294.18% |
| best_fixed_train | 3.120574 | 1186.90% |
| random_search | 1.411934 | 77.13% |
| greedy_search | 1.490250 | 114.46% |
| exhaustive_oracle | 1.162302 | 0.00% |
| reinforce (seed mean) | 3.190592 | 2468.71% |
| classifier (seed mean) | 2.056087 | 4634.24% |
| cost_regressor (seed mean) | 2.276683 | 247.99% |

## Robustness macro-summary

| Learning method | Narrow-trained ID regret | Narrow-trained OOD regret | Domain-randomized ID regret | Domain-randomized OOD regret | OOD regret reduction from domain randomization |
|---|---:|---:|---:|---:|---:|
| reinforce | 27.30% | 179.57% | 40.29% | 568.76% | -389.18 pp |
| classifier | 17.75% | 214.69% | 19.35% | 970.84% | -756.15 pp |
| cost_regressor | 6.94% | 65.74% | 11.89% | 74.44% | -8.70 pp |

## Interpretation rules

- Supervised models have a stronger training-information advantage: their labels require offline evaluation of all 96 schedules.
- REINFORCE uses sampled-action feedback plus a fixed-reference control variate, so its training-information budget is different.
- Random and greedy search evaluate candidate schedules online; a learned model performs one policy inference plus the selected-circuit diagnostic.
- Exhaustive search is still cheap for this 96-circuit pilot and remains the exact oracle only within this finite library.
- OOD families are synthetic stress tests, not measured hardware distributions.
- This phase tests method choice and generalization; it does not establish unrestricted circuit synthesis, hardware advantage, or full QEC-cycle fault tolerance.

See `learning_curves_narrow.svg`, `learning_curves_domain_randomized.svg`, and `robustness.svg` for plots.
