# Phase 7 guide

Phase 7 stops training ML and addresses the physical-routing failure uncovered in Phase 6.

It has two parts:

1. **Phase 7A: first-order fault forensics.** Trace every single physical fault that causes logical failure under the Phase-6 SWAP router, and verify that the corresponding unrouted logical circuit still passes its single-fault checks.
2. **Phase 7B: fault-tolerance-preserving physical routing.** Replace generic SWAP-forward/CNOT/SWAP-back routing with a nearest-neighbour bridge-CNOT construction, then admit a complete routed round only if exhaustive single-native-fault certification gives `C1 = 0` with zero decoder conflicts, zero single-fault logical failures, and zero incoming-single-error failures.

The bridge primitive is **not assumed to be fault tolerant by itself**. Certification is performed on the complete routed round.

## 1. Use the existing environment

```bash
cd ~/qec_flag_project
source .venv/bin/activate
python run_phase7.py doctor
```

No new packages are required.

## 2. Run all tests

```bash
python -m pytest -q
```

The Phase-7 development tree used to build this patch has **459 passing tests**.

## 3. Rebuild the certified physical catalog

```bash
python run_phase7.py build-cache
```

The deterministic Phase-7 build checks all 96 homogeneous Phase-5 hardware actions under the bridge router and then adds a small set of certified one-check variants around a safe base round.

For the current fixed topology, the reference build finds:

```text
certified homogeneous rounds: 32
certified catalog size:       74
```

The cache is written to:

```text
cache/phase7_certified_bridge_catalog.json
```

A round enters the catalog only if all of the following hold:

```text
C1 == 0
single-fault decoder conflicts == 0
single-fault logical failures == 0
incoming-single-data-error failures == 0
```

## 4. Run the forensic analysis

```bash
python run_phase7.py forensics
```

The important control is the logical, unrouted round. It should still report zero single-fault conflicts, zero single-fault logical failures, and zero incoming-error failures.

The Phase-6 SWAP implementation should report nonzero `C1`. The forensic output classifies the physical location of each first-order failure as preparation, measurement, idle, original logical CNOT, forward SWAP, or reverse SWAP.

For the reproducible development reference, every first-order failure of the naive routed reference circuit came from inserted SWAP CNOTs rather than the original logical CNOT locations.

The same logical schedule under the bridge router uses fewer native CNOTs and strongly reduces the first-order problem, but it is still not automatically certified. This is why Phase 7 filters complete rounds rather than declaring the primitive safe in advance.

## 5. Inspect a certified routed round

```bash
python run_phase7.py inspect-certified
```

This loads the first certified catalog entry, explicitly propagates every single native CNOT/preparation/readout/route-boundary-idle fault, and then evaluates its exact native `C2`.

The key fields should include:

```text
C1: 0.0
single_fault_conflicts: 0
single_fault_failures: 0
incoming_failures: 0
single_fault_FT_pass: true
```

## 6. Smoke experiment

```bash
python run_phase7.py all \
  --config configs/phase7_smoke.json \
  --out runs/phase7_smoke
```

If that directory already exists, choose a new one such as `runs/phase7_smoke_2`.

The smoke run compares:

- `naive_swap_reference`: Phase-6 SWAP routing;
- `bridge_same_reference`: the same logical schedule under bridge routing, without certification;
- `certified_fixed`: one certified physical round selected using training-only synthetic contexts;
- `certified_random_search`: bounded exact search over random certified rounds;
- `certified_proxy_search`: a cheap bridge-aware proxy ranks the certified catalog, followed by exact native evaluation of only the stated budget.

The ordering is **lexicographic**: fault-tolerance certification comes first. An uncertified circuit with a numerically attractive `C2` is not considered a valid replacement for a certified circuit.

## 7. Full Phase-7 experiment

```bash
python run_phase7.py all \
  --config configs/phase7_full.json \
  --out runs/phase7_full
```

The configured families are:

```text
hw_id
ood_hub0_bad
ood_hub1_bad
ood_edge_hotspot
ood_logical_shift
ood_mixed
```

The main output is:

```text
runs/phase7_full/phase7_summary.md
```

Additional files include:

```text
phase7_results.json
phase7_evaluation.csv
phase7_forensics.json
phase7_failing_faults.csv
```

## 8. How to interpret Phase 7

The main scientific question is no longer “does RL beat coordinate search?” It is:

> Can the same hardware graph support a physically routed implementation that retains the single-fault guarantee once routing gates are explicitly faulted?

A successful Phase-7 result requires `C1 = 0` and all single-fault checks to pass. Only after that should `C2`, duration, native-CX count, or bounded-search quality be compared.

Phase 7 still has important limitations: the 12-node graph and calibration families are synthetic, checks remain serialized, idle noise is discretized at route boundaries, and the decoder uses an ideal final memory-boundary syndrome. It is not repeated device-level fault-tolerant memory.
