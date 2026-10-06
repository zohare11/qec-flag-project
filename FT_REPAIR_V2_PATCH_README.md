# FT Compiler Repair v2 Patch

Merge this patch into the existing `qec_flag_project` after the original FT compiler-repair fork.

## Added files

- `run_ft_repair_v2.py`
- `ftrepair_v2/__init__.py`
- `ftrepair_v2/hittingset.py`
- `ftrepair_v2/mutations.py`
- `ftrepair_v2/routing_cegis.py`
- `ftrepair_v2/schedule_cegis.py`
- `ftrepair_v2/mixed_repair.py`
- `ftrepair_v2/experiment.py`
- `configs/ft_repair_v2_smoke.json`
- `configs/ft_repair_v2_standard.json`
- `configs/ft_repair_v2_full.json`
- `tests/test_ft_repair_v2.py`
- `FT_REPAIR_V2_GUIDE.md`
- `FT_REPAIR_V2_SCIENTIFIC_SCOPE.md`

The patch does not remove or overwrite the v1 `ftrepair/` implementation.

## Key methodological changes

1. Hidden multi-defect lowering cases with 1–3 simultaneous compiler mutations.
2. Best-first counterexample-guided local repair without access to hidden defect labels.
3. Exact minimum-hitting-set reasoning over accumulated schedule counterexamples.
4. Explicit pure-hitting-set ablation.
5. Robust scheduling portfolio using exact minimization of a certified seed.
6. Mixed lowering+scheduling repair.
7. V1 baselines retained in the same benchmark.
8. Hidden defect-set precision/recall metrics.

## Safety rule

Every accepted repair must pass the exact physical single-fault verifier. Optimization metrics are secondary.
