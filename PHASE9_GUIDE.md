# Phase 9 guide

Use the **same** `qec_flag_project` and the same `.venv` from Phases 1-8. No new package is required.

## 1. Install the patch

```bash
cd ~/Downloads
unzip -q -o qec_flag_phase9_patch.zip
cp -R qec_flag_phase9_patch/. ~/qec_flag_project/

cd ~/qec_flag_project
source .venv/bin/activate
```

## 2. Check the environment

```bash
python run_phase9.py doctor
```

The Python executable should point into `qec_flag_project/.venv/bin/python`.

## 3. Run the complete test suite

```bash
python -m pytest -q
```

Expected for the merged Phase 1-9 project used to build this patch:

```text
468 passed
```

## 4. Inspect the detector decoder

```bash
python run_phase9.py inspect-decoder
```

The reference development context produces hundreds of aggregate detector hyperedges and tens of thousands of order-2 event-map entries. The important checks are:

```text
single_fault_conflicts: 0
single_fault_failures: 0
incoming_failures: 0
detector_transform_roundtrip_ok: true
```

## 5. Inspect the low-p expansion

```bash
python run_phase9.py inspect-scaling
```

The output reports:

- `c1`
- exact `c2`
- malignant pair count
- sampled raw three-fault weight
- sampled three-fault standard error
- third-order Taylor estimate
- low-p predictions

For a certified circuit, the key requirement remains `c1 = 0`.

A negative third-order Taylor coefficient is not a failure: higher Taylor coefficients can be negative because expanding the independent no-fault factors subtracts probability mass from lower-order exact-fault sectors.

## 6. Run smoke

```bash
python run_phase9.py all \
  --config configs/phase9_smoke.json \
  --out runs/phase9_smoke
```

The smoke run is only an end-to-end execution check. Do not use its small-shot decoder rates as final evidence.

## 7. Run the full Phase-9 experiment

Phase 9 allocates large temporary arrays during exact two-fault enumeration. The recommended laptop command runs each noise family in a fresh child process and merges the reports automatically:

```bash
python run_phase9.py split \
  --config configs/phase9_full.json \
  --out runs/phase9_full
```

You can also run the monolithic version:

```bash
python run_phase9.py all \
  --config configs/phase9_full.json \
  --out runs/phase9_full
```

`split` is recommended because it keeps peak memory stable. It uses exactly the same family-specific random seeds as the monolithic experiment.

The full configuration uses:

- 3 repeated rounds;
- 5 synthetic test families;
- p = 0.00005, 0.0001, 0.0002, 0.0005;
- 30,000 paired Monte Carlo shots per p/family;
- exact C1/C2 calculation for one predeclared proxy-selected circuit per family;
- 30,000 importance-sampled three-fault histories per rare-event calculation.

## 8. Outputs

The top-level full run produces:

```text
runs/phase9_full/phase9_summary.md
runs/phase9_full/phase9_results.json
```

A monolithic `all` run additionally writes:

```text
phase9_low_order.csv
phase9_decoder_comparison.csv
phase9_certification.csv
```

A `split` run preserves each family's corresponding CSV files under:

```text
runs/phase9_full/parts/<family>/
```

## 9. How to read the result

The first table is the low-order analysis. The decisive checks are:

```text
C1 = 0
C2 > 0
predicted leading order = 2
```

The second section compares decoders. The detector decoder must keep:

```text
single_fault_failures = 0
single_fault_conflicts = 0
```

If its logical failure rate is below the history lookup, that does **not** mean it has beaten an omniscient exact decoder. The Phase-8 lookup was exact over its single-fault history table and fell back for unseen multi-fault histories; the Phase-9 detector decoder explicitly includes two-hyperedge explanations.

## Reference run

The included full reference summary was produced by running the five full-config families in fresh processes with the same canonical seeds and merging the outputs, equivalent to the `split` command. It is a reproducibility reference, not a substitute for your own run.
