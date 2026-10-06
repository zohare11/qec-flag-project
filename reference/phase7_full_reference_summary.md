# Phase 7 summary

Scope: exact first-order fault forensics plus single-fault-certified nearest-neighbour bridge routing on the same synthetic 12-node graph.

The routing primitive is not assumed safe. Complete routed rounds enter the certified catalog only after exhaustive single-native-fault and incoming-single-data-error checks.

- Certified catalog size: 74
- Certified homogeneous rounds: 32
- Validation p: 0.0002
- Exact evaluation budget for proxy/random certified search: 4

## Phase 7A forensic result

- Unrouted logical control: conflicts=0, single-fault logical failures=0, incoming failures=0.
- Naive SWAP routing: C1=18.794000, single-fault failures=90, conflicts=9.
- Same logical schedule with bridge routing: C1=0.332133, single-fault failures=8, conflicts=2.
- Naive SWAP failing-fault stages: {'forward_swap': 57, 'reverse_swap': 33}.

## Phase 7B certified routing

### hw_id

| Method | Mean C1 | Mean C2 | Mean small-p score | FT pass | Mean native CX | Mean duration (us) | Exact evals/context |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive_swap_reference | 16.227602 | 18485.811207 | 0.00398495 | 0.0% | 180.0 | 44.728 | 1.0 |
| bridge_same_reference | 0.776829 | 4633.521874 | 0.00034071 | 0.0% | 114.0 | 29.105 | 1.0 |
| certified_fixed | 0.000000 | 4060.043654 | 0.00016240 | 100.0% | 150.0 | 38.015 | 1.0 |
| certified_random_search | 0.000000 | 3817.307878 | 0.00015269 | 100.0% | 152.0 | 38.939 | 4.0 |
| certified_proxy_search | 0.000000 | 3356.320661 | 0.00013425 | 100.0% | 150.0 | 38.015 | 4.0 |

### ood_edge_hotspot

| Method | Mean C1 | Mean C2 | Mean small-p score | FT pass | Mean native CX | Mean duration (us) | Exact evals/context |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive_swap_reference | 18.835450 | 34614.956839 | 0.00515169 | 0.0% | 180.0 | 43.521 | 1.0 |
| bridge_same_reference | 0.509577 | 10791.521195 | 0.00053358 | 0.0% | 114.0 | 30.138 | 1.0 |
| certified_fixed | 0.000000 | 9428.945791 | 0.00037716 | 100.0% | 150.0 | 38.026 | 1.0 |
| certified_random_search | 0.000000 | 10411.420635 | 0.00041646 | 100.0% | 170.0 | 42.540 | 4.0 |
| certified_proxy_search | 0.000000 | 8995.835864 | 0.00035983 | 100.0% | 150.0 | 38.026 | 4.0 |

### ood_hub0_bad

| Method | Mean C1 | Mean C2 | Mean small-p score | FT pass | Mean native CX | Mean duration (us) | Exact evals/context |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive_swap_reference | 50.493821 | 399277.824058 | 0.02606988 | 0.0% | 216.0 | 64.361 | 1.0 |
| bridge_same_reference | 28.692964 | 220609.114971 | 0.01456296 | 0.0% | 114.0 | 36.388 | 1.0 |
| certified_fixed | 0.000000 | 213007.921410 | 0.00852032 | 100.0% | 150.0 | 47.112 | 1.0 |
| certified_random_search | 0.000000 | 136468.802452 | 0.00545875 | 100.0% | 142.0 | 45.618 | 4.0 |
| certified_proxy_search | 0.000000 | 82046.516950 | 0.00328186 | 100.0% | 142.0 | 45.051 | 4.0 |

### ood_hub1_bad

| Method | Mean C1 | Mean C2 | Mean small-p score | FT pass | Mean native CX | Mean duration (us) | Exact evals/context |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive_swap_reference | 42.205306 | 39635.901062 | 0.01002650 | 0.0% | 180.0 | 45.072 | 1.0 |
| bridge_same_reference | 0.681431 | 40700.565064 | 0.00176431 | 0.0% | 114.0 | 35.156 | 1.0 |
| certified_fixed | 0.000000 | 39582.928975 | 0.00158332 | 100.0% | 150.0 | 49.962 | 1.0 |
| certified_random_search | 0.000000 | 41505.798053 | 0.00166023 | 100.0% | 142.0 | 44.971 | 4.0 |
| certified_proxy_search | 0.000000 | 49441.891597 | 0.00197768 | 100.0% | 156.0 | 47.507 | 4.0 |

### ood_logical_shift

| Method | Mean C1 | Mean C2 | Mean small-p score | FT pass | Mean native CX | Mean duration (us) | Exact evals/context |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive_swap_reference | 6.532913 | 8826.141894 | 0.00165963 | 0.0% | 180.0 | 44.774 | 1.0 |
| bridge_same_reference | 0.517640 | 2642.426303 | 0.00020923 | 0.0% | 114.0 | 28.247 | 1.0 |
| certified_fixed | 0.000000 | 2448.111917 | 0.00009792 | 100.0% | 150.0 | 36.599 | 1.0 |
| certified_random_search | 0.000000 | 3855.266422 | 0.00015421 | 100.0% | 142.0 | 34.980 | 4.0 |
| certified_proxy_search | 0.000000 | 2355.349633 | 0.00009421 | 100.0% | 164.0 | 40.166 | 4.0 |

### ood_mixed

| Method | Mean C1 | Mean C2 | Mean small-p score | FT pass | Mean native CX | Mean duration (us) | Exact evals/context |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive_swap_reference | 12.129400 | 101532.915139 | 0.00648720 | 0.0% | 180.0 | 56.740 | 1.0 |
| bridge_same_reference | 1.837438 | 52682.517100 | 0.00247479 | 0.0% | 114.0 | 36.421 | 1.0 |
| certified_fixed | 0.000000 | 12418.530790 | 0.00049674 | 100.0% | 150.0 | 47.961 | 1.0 |
| certified_random_search | 0.000000 | 11597.699849 | 0.00046391 | 100.0% | 138.0 | 44.464 | 4.0 |
| certified_proxy_search | 0.000000 | 8943.583806 | 0.00035774 | 100.0% | 134.0 | 42.830 | 4.0 |

## Explicit finite-p diagnostics

| Method | p | failures/shots | logical failure rate | 95% interval | C1 | C2 |
|---|---:|---:|---:|---:|---:|---:|
| naive_swap_reference | 5e-05 | 0/10000 | 0.0000000 | [0.0000000, 0.0003840] | 2.550455 | 8837.983292 |
| naive_swap_reference | 0.0001 | 4/10000 | 0.0004000 | [0.0001556, 0.0010281] | 2.550455 | 8837.983292 |
| naive_swap_reference | 0.0002 | 11/10000 | 0.0011000 | [0.0006144, 0.0019688] | 2.550455 | 8837.983292 |
| naive_swap_reference | 0.0005 | 27/10000 | 0.0027000 | [0.0018563, 0.0039256] | 2.550455 | 8837.983292 |
| certified_proxy_search | 5e-05 | 1/10000 | 0.0001000 | [0.0000177, 0.0005663] | 0.000000 | 2592.735154 |
| certified_proxy_search | 0.0001 | 0/10000 | 0.0000000 | [0.0000000, 0.0003840] | 0.000000 | 2592.735154 |
| certified_proxy_search | 0.0002 | 2/10000 | 0.0002000 | [0.0000548, 0.0007290] | 0.000000 | 2592.735154 |
| certified_proxy_search | 0.0005 | 3/10000 | 0.0003000 | [0.0001020, 0.0008817] | 0.000000 | 2592.735154 |
| certified_random_search | 5e-05 | 0/10000 | 0.0000000 | [0.0000000, 0.0003840] | 0.000000 | 3289.800314 |
| certified_random_search | 0.0001 | 1/10000 | 0.0001000 | [0.0000177, 0.0005663] | 0.000000 | 3289.800314 |
| certified_random_search | 0.0002 | 1/10000 | 0.0001000 | [0.0000177, 0.0005663] | 0.000000 | 3289.800314 |
| certified_random_search | 0.0005 | 14/10000 | 0.0014000 | [0.0008342, 0.0023488] | 0.000000 | 3289.800314 |

## Interpretation constraints

- Phase 7 uses a bridge-CNOT primitive along deterministic paths that prefer no interior data qubits; the primitive itself is not declared fault tolerant.
- Fault tolerance is enforced at the complete routed-round level: catalog entries require C1=0, zero single-fault decoder conflicts/failures, and zero incoming-single-error failures.
- The certified catalog is a deliberately small structured family, not an exhaustive search over all physical circuits.
- The 12-node graph and calibration families remain synthetic.
- Native CNOT faults are explicit. Data idle faults remain discretized at route boundaries rather than continuously scheduled per sub-gate.
- This is one serialized Steane extraction round with an ideal final memory boundary, not repeated fault-tolerant memory.

