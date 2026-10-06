# Phase 10 Guide — fault-tolerance-aware parallel scheduling

Phase 10 keeps the Phase-7/8/9 physically certified bridge-routed Steane circuits fixed and changes only **when** physical operations execute. It is a deterministic scheduling study; no new RL model is trained.

## Scientific question

Can resource-valid parallelism shorten a certified syndrome-extraction round without destroying the single-fault guarantee, and if so does the shorter schedule improve repeated-round logical performance?

The scheduler works at the physical-operation level:

- syndrome/flag preparation blocks,
- every native bridge CNOT,
- syndrome/flag measurement blocks.

Same-check operation order is never changed. Operations from different checks may overlap only when their physical-qubit resources are disjoint.

Every proposed schedule is then re-simulated in the resulting temporal order. **Resource validity is not treated as fault-tolerance certification.** A schedule is admissible only if it preserves the ideal circuit and passes:

- `C1 == 0`,
- zero single-fault decoder conflicts,
- zero single-fault logical failures,
- zero incoming-single-data-error failures.

## Baselines

Phase 10 evaluates the same physical circuit with:

- `serialized` — Phase-9-style fully serialized execution.
- `ancilla_overlap` — keeps all native CNOTs globally serialized, but allows disjoint prep/measurement blocks to overlap.
- `asap` — starts any ready resource-compatible operation immediately.
- `shortest_greedy` — gives shorter ready operations priority.
- `critical_greedy` — prioritizes the check with the largest remaining duration.
- `noise_greedy` — prioritizes activity on high-idle-rate data qubits.
- `css_block` — parallelizes within the X-check block, then within the Z-check block.
- `local_search` — local search over static check-priority permutations using a timing/idle proxy.
- `beam_search` — deterministic beam search over static check-priority permutations using the same proxy.

The local/beam search is not arbitrary gate synthesis and is not learned search.

## Install

Merge into the existing project and keep the same environment:

```bash
cd ~/Downloads
unzip -q -o qec_flag_phase10_patch.zip
cp -R qec_flag_phase10_patch/. ~/qec_flag_project/

cd ~/qec_flag_project
source .venv/bin/activate
```

No new packages are required.

## Checks

```bash
python run_phase10.py doctor
python -m pytest -q
```

Then inspect one representative schedule set:

```bash
python run_phase10.py inspect-schedule
```

and its physical certification:

```bash
python run_phase10.py inspect-certification
```

`inspect-certification` is intentionally important: a schedule can be much shorter and still be rejected if the new interleaving creates first-order fault mechanisms.

## Smoke

```bash
python run_phase10.py all \
  --config configs/phase10_smoke.json \
  --out runs/phase10_smoke
```

## Full experiment

Use split mode so each synthetic noise family runs in a fresh Python process:

```bash
python run_phase10.py split \
  --config configs/phase10_full.json \
  --out runs/phase10_full
```

Main output:

```text
runs/phase10_full/phase10_summary.md
```

Supporting files:

- `phase10_schedule_metrics.csv` — timing, idle exposure, C1, certification outcomes.
- `phase10_repeated_detector.csv` — three-round detector-decoder logical diagnostics for FT-safe schedules.
- `phase10_timeline_first_context.csv` — physical event timeline for inspection.
- `phase10_results.json` — machine-readable complete summary.

## Metrics

For every scheduler Phase 10 reports:

- total round duration,
- native CNOT count,
- total persistent-data idle time,
- maximum number of simultaneous native CNOTs,
- physical single-fault coefficient C1,
- exact single-fault certification outcome.

Repeated-round Monte Carlo is run only on physically admissible schedules, using the Phase-9 order-2 detector-hypergraph decoder.

## Interpretation

A shorter schedule is not automatically a better schedule. In particular, if an interleaving yields `C1 > 0`, it is rejected even if it reduces duration or idle time substantially.

Phase 10 therefore answers a prerequisite question for any later learned scheduler: **does the current certified circuit family contain useful physically fault-tolerant concurrency at all?**
