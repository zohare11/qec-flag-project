# Phase 9 summary

Scope: low-order repeated-round scaling analysis and detector-event decoding for the Phase-8 physically certified Steane memory circuits.

- Repeated rounds: 3
- Physical catalog: 74 continuously-idle-certified routed circuits
- Low-order analysis: exact C1/C2 for the primary history decoder plus importance-sampled raw three-fault weight and p^3 Taylor estimate.
- Scalable baseline: order-2 detector-hypergraph decoder over syndrome-difference detector events plus flags; this is not MWPM/PyMatching.
- Majority-vote decoding is retained only as a weak baseline.

## Low-order rare-event analysis

| Family | Method | C1 | exact C2 | raw T3 estimate | p^3 Taylor coeff estimate | T3 rel. SE | predicted leading order |
|---|---|---:|---:|---:|---:|---:|---:|
| hw_id | certified_proxy_history | 0 | 80634.8 | 7.19128e+07 | -4.07715e+07 | 1.34% | 2 |
| ood_idle_hotspot | certified_proxy_history | 0 | 125166 | 1.40212e+08 | -6.91419e+07 | 1.25% | 2 |
| ood_slow_link | certified_proxy_history | 0 | 26387.6 | 1.11745e+07 | -6.159e+06 | 1.05% | 2 |
| ood_logical_shift | certified_proxy_history | 0 | 16142.5 | 5.91164e+06 | -3.89792e+06 | 1.34% | 2 |
| ood_mixed | certified_proxy_history | 0 | 297733 | 3.78762e+08 | -2.23467e+08 | 0.96% | 2 |

## Decoder comparison

### hw_id

| p | History lookup | Detector hypergraph | Temporal majority |
|---:|---:|---:|---:|
| 5e-05 | 0.0000667 | 0.0000000 | 0.0155333 |
| 0.0001 | 0.0005667 | 0.0000667 | 0.0289000 |
| 0.0002 | 0.0029667 | 0.0005667 | 0.0612000 |
| 0.0005 | 0.0157000 | 0.0068000 | 0.1471333 |

- Log-log slope, history lookup: 2.354
- Log-log slope, detector hypergraph: 2.865
- Log-log slope, temporal majority: 0.986
- Detector single-fault failures: 0
- Detector single-fault conflicts: 0

### ood_idle_hotspot

| p | History lookup | Detector hypergraph | Temporal majority |
|---:|---:|---:|---:|
| 5e-05 | 0.0003000 | 0.0001333 | 0.0187333 |
| 0.0001 | 0.0010333 | 0.0002333 | 0.0361667 |
| 0.0002 | 0.0046667 | 0.0013333 | 0.0747333 |
| 0.0005 | 0.0241000 | 0.0104667 | 0.1832333 |

- Log-log slope, history lookup: 1.927
- Log-log slope, detector hypergraph: 1.967
- Log-log slope, temporal majority: 0.995
- Detector single-fault failures: 0
- Detector single-fault conflicts: 0

### ood_slow_link

| p | History lookup | Detector hypergraph | Temporal majority |
|---:|---:|---:|---:|
| 5e-05 | 0.0001333 | 0.0000667 | 0.0068333 |
| 0.0001 | 0.0003667 | 0.0001000 | 0.0160667 |
| 0.0002 | 0.0009667 | 0.0002667 | 0.0323000 |
| 0.0005 | 0.0059333 | 0.0019333 | 0.0786667 |

- Log-log slope, history lookup: 1.636
- Log-log slope, detector hypergraph: 1.482
- Log-log slope, temporal majority: 1.053
- Detector single-fault failures: 0
- Detector single-fault conflicts: 0

### ood_logical_shift

| p | History lookup | Detector hypergraph | Temporal majority |
|---:|---:|---:|---:|
| 5e-05 | 0.0000000 | 0.0000000 | 0.0058667 |
| 0.0001 | 0.0001667 | 0.0000333 | 0.0118667 |
| 0.0002 | 0.0006333 | 0.0001667 | 0.0220667 |
| 0.0005 | 0.0033667 | 0.0007333 | 0.0575667 |

- Log-log slope, history lookup: 1.865
- Log-log slope, detector hypergraph: 1.905
- Log-log slope, temporal majority: 0.984
- Detector single-fault failures: 0
- Detector single-fault conflicts: 0

### ood_mixed

| p | History lookup | Detector hypergraph | Temporal majority |
|---:|---:|---:|---:|
| 5e-05 | 0.0006333 | 0.0000667 | 0.0247000 |
| 0.0001 | 0.0026333 | 0.0003667 | 0.0517333 |
| 0.0002 | 0.0105000 | 0.0031333 | 0.0997333 |
| 0.0005 | 0.0505333 | 0.0242667 | 0.2390000 |

- Log-log slope, history lookup: 1.904
- Log-log slope, detector hypergraph: 2.601
- Log-log slope, temporal majority: 0.981
- Detector single-fault failures: 0
- Detector single-fault conflicts: 0

## Interpretation constraints

- C2 is evaluated exactly only for the selected rare-event circuit/context rows; the three-fault term is importance-sampled and therefore has sampling uncertainty.
- The reported p^3 Taylor estimate is meaningful when C1=0; it subtracts the cubic no-fault expansion associated with malignant pairs.
- The detector decoder is a fixed-order hypergraph decoder. It scales polynomially in the number of repeated rounds for this fixed Steane circuit family, but it is not a large-code decoder.
- The exact history lookup remains the small-code reference decoder and still uses the ideal final memory-boundary syndrome.
- Native bridge-CNOT faults and serialized per-interval data idling remain explicit; the hardware graph and calibration families remain synthetic.
- Checks remain serialized and no crosstalk, leakage, or real-backend calibration is modeled.
- Phase 9 is a decoder/scaling validation phase; it does not retrain the proposal policy.

