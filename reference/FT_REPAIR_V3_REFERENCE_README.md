# FT Repair v3 development references

The included smoke summary is a software-validation run only. The smoke config intentionally disables the expensive v2 baselines and mixed/cross-layer benchmark so that installation can be checked quickly.

Development checks completed while building v3:

- **Core v3 tests:** five core tests passed together in 27.28 s. The cross-layer portfolio test passed separately in 15.72 s. A monolithic six-test run exceeded the tool execution window, so no claim is made that all six completed in one process.
- **Repair-v1 regression suite:** 5 passed in 16.14 s.
- **Smoke experiment:** completed end to end in about 28 s. The selected routing defect repaired with 8 exact verifier calls and exact hidden changed-check recovery. The v3 schedule portfolio restored C1=0 with four operation constraints, true native-CX concurrency, and about 7.85% speedup over fully serialized execution. Pure operation-CEGIS did not certify within the deliberately small smoke budget.
- **Split smoke execution:** completed successfully and merged family-isolated CSV/JSON/Markdown outputs.
- **Path-defect experiment:** a semantics-preserving alternate physical bridge path produced C1 about 0.779742. V3 repaired it to C1=0 with one path edit; witness-route recall was 100% in the one-case development experiment. The compact experiment used 9 exact verifier calls for the repair.
- **Mixed staged development case:** routing + schedule repair succeeded with true CX concurrency and about 7.85% retained speedup; total reported verifier calls were 29.
- **Cross-layer development case:** with one routing candidate, the cross-layer path also succeeded with total reported verifier calls 26 and the same 7.85% speedup. A separate two-routing-candidate inspection showed that exact-safe routing alternatives can have materially different downstream schedulability: one retained about 7.85% speedup with four schedule constraints, while another retained only about 1.35% with five constraints.

Use the user's local standard/full runs, not these development references, for research conclusions.
