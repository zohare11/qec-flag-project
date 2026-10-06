# Phase 4 summary

Scope: one noisy full six-check Steane syndrome-extraction round with an explicit flag-aware lookup decoder and ideal initial/final boundaries.

The learned model is a proposal policy. Policy-beam and random/coordinate search use the same exact full-round C2 evaluation budget.

- Local action table: 48 certified templates ({'A_and_B': 16, 'A_only': 16, 'B_only': 16})
- Full schedule space represented by the action table: 48^6 = 12,230,590,464
- Exact search budget per context: 4 complete schedules
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
| reference | 952.822974 | 884.488274 | 0.00% | 1 |
| proxy_fixed | 769.714133 | 874.154230 | -6.57% | 1 |
| local_greedy | 479.298331 | 313.338201 | 40.79% | 1 |
| random_search | 565.529818 | 420.228038 | 28.91% | 4 |
| coordinate_search | 455.399743 | 302.276349 | 45.28% | 4 |
| policy_greedy_seed_mean | 407.417071 | 318.818582 | 50.94% | 1 |
| policy_beam_seed_mean | 405.761755 | 314.160563 | 51.07% | 4 |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -28.25%.
- Policy-beam vs coordinate search: win fraction 33.3%; mean C2 change -10.90%.
- Policy-beam local-template mix: A-only 66.7%, B-only 33.3%, A+B 0.0%.
- Local-greedy template mix: A-only 50.0%, B-only 50.0%, A+B 0.0%.

## ood_flagA_bad

| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |
|---|---:|---:|---:|---:|
| reference | 9903.197386 | 11262.997931 | 0.00% | 1 |
| proxy_fixed | 1060.464841 | 883.380225 | 88.94% | 1 |
| local_greedy | 214.119178 | 217.459087 | 97.58% | 1 |
| random_search | 909.251817 | 969.315214 | 91.28% | 4 |
| coordinate_search | 202.005872 | 210.489082 | 97.75% | 4 |
| policy_greedy_seed_mean | 213.016368 | 200.631835 | 97.71% | 1 |
| policy_beam_seed_mean | 206.483601 | 192.253363 | 97.79% | 4 |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -77.29%.
- Policy-beam vs coordinate search: win fraction 33.3%; mean C2 change 2.22%.
- Policy-beam local-template mix: A-only 0.0%, B-only 100.0%, A+B 0.0%.
- Local-greedy template mix: A-only 0.0%, B-only 100.0%, A+B 0.0%.

## ood_flagB_bad

| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |
|---|---:|---:|---:|---:|
| reference | 227.791440 | 264.691422 | 0.00% | 1 |
| proxy_fixed | 715.758194 | 744.135678 | -257.68% | 1 |
| local_greedy | 209.655785 | 256.711104 | 4.88% | 1 |
| random_search | 810.617571 | 718.573189 | -273.89% | 4 |
| coordinate_search | 200.047674 | 244.480917 | 8.96% | 4 |
| policy_greedy_seed_mean | 190.653360 | 237.587853 | 15.19% | 1 |
| policy_beam_seed_mean | 189.772798 | 237.587853 | 15.53% | 4 |

- Policy-beam vs random: win fraction 100.0%; mean C2 change -76.59%.
- Policy-beam vs coordinate search: win fraction 100.0%; mean C2 change -5.14%.
- Policy-beam local-template mix: A-only 100.0%, B-only 0.0%, A+B 0.0%.
- Local-greedy template mix: A-only 100.0%, B-only 0.0%, A+B 0.0%.

## ood_both_flags_clean

| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |
|---|---:|---:|---:|---:|
| reference | 95.149280 | 97.578182 | 0.00% | 1 |
| proxy_fixed | 104.914652 | 104.506457 | -10.31% | 1 |
| local_greedy | 108.706522 | 102.908408 | -14.23% | 1 |
| random_search | 99.713222 | 104.278694 | -4.62% | 4 |
| coordinate_search | 107.644972 | 102.908408 | -13.16% | 4 |
| policy_greedy_seed_mean | 105.994372 | 95.241982 | -11.55% | 1 |
| policy_beam_seed_mean | 105.604511 | 94.072401 | -11.15% | 4 |

- Policy-beam vs random: win fraction 33.3%; mean C2 change 5.91%.
- Policy-beam vs coordinate search: win fraction 33.3%; mean C2 change -1.90%.
- Policy-beam local-template mix: A-only 0.0%, B-only 0.0%, A+B 100.0%.
- Local-greedy template mix: A-only 44.4%, B-only 55.6%, A+B 0.0%.

## Finite-p logical-memory diagnostics

These rows use one predeclared `round_id` synthetic calibration. They are one-round memory experiments with an explicit decoder and ideal boundaries.

| Method | p | failures/shots | logical failure rate | Wilson 95% interval |
|---|---:|---:|---:|---:|
| reference | 0.0005 | 2/5000 | 0.0004000 | [0.0001097, 0.0014574] |
| reference | 0.001 | 5/5000 | 0.0010000 | [0.0004272, 0.0023390] |
| local_greedy | 0.0005 | 1/5000 | 0.0002000 | [0.0000353, 0.0011321] |
| local_greedy | 0.001 | 6/5000 | 0.0012000 | [0.0005501, 0.0026158] |
| random_search | 0.0005 | 0/5000 | 0.0000000 | [0.0000000, 0.0007677] |
| random_search | 0.001 | 4/5000 | 0.0008000 | [0.0003111, 0.0020553] |
| coordinate_search | 0.0005 | 1/5000 | 0.0002000 | [0.0000353, 0.0011321] |
| coordinate_search | 0.001 | 4/5000 | 0.0008000 | [0.0003111, 0.0020553] |
| policy_beam | 0.0005 | 2/5000 | 0.0004000 | [0.0001097, 0.0014574] |
| policy_beam | 0.001 | 4/5000 | 0.0008000 | [0.0003111, 0.0020553] |

## Interpretation constraints

- Ideal boundaries are used, analogous to a one-round memory experiment; this is not repeated fault-tolerant QEC.
- The decoder is schedule-specific and built from all single-fault signatures; it is not PyMatching or a scalable general decoder.
- Checks are serialized in X0,X1,X2,Z0,Z1,Z2 order; idle noise and hardware timing/connectivity are not modeled.
- Calibration families are synthetic stress tests, not measured device data.
- The 48-template local action table is an offline-pruned subset of the 4,896 Phase-3-certified templates.
- C2 is a second-order logical-failure coefficient; finite-p diagnostics are separate Monte Carlo estimates.
- FastSched (Ye, Pabla, Palsberg, 2026) already establishes RL for syndrome-extraction scheduling; Phase 4 instead tests calibration-conditioned flag-template proposals under a bounded exact-evaluation budget.

