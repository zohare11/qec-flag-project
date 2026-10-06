# Phase 4 guide

Phase 4 moves from one flagged Steane stabilizer to a **complete six-check Steane syndrome-extraction round** and evaluates schedules with an explicit decoder and ideal memory boundaries.

The main experiment asks whether a learned proposal policy can use a small exact-search budget more effectively than random and deterministic alternatives when the synthetic calibration changes.

## 1. Install the patch

Do **not** create a new virtual environment. Keep using the existing `qec_flag_project/.venv`.

After downloading `qec_flag_phase4_patch.zip`:

```bash
cd ~/Downloads
unzip -q -o qec_flag_phase4_patch.zip
cp -R qec_flag_phase4_patch/. ~/qec_flag_project/
cd ~/qec_flag_project
source .venv/bin/activate
```

The `-o` flag avoids the interactive overwrite prompt if an old extracted copy exists in Downloads.

## 2. Check the environment

```bash
python run_phase4.py doctor
```

The Python executable should end in something like:

```text
qec_flag_project/.venv/bin/python
```

and `inside_virtual_environment` should be `true`.

No new packages are required.

## 3. Run all automated tests

```bash
python -m pytest -q
```

With the Phase 1-4 files used to build this patch, the expected result is:

```text
435 passed
```

If a test fails, stop before training and preserve the complete failure message.

## 4. Build/verify the Phase-4 action table

```bash
python run_phase4.py build-cache
```

Expected high-level output:

```text
PHASE 4 ACTION TABLE
  actions: 48
  A_only: 16
  B_only: 16
  A_and_B: 16
  full_round_space: 12230590464

PHASE 4 REFERENCE VERIFICATION
  fault_count: 564
  single_fault_conflicts: 0
  single_fault_logical_failures: 0
  single_incoming_error_failures: 0
```

The action table is selected from the Phase-3 certified catalog. If the Phase-3 catalog cache already exists, this is quick.

## 5. Run the smoke experiment

```bash
python run_phase4.py all \
  --config configs/phase4_smoke.json \
  --out runs/phase4_smoke
```

If that directory already exists, use a new name such as:

```bash
python run_phase4.py all \
  --config configs/phase4_smoke.json \
  --out runs/phase4_smoke_2
```

The smoke configuration is only a pipeline check. It uses one training seed, three test contexts per family, a four-schedule exact-search budget, and low-shot finite-p diagnostics.

It should print lines resembling:

```text
P4 TRAIN seed=0 proxy=...
P4 TRAIN seed=0 exact=...
P4 EVAL round_id: ...
P4 NOISE ...
PHASE 4 REPORT: .../phase4_summary.md
DONE Phase 4: ...
```

A tested reference smoke report is included in `reference/phase4_smoke_summary.md`. It is only a debugging reference and is not a substitute for your own run.

## 6. Run the full experiment

After smoke succeeds:

```bash
python run_phase4.py all \
  --config configs/phase4_full.json \
  --out runs/phase4_full
```

If the destination exists, use another name rather than deleting a previous run:

```bash
python run_phase4.py all \
  --config configs/phase4_full.json \
  --out runs/phase4_full_2
```

The full configuration uses:

- three independent training seeds;
- 2,048 synthetic training calibrations;
- 900 cheap-proxy actor-critic updates per seed;
- 40 small exact-C2 fine-tuning updates per seed;
- eight ID/OOD evaluation families;
- 12 test calibrations per family;
- an exact-search budget of eight complete schedules per context for random, coordinate, and policy-beam search;
- 50,000 finite-p diagnostic shots per reported point.

Expect a runtime of **several minutes**, depending on the Mac. Full-round exact C2 evaluation enumerates malignant pairs, so it is intentionally much more expensive than Phases 1-3.

## 7. Read the results

Open:

```text
runs/phase4_full/phase4_summary.md
```

The detailed machine-readable output is:

```text
runs/phase4_full/phase4_results.json
```

Per-case C2 values are in:

```text
runs/phase4_full/phase4_cases.csv
```

Saved policies and training logs are also stored in the run directory.

## 8. How to interpret the methods

### `reference`

The same `0A12A3` A-flag template is used for all six checks.

### `proxy_fixed`

One context-independent six-check schedule is chosen using mean local component costs over the training calibration set.

### `local_greedy`

For each calibration, every check independently chooses the locally cheapest template according to the Phase-3 component C2 proxy. Only the resulting complete round is evaluated with exact full-round C2.

This is an important baseline because it tests whether cross-check learning/search is needed at all.

### `random_search`

Samples the configured number of complete six-check schedules uniformly and evaluates each with exact full-round C2.

### `coordinate_search`

Starts from the local-greedy schedule, proposes low-proxy one-check substitutions, and spends the same exact full-round evaluation budget as random/policy-beam search.

This is the strongest simple deterministic search baseline in Phase 4.

### `policy_greedy`

The learned actor produces one complete six-check schedule. It gets one full-round exact evaluation.

### `policy_beam`

The policy expands a beam using neural probabilities only. It does **not** query full-round C2 while building the beam. The final beam contains at most the configured number of complete schedules, which are then evaluated exactly.

The exact-evaluation budget is matched to `random_search` and `coordinate_search`.

## 9. Primary comparisons

The report gives mean and median full-round C2, plus paired comparisons.

The most important comparisons are:

1. `policy_beam` vs `random_search` under the same exact-evaluation budget;
2. `policy_beam` vs `coordinate_search` under the same exact-evaluation budget;
3. `policy_greedy` vs `local_greedy` to see whether the neural policy alone adds anything;
4. flag-template mixtures under `ood_flagA_bad` and `ood_flagB_bad` to check whether the model actually adapts the architecture to the calibration.

There is no global oracle in Phase 4. Do not call the best observed schedule globally optimal.

## 10. Finite-p diagnostics

The final table estimates logical failure probabilities for one predeclared `round_id` calibration.

These are one-round memory-style diagnostics with an explicit decoder and ideal initial/final boundaries. They are not physical-device logical error rates.

At low p, failure counts can be small. Use the Wilson confidence intervals rather than overinterpreting a difference of one or two failures.

## 11. What to send back

After the full run, send the complete contents of:

```text
runs/phase4_full/phase4_summary.md
```

If the run used another output name, send that folder's `phase4_summary.md` instead.

The Phase-4 decision will be based mainly on whether policy-guided bounded search consistently improves over random and coordinate search, and whether that advantage survives the OOD calibration families.
