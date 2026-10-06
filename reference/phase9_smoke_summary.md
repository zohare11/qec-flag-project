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
| hw_id | certified_proxy_history | 0 | 80634.8 | 7.05565e+07 | -4.21278e+07 | 4.27% | 2 |

## Decoder comparison

### hw_id

| p | History lookup | Detector hypergraph | Temporal majority |
|---:|---:|---:|---:|
| 0.0001 | 0.0006667 | 0.0000000 | 0.0346667 |
| 0.0002 | 0.0033333 | 0.0020000 | 0.0506667 |

- Log-log slope, history lookup: 2.322
- Log-log slope, detector hypergraph: nan
- Log-log slope, temporal majority: 0.547
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

