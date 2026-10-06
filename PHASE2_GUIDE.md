# Phase 2: learning paradigm + robustness

This phase leaves the Phase-1 files and `runs/full_2` untouched.

## Scientific question

For the same finite library of 96 certified flagged-check schedules:

1. Does one-step REINFORCE outperform supervised alternatives when all methods receive the same calibration context at inference time?
2. Does training on a broader, domain-randomized synthetic noise distribution improve performance on held-out synthetic distribution shifts?

The methods do **not** receive the same amount of training information:

- `reinforce`: sampled action cost plus fixed-reference cost; no oracle argmin labels.
- `classifier`: full 96-schedule costs are computed offline and reduced to tied-oracle soft labels.
- `cost_regressor`: full 96-schedule costs are computed offline and used as regression targets.

This distinction must remain attached to any comparison.

## Synthetic test families

- `narrow`: the original Phase-1 training distribution.
- `broad_shift`: the original broader Phase-1 shifted distribution.
- `ood_edge_hotspot`: one data CNOT edge is much noisier than the others.
- `ood_flag_hotspot`: the flag-to-syndrome CNOT edge is much noisier.
- `ood_readout_hotspot`: ancilla readout locations are much noisier.
- `ood_pauli_sparse`: CNOT faults are concentrated into a few Pauli outcomes.

These are stress tests, **not hardware calibration data**.

## Commands

With `(qec_flag_env)` active and VS Code opened at `qec_flag_project`:

```bash
python run_phase2.py doctor
python -m pytest -q
python run_phase2.py all --config configs/phase2_smoke.json --out runs/phase2_smoke
python run_phase2.py all --config configs/phase2_full.json --out runs/phase2_full
```

Never reuse a nonempty `--out` folder for `all`; use `runs/phase2_full_2`, etc.

## Main outputs

- `phase2_summary.md`: readable tables and interpretation caveats.
- `phase2_evaluation.json`: complete nested results.
- `phase2_evaluation_cases.csv`: every context/method decision.
- `phase2_seed_aggregates.csv`: compact learned-method results.
- `training_summary.json`: training information budgets and checkpoint summaries.
- `learning_curves_narrow.svg`
- `learning_curves_domain_randomized.svg`
- `robustness.svg`

## What would count as a useful result?

- If supervised learning strongly outperforms REINFORCE, schedule selection is better treated as supervised compilation while the library is exhaustively labelable.
- If domain randomization lowers OOD regret without destroying ID performance, broader synthetic training improves robustness in this model.
- If REINFORCE remains competitive despite using weaker training information, that supports keeping RL for a later sequential synthesis stage where exhaustive labels are unavailable.
- If none of the learned methods beats 16-candidate random search on OOD families, the current context representation or training distributions are not robust enough to justify scaling yet.
