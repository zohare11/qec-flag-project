# Phase 6 summary

Scope: explicit native-routed-CNOT fault validation of schedules selected by the Phase-5 hardware-aware search pipeline.

Every routed SWAP is expanded into native CNOTs and every native CNOT receives its own 15-outcome Pauli fault location. Data idle faults are explicit at route boundaries. Lower native small-p score is better.

- Validation reference p: 0.0002; native score = p*C1 + p^2*C2.
- Phase-5 bounded-search budget used to select candidates before native validation: 8.
- Phase 6 does not retrain the policy; it validates schedules proposed by saved Phase-5 models.

## hw_id

| Method | Surrogate C2 | Native C1 | Native C2 | Native small-p score | Single-fault FT pass | Native CX | Duration (us) |
|---|---:|---:|---:|---:|---:|---:|---:|
| reference | 18415.171000 | 7.634017 | 23184.587509 | 0.00245419 | 0.0% | 180.0 | 45.743 |
| local_greedy | 6886.854337 | 4.839560 | 8235.804086 | 0.00129734 | 0.0% | 186.0 | 46.421 |
| random_search | 11871.429846 | 4.734000 | 9657.478869 | 0.00133310 | 0.0% | 224.0 | 54.940 |
| coordinate_search | 6814.492471 | 4.839560 | 8223.882552 | 0.00129687 | 0.0% | 186.0 | 46.421 |
| policy_beam_seed0 | 8012.309162 | 6.640521 | 9312.342987 | 0.00170060 | 0.0% | 180.0 | 44.734 |
| policy_beam_seed1 | 7530.989297 | 5.237574 | 9325.760367 | 0.00142055 | 0.0% | 180.0 | 44.862 |
| policy_beam_seed2 | 6674.084273 | 4.489404 | 8439.363364 | 0.00123546 | 0.0% | 180.0 | 44.998 |

- Mean within-context Spearman rank correlation, surrogate C2 vs explicit native score: 0.713.
- Surrogate and native models select the same best listed method in 100.0% of contexts.
- Policy-seed mean vs coordinate: win fraction 0.0%; mean native-score change 11.98%.
- Policy-seed mean vs local greedy: win fraction 0.0%.
- Policy-seed mean vs random search: win fraction 50.0%.

## ood_hub0_bad

| Method | Surrogate C2 | Native C1 | Native C2 | Native small-p score | Single-fault FT pass | Native CX | Duration (us) |
|---|---:|---:|---:|---:|---:|---:|---:|
| reference | 732643.753410 | 58.622002 | 324603.439525 | 0.02470854 | 0.0% | 216.0 | 71.344 |
| local_greedy | 16278.508015 | 18.874240 | 24736.181487 | 0.00476430 | 0.0% | 228.0 | 55.348 |
| random_search | 48991.875283 | 17.384703 | 40483.631389 | 0.00509629 | 0.0% | 266.0 | 68.576 |
| coordinate_search | 15233.203900 | 18.874240 | 24493.524454 | 0.00475459 | 0.0% | 228.0 | 55.348 |
| policy_beam_seed0 | 15109.424640 | 22.052089 | 29585.520906 | 0.00559384 | 0.0% | 222.0 | 55.407 |
| policy_beam_seed1 | 28905.105231 | 11.047184 | 32857.131832 | 0.00352372 | 0.0% | 198.0 | 53.437 |
| policy_beam_seed2 | 35782.532735 | 35.778301 | 41762.321209 | 0.00882615 | 0.0% | 198.0 | 52.501 |

- Mean within-context Spearman rank correlation, surrogate C2 vs explicit native score: 0.214.
- Surrogate and native models select the same best listed method in 0.0% of contexts.
- Policy-seed mean vs coordinate: win fraction 50.0%; mean native-score change 25.80%.
- Policy-seed mean vs local greedy: win fraction 50.0%.
- Policy-seed mean vs random search: win fraction 50.0%.

## ood_logical_shift

| Method | Surrogate C2 | Native C1 | Native C2 | Native small-p score | Single-fault FT pass | Native CX | Duration (us) |
|---|---:|---:|---:|---:|---:|---:|---:|
| reference | 4177.943744 | 2.667909 | 5417.758081 | 0.00075029 | 0.0% | 180.0 | 44.417 |
| local_greedy | 4361.751530 | 2.088547 | 5511.888949 | 0.00063818 | 0.0% | 186.0 | 46.108 |
| random_search | 9636.774405 | 4.922990 | 8203.222139 | 0.00131273 | 0.0% | 236.0 | 56.788 |
| coordinate_search | 3612.035444 | 2.085755 | 5239.624944 | 0.00062674 | 0.0% | 186.0 | 46.108 |
| policy_beam_seed0 | 3982.328080 | 4.651566 | 4824.242216 | 0.00112328 | 0.0% | 180.0 | 43.863 |
| policy_beam_seed1 | 3457.577018 | 4.653851 | 5072.984559 | 0.00113369 | 0.0% | 180.0 | 44.497 |
| policy_beam_seed2 | 3831.259874 | 4.014095 | 5086.211916 | 0.00100627 | 0.0% | 180.0 | 43.867 |

- Mean within-context Spearman rank correlation, surrogate C2 vs explicit native score: 0.036.
- Surrogate and native models select the same best listed method in 0.0% of contexts.
- Policy-seed mean vs coordinate: win fraction 0.0%; mean native-score change 73.56%.
- Policy-seed mean vs local greedy: win fraction 0.0%.
- Policy-seed mean vs random search: win fraction 100.0%.

## ood_mixed

| Method | Surrogate C2 | Native C1 | Native C2 | Native small-p score | Single-fault FT pass | Native CX | Duration (us) |
|---|---:|---:|---:|---:|---:|---:|---:|
| reference | 101723.297513 | 16.472717 | 49126.110418 | 0.00525959 | 0.0% | 180.0 | 46.544 |
| local_greedy | 18903.961951 | 22.663543 | 27490.414043 | 0.00563233 | 0.0% | 192.0 | 49.156 |
| random_search | 99453.214062 | 17.577842 | 60757.573823 | 0.00594587 | 0.0% | 256.0 | 69.102 |
| coordinate_search | 18739.271444 | 22.474784 | 27514.223510 | 0.00559553 | 0.0% | 192.0 | 49.156 |
| policy_beam_seed0 | 26534.105910 | 21.325265 | 31380.797996 | 0.00552028 | 0.0% | 192.0 | 50.075 |
| policy_beam_seed1 | 32414.314521 | 17.277967 | 32667.562824 | 0.00476230 | 0.0% | 192.0 | 49.434 |
| policy_beam_seed2 | 19831.052504 | 22.378122 | 27380.561579 | 0.00557085 | 0.0% | 192.0 | 49.706 |

- Mean within-context Spearman rank correlation, surrogate C2 vs explicit native score: 0.058.
- Surrogate and native models select the same best listed method in 0.0% of contexts.
- Policy-seed mean vs coordinate: win fraction 50.0%; mean native-score change -5.56%.
- Policy-seed mean vs local greedy: win fraction 50.0%.
- Policy-seed mean vs random search: win fraction 50.0%.

## Explicit finite-p native diagnostics

These use the first fresh `hw_id` validation context. Faults are sampled directly at native CNOT, preparation/readout, and route-boundary idle locations.

| Method | p | failures/shots | logical failure rate | 95% interval | C1 | C2 |
|---|---:|---:|---:|---:|---:|---:|
| reference | 0.0001 | 7/10000 | 0.0007000 | [0.0003391, 0.0014443] | 3.380733 | 19779.978381 |
| reference | 0.0002 | 14/10000 | 0.0014000 | [0.0008342, 0.0023488] | 3.380733 | 19779.978381 |
| reference | 0.0005 | 41/10000 | 0.0041000 | [0.0030239, 0.0055570] | 3.380733 | 19779.978381 |
| local_greedy | 0.0001 | 10/10000 | 0.0010000 | [0.0005433, 0.0018399] | 4.344994 | 7010.987379 |
| local_greedy | 0.0002 | 10/10000 | 0.0010000 | [0.0005433, 0.0018399] | 4.344994 | 7010.987379 |
| local_greedy | 0.0005 | 26/10000 | 0.0026000 | [0.0017750, 0.0038070] | 4.344994 | 7010.987379 |
| coordinate_search | 0.0001 | 3/10000 | 0.0003000 | [0.0001020, 0.0008817] | 4.344994 | 6987.144311 |
| coordinate_search | 0.0002 | 15/10000 | 0.0015000 | [0.0009093, 0.0024736] | 4.344994 | 6987.144311 |
| coordinate_search | 0.0005 | 31/10000 | 0.0031000 | [0.0021849, 0.0043968] | 4.344994 | 6987.144311 |
| policy_beam_seed0 | 0.0001 | 7/10000 | 0.0007000 | [0.0003391, 0.0014443] | 7.766822 | 8376.246883 |
| policy_beam_seed0 | 0.0002 | 8/10000 | 0.0008000 | [0.0004054, 0.0015780] | 7.766822 | 8376.246883 |
| policy_beam_seed0 | 0.0005 | 52/10000 | 0.0052000 | [0.0039679, 0.0068122] | 7.766822 | 8376.246883 |

## Interpretation constraints

- The hardware graph and calibration families remain synthetic; this is not a named device calibration.
- Routing CNOT faults are now propagated gate by gate. This is the main Phase-6 upgrade over Phase 5.
- Idle faults are explicit once per route boundary for nonparticipating persistent data qubits, but continuous-time idling during each individual native sub-gate is still approximated.
- The native two-qubit Pauli channel on each routed CNOT reuses the corresponding logical-interaction 15-outcome profile, scaled by the physical-edge multiplier.
- The schedule-specific decoder still uses the noisy extraction record plus an ideal final memory-boundary syndrome.
- Any nonzero native C1 or failure of the single-fault checks means the routed implementation is not first-order fault tolerant under this model; C2 alone must not then be treated as the leading logical-failure term.
- Phase 6 is a validation study, not a new RL training phase.

