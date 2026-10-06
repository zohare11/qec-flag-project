# Phase 4 summary

Scope: one noisy full six-check Steane syndrome-extraction round with an explicit flag-aware lookup decoder and ideal initial/final boundaries.

The learned model is a proposal policy. Policy-beam and random/coordinate search use the same exact full-round C2 evaluation budget.

- Local action table: 48 certified templates ({'A_and_B': 16, 'A_only': 16, 'B_only': 16})
- Full schedule space represented by the action table: 48^6 = 12,230,590,464
- Exact search budget per context: 8 complete schedules
- No exhaustive oracle is reported for the full Phase-4 space.

## Verification

- Reference round single-fault conflicts: 0
- Reference round single-fault logical failures: 0
- Reference round single incoming-error failures: 0
- Reference round elementary fault outcomes: 564
- Reference round malignant two-fault patterns: 50222

## round_id

| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |
|---|---:|---:|---:|---:|
| reference | 1289.648268 | 1178.171352 | 0.00% | 1 |
| proxy_fixed | 1108.271267 | 867.855888 | 3.26% | 1 |
| local_greedy | 561.751401 | 414.676863 | 56.04% | 1 |
| random_search | 762.257725 | 632.343119 | 38.45% | 8 |
| coordinate_search | 543.059331 | 383.728277 | 57.86% | 8 |
| policy_greedy_seed_mean | 590.291395 | 422.768753 | 53.21% | 1 |
| policy_beam_seed_mean | 560.772021 | 375.784440 | 56.30% | 8 |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -26.43%.
- Policy-beam vs coordinate search: win fraction 25.0%; mean C2 change 3.26%.
- Policy-beam local-template mix: A-only 48.6%, B-only 51.4%, A+B 0.0%.
- Local-greedy template mix: A-only 40.3%, B-only 59.7%, A+B 0.0%.

## ood_flagA_bad

| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |
|---|---:|---:|---:|---:|
| reference | 16291.504179 | 14169.980282 | 0.00% | 1 |
| proxy_fixed | 989.283226 | 878.431292 | 93.36% | 1 |
| local_greedy | 209.939631 | 205.148950 | 98.30% | 1 |
| random_search | 923.034910 | 754.997555 | 93.87% | 8 |
| coordinate_search | 197.008631 | 199.377325 | 98.40% | 8 |
| policy_greedy_seed_mean | 212.611501 | 213.811839 | 98.27% | 1 |
| policy_beam_seed_mean | 199.554059 | 202.819370 | 98.39% | 8 |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -78.38%.
- Policy-beam vs coordinate search: win fraction 41.7%; mean C2 change 1.29%.
- Policy-beam local-template mix: A-only 0.0%, B-only 100.0%, A+B 0.0%.
- Local-greedy template mix: A-only 0.0%, B-only 100.0%, A+B 0.0%.

## ood_flagB_bad

| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |
|---|---:|---:|---:|---:|
| reference | 238.877577 | 232.288382 | 0.00% | 1 |
| proxy_fixed | 1539.047905 | 1275.895160 | -543.96% | 1 |
| local_greedy | 237.344482 | 222.667798 | 1.79% | 1 |
| random_search | 911.682315 | 650.086130 | -294.97% | 8 |
| coordinate_search | 223.460665 | 214.098454 | 7.37% | 8 |
| policy_greedy_seed_mean | 223.859096 | 199.351283 | 6.96% | 1 |
| policy_beam_seed_mean | 214.935901 | 190.948406 | 10.66% | 8 |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -76.42%.
- Policy-beam vs coordinate search: win fraction 75.0%; mean C2 change -3.81%.
- Policy-beam local-template mix: A-only 100.0%, B-only 0.0%, A+B 0.0%.
- Local-greedy template mix: A-only 100.0%, B-only 0.0%, A+B 0.0%.

## ood_both_flags_clean

| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |
|---|---:|---:|---:|---:|
| reference | 164.418714 | 171.975366 | 0.00% | 1 |
| proxy_fixed | 199.473849 | 206.603908 | -21.41% | 1 |
| local_greedy | 175.019558 | 173.325271 | -6.60% | 1 |
| random_search | 165.722150 | 173.902865 | -1.35% | 8 |
| coordinate_search | 169.063901 | 166.638144 | -2.71% | 8 |
| policy_greedy_seed_mean | 182.953282 | 190.936630 | -11.98% | 1 |
| policy_beam_seed_mean | 171.795013 | 177.262504 | -5.14% | 8 |

- Policy-beam vs random: win fraction 25.0%; mean C2 change 3.66%.
- Policy-beam vs coordinate search: win fraction 41.7%; mean C2 change 1.62%.
- Policy-beam local-template mix: A-only 52.3%, B-only 47.7%, A+B 0.0%.
- Local-greedy template mix: A-only 44.4%, B-only 55.6%, A+B 0.0%.

## ood_check_hotspot

| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |
|---|---:|---:|---:|---:|
| reference | 23109.809369 | 4624.323591 | 0.00% | 1 |
| proxy_fixed | 4098.400873 | 2985.172867 | 26.04% | 1 |
| local_greedy | 2675.382833 | 2407.661561 | 55.27% | 1 |
| random_search | 3181.147249 | 2693.936265 | 48.73% | 8 |
| coordinate_search | 2599.843234 | 2342.587464 | 56.70% | 8 |
| policy_greedy_seed_mean | 2805.497039 | 2321.626761 | 52.68% | 1 |
| policy_beam_seed_mean | 2575.240327 | 2063.051239 | 58.42% | 8 |

- Policy-beam vs random: win fraction 75.0%; mean C2 change -19.05%.
- Policy-beam vs coordinate search: win fraction 66.7%; mean C2 change -0.95%.
- Policy-beam local-template mix: A-only 54.2%, B-only 45.8%, A+B 0.0%.
- Local-greedy template mix: A-only 52.8%, B-only 47.2%, A+B 0.0%.

## ood_data_hotspot

| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |
|---|---:|---:|---:|---:|
| reference | 5835.728093 | 5152.047465 | 0.00% | 1 |
| proxy_fixed | 6089.403094 | 5832.950240 | -9.11% | 1 |
| local_greedy | 4763.664220 | 3758.871790 | 18.46% | 1 |
| random_search | 5003.798492 | 3798.369392 | 10.99% | 8 |
| coordinate_search | 4559.544208 | 3611.106510 | 21.03% | 8 |
| policy_greedy_seed_mean | 4707.811385 | 3745.926072 | 18.35% | 1 |
| policy_beam_seed_mean | 4480.779949 | 3471.864368 | 22.78% | 8 |

- Policy-beam vs random: win fraction 83.3%; mean C2 change -10.45%.
- Policy-beam vs coordinate search: win fraction 50.0%; mean C2 change -1.73%.
- Policy-beam local-template mix: A-only 61.6%, B-only 38.4%, A+B 0.0%.
- Local-greedy template mix: A-only 45.8%, B-only 54.2%, A+B 0.0%.

## ood_readout_hotspot

| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |
|---|---:|---:|---:|---:|
| reference | 826.100594 | 827.362281 | 0.00% | 1 |
| proxy_fixed | 1032.436499 | 1030.075076 | -24.61% | 1 |
| local_greedy | 735.237755 | 704.991344 | 11.78% | 1 |
| random_search | 839.376341 | 657.942192 | -0.24% | 8 |
| coordinate_search | 657.652211 | 654.178026 | 20.62% | 8 |
| policy_greedy_seed_mean | 728.024784 | 692.810615 | 13.37% | 1 |
| policy_beam_seed_mean | 645.356481 | 627.591864 | 23.15% | 8 |

- Policy-beam vs random: win fraction 91.7%; mean C2 change -23.11%.
- Policy-beam vs coordinate search: win fraction 41.7%; mean C2 change -1.87%.
- Policy-beam local-template mix: A-only 59.7%, B-only 40.3%, A+B 0.0%.
- Local-greedy template mix: A-only 55.6%, B-only 44.4%, A+B 0.0%.

## ood_pauli_sparse

| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |
|---|---:|---:|---:|---:|
| reference | 417.363817 | 392.592956 | 0.00% | 1 |
| proxy_fixed | 282.315137 | 308.038301 | 26.83% | 1 |
| local_greedy | 238.566203 | 208.481411 | 42.45% | 1 |
| random_search | 219.091606 | 201.602175 | 45.47% | 8 |
| coordinate_search | 226.571930 | 202.413210 | 45.29% | 8 |
| policy_greedy_seed_mean | 247.437788 | 231.325718 | 39.95% | 1 |
| policy_beam_seed_mean | 218.325407 | 204.774410 | 47.01% | 8 |

- Policy-beam vs random: win fraction 50.0%; mean C2 change -0.35%.
- Policy-beam vs coordinate search: win fraction 50.0%; mean C2 change -3.64%.
- Policy-beam local-template mix: A-only 41.2%, B-only 58.8%, A+B 0.0%.
- Local-greedy template mix: A-only 51.4%, B-only 48.6%, A+B 0.0%.

## Finite-p logical-memory diagnostics

These rows use one predeclared `round_id` synthetic calibration. They are one-round memory experiments with an explicit decoder and ideal boundaries.

| Method | p | failures/shots | logical failure rate | Wilson 95% interval |
|---|---:|---:|---:|---:|
| reference | 0.0005 | 7/50000 | 0.0001400 | [0.0000678, 0.0002890] |
| reference | 0.001 | 21/50000 | 0.0004200 | [0.0002747, 0.0006420] |
| reference | 0.002 | 116/50000 | 0.0023200 | [0.0019348, 0.0027816] |
| local_greedy | 0.0005 | 4/50000 | 0.0000800 | [0.0000311, 0.0002057] |
| local_greedy | 0.001 | 19/50000 | 0.0003800 | [0.0002433, 0.0005935] |
| local_greedy | 0.002 | 56/50000 | 0.0011200 | [0.0008627, 0.0014540] |
| random_search | 0.0005 | 9/50000 | 0.0001800 | [0.0000947, 0.0003421] |
| random_search | 0.001 | 39/50000 | 0.0007800 | [0.0005707, 0.0010660] |
| random_search | 0.002 | 128/50000 | 0.0025600 | [0.0021537, 0.0030428] |
| coordinate_search | 0.0005 | 2/50000 | 0.0000400 | [0.0000110, 0.0001458] |
| coordinate_search | 0.001 | 14/50000 | 0.0002800 | [0.0001668, 0.0004700] |
| coordinate_search | 0.002 | 75/50000 | 0.0015000 | [0.0011969, 0.0018797] |
| policy_beam | 0.0005 | 5/50000 | 0.0001000 | [0.0000427, 0.0002341] |
| policy_beam | 0.001 | 20/50000 | 0.0004000 | [0.0002590, 0.0006178] |
| policy_beam | 0.002 | 83/50000 | 0.0016600 | [0.0013394, 0.0020571] |

## Interpretation constraints

- Ideal boundaries are used, analogous to a one-round memory experiment; this is not repeated fault-tolerant QEC.
- The decoder is schedule-specific and built from all single-fault signatures; it is not PyMatching or a scalable general decoder.
- Checks are serialized in X0,X1,X2,Z0,Z1,Z2 order; idle noise and hardware timing/connectivity are not modeled.
- Calibration families are synthetic stress tests, not measured device data.
- The 48-template local action table is an offline-pruned subset of the 4,896 Phase-3-certified templates.
- C2 is a second-order logical-failure coefficient; finite-p diagnostics are separate Monte Carlo estimates.
- FastSched (Ye, Pabla, Palsberg, 2026) already establishes RL for syndrome-extraction scheduling; Phase 4 instead tests calibration-conditioned flag-template proposals under a bounded exact-evaluation budget.

