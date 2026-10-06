# Phase 7 summary

Scope: exact first-order fault forensics plus single-fault-certified nearest-neighbour bridge routing on the same synthetic 12-node graph.

The routing primitive is not assumed safe. Complete routed rounds enter the certified catalog only after exhaustive single-native-fault and incoming-single-data-error checks.

- Certified catalog size: 74
- Certified homogeneous rounds: 32
- Validation p: 0.0002
- Exact evaluation budget for proxy/random certified search: 3

## Phase 7A forensic result

- Unrouted logical control: conflicts=0, single-fault logical failures=0, incoming failures=0.
- Naive SWAP routing: C1=10.959424, single-fault failures=90, conflicts=14.
- Same logical schedule with bridge routing: C1=1.220188, single-fault failures=8, conflicts=2.
- Naive SWAP failing-fault stages: {'forward_swap': 48, 'reverse_swap': 42}.

## Phase 7B certified routing

### hw_id

| Method | Mean C1 | Mean C2 | Mean small-p score | FT pass | Mean native CX | Mean duration (us) | Exact evals/context |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive_swap_reference | 9.927890 | 13583.919599 | 0.00252893 | 0.0% | 180.0 | 42.877 | 1.0 |
| bridge_same_reference | 0.452210 | 2149.046400 | 0.00017640 | 0.0% | 114.0 | 29.318 | 1.0 |
| certified_fixed | 0.000000 | 3417.585849 | 0.00013670 | 100.0% | 150.0 | 40.048 | 1.0 |
| certified_random_search | 0.000000 | 2416.225460 | 0.00009665 | 100.0% | 142.0 | 36.652 | 3.0 |
| certified_proxy_search | 0.000000 | 2280.304991 | 0.00009121 | 100.0% | 142.0 | 36.652 | 3.0 |

### ood_hub0_bad

| Method | Mean C1 | Mean C2 | Mean small-p score | FT pass | Mean native CX | Mean duration (us) | Exact evals/context |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive_swap_reference | 19.184492 | 416311.621457 | 0.02048936 | 0.0% | 180.0 | 45.368 | 1.0 |
| bridge_same_reference | 7.213119 | 220126.973141 | 0.01024770 | 0.0% | 114.0 | 29.678 | 1.0 |
| certified_fixed | 0.000000 | 88529.358991 | 0.00354117 | 100.0% | 150.0 | 37.727 | 1.0 |
| certified_random_search | 0.000000 | 50370.093902 | 0.00201480 | 100.0% | 142.0 | 36.692 | 3.0 |
| certified_proxy_search | 0.000000 | 33973.376552 | 0.00135894 | 100.0% | 142.0 | 36.692 | 3.0 |

## Explicit finite-p diagnostics

| Method | p | failures/shots | logical failure rate | 95% interval | C1 | C2 |
|---|---:|---:|---:|---:|---:|---:|
| naive_swap_reference | 0.0001 | 2/3000 | 0.0006667 | [0.0001828, 0.0024276] | 9.927890 | 13583.919599 |
| naive_swap_reference | 0.0002 | 7/3000 | 0.0023333 | [0.0011307, 0.0048088] | 9.927890 | 13583.919599 |
| certified_proxy_search | 0.0001 | 0/3000 | 0.0000000 | [0.0000000, 0.0012788] | 0.000000 | 2280.304991 |
| certified_proxy_search | 0.0002 | 0/3000 | 0.0000000 | [0.0000000, 0.0012788] | 0.000000 | 2280.304991 |
| certified_random_search | 0.0001 | 0/3000 | 0.0000000 | [0.0000000, 0.0012788] | 0.000000 | 2416.225460 |
| certified_random_search | 0.0002 | 0/3000 | 0.0000000 | [0.0000000, 0.0012788] | 0.000000 | 2416.225460 |

## Interpretation constraints

- Phase 7 uses a bridge-CNOT primitive along deterministic paths that prefer no interior data qubits; the primitive itself is not declared fault tolerant.
- Fault tolerance is enforced at the complete routed-round level: catalog entries require C1=0, zero single-fault decoder conflicts/failures, and zero incoming-single-error failures.
- The certified catalog is a deliberately small structured family, not an exhaustive search over all physical circuits.
- The 12-node graph and calibration families remain synthetic.
- Native CNOT faults are explicit. Data idle faults remain discretized at route boundaries rather than continuously scheduled per sub-gate.
- This is one serialized Steane extraction round with an ideal final memory boundary, not repeated fault-tolerant memory.

