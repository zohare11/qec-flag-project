# FT Compiler Repair v3 Patch

This patch is an overlay for the existing `qec_flag_project`.  It does not replace or modify the Phase 1-10, repair-v1, or repair-v2 namespaces.

## Added

- `ftrepair_v3/` package
- `run_ft_repair_v3.py`
- smoke / standard / full v3 configs
- v3 tests
- v3 guide and scientific scope
- development reference outputs

## Core implementation additions

- path-overridden bridge compiler states;
- exact native verification of custom physical paths;
- native-gate/route counterexample localization;
- hidden physical-path defect generation;
- richer check/template/hub/path repair actions;
- process-local verifier memoization;
- operation-level precedence scheduler;
- large-universe hybrid hitting-set synthesis;
- exact schedule recertification;
- chunk-first/deletion minimization of safe constraint sets;
- conservative-safe seed + operation-level refinement portfolio;
- cross-layer routing-candidate/scheduling portfolio;
- defect-count-stratified benchmark reporting.

## Dependencies

No new package dependency is required beyond the existing project environment.
