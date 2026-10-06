# Phase 4 patch

This patch extends the existing `qec_flag_project` from one-check schedule synthesis to a **full six-check Steane syndrome-extraction round**.

It does **not** create a new virtual environment and does not add any Python dependencies beyond the existing project requirements.

## Added files

- `run_phase4.py`
- `PHASE4_GUIDE.md`
- `PHASE4_SCIENTIFIC_SCOPE.md`
- `qecflag/phase4_physics.py`
- `qecflag/phase4_templates.py`
- `qecflag/phase4_noise.py`
- `qecflag/phase4_env.py`
- `qecflag/phase4_agent.py`
- `qecflag/phase4_simulation.py`
- `qecflag/phase4_experiment.py`
- `configs/phase4_smoke.json`
- `configs/phase4_full.json`
- `tests/test_phase4.py`
- `reference/phase4_smoke_summary.md`

## Merge into the existing project

From a terminal:

```bash
cd ~/Downloads
unzip -q -o qec_flag_phase4_patch.zip
cp -R qec_flag_phase4_patch/. ~/qec_flag_project/
cd ~/qec_flag_project
source .venv/bin/activate
```

Then follow `PHASE4_GUIDE.md`.

The patch is additive: it does not overwrite the Phase 1, 2, or 3 source files or the existing `runs/` results. It does add new files inside the same project directories.
