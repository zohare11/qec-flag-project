# Phase 7 patch

Adds exact first-order fault forensics and a single-fault-certified physical-routing branch to the existing QEC project.

New files:

- `run_phase7.py`
- `qecflag/phase7_routing.py`
- `qecflag/phase7_forensics.py`
- `qecflag/phase7_catalog.py`
- `qecflag/phase7_experiment.py`
- `configs/phase7_smoke.json`
- `configs/phase7_full.json`
- `tests/test_phase7.py`
- `PHASE7_GUIDE.md`
- `PHASE7_SCIENTIFIC_SCOPE.md`
- `cache/phase7_certified_bridge_catalog.json`

No new Python dependencies are required.

The cached catalog is reproducible from `python run_phase7.py build-cache`; it is included so the normal test suite does not spend tens of seconds rebuilding physical certifications every time.
