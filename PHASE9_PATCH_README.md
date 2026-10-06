# Phase 9 patch

Phase 9 is a decoder/scaling validation phase. It does **not** retrain the Phase-5 proposal policy and it does not expand the physical routing catalog.

It adds two capabilities on top of the 74 Phase-8 continuously-idle-certified bridge circuits:

1. **Low-order rare-event analysis** for the three-round memory experiment. C1 and C2 are computed exactly for the primary history decoder. The raw malignant three-fault weight is importance-sampled, and a third-order Taylor estimate is reported after subtracting the cubic no-fault correction from malignant pairs.
2. **Detector-event decoding**. Syndrome histories are converted to time-difference detector events and combined with flag outcomes. A deterministic order-2 detector-hypergraph decoder constructs minimum-fault-order explanations from zero, one, or two single-fault hyperedges. It is designed to scale polynomially with repeated rounds for this fixed Steane pilot.

The detector decoder is deliberately **not called MWPM**. Flagged extraction faults can produce more than two detector events, so the circuit naturally gives a hypergraph rather than an ordinary matching graph. No new Python package is required.

New files:

- `run_phase9.py`
- `qecflag/phase9_analysis.py`
- `qecflag/phase9_experiment.py`
- `configs/phase9_smoke.json`
- `configs/phase9_full.json`
- `tests/test_phase9.py`
- `PHASE9_GUIDE.md`
- `PHASE9_SCIENTIFIC_SCOPE.md`
- `reference/phase9_smoke_summary.md`
- `reference/phase9_full_reference_summary.md`
- `reference/phase9_full_reference_results.json`

The full Phase 1-9 test suite used to build this patch reports **468 passed**.
