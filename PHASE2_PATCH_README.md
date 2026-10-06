# Phase 2 patch for `qec_flag_project`

This patch adds Phase 2 without modifying the Phase-1 source files or your existing `runs/full_2` directory.

## Add the files

Copy the **contents** of this patch folder into the root of your existing `qec_flag_project` folder. The directory structure should become:

```text
qec_flag_project/
  run_phase2.py
  PHASE2_GUIDE.md
  qecflag/
    phase2_noise.py
    phase2_models.py
    phase2_experiment.py
  configs/
    phase2_smoke.json
    phase2_full.json
  tests/
    test_phase2.py
  ...your existing Phase-1 files...
```

No existing Phase-1 file needs to be replaced.

## Run

Activate the environment you already created for this project:

```bash
cd ~/qec_flag_project
source .venv/bin/activate
```

Then:

```bash
python run_phase2.py doctor
python -m pytest -q
python run_phase2.py all --config configs/phase2_smoke.json --out runs/phase2_smoke
python run_phase2.py all --config configs/phase2_full.json --out runs/phase2_full
```

Expected unit-test count for this patch: **409 passed**.

The full run can take a few minutes because it trains 18 models: three learning methods x two training regimes x three random seeds.

## Return these results

Open `runs/phase2_full/phase2_summary.md` and paste the entire file into ChatGPT. Also mention whether the command completed without errors.

Do not overwrite a previous run directory. If `runs/phase2_full` already exists, use `runs/phase2_full_2`.
