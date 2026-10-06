# QEC flag-gadget scheduling: a complete, bounded research pilot

This project studies **RL selection of a fault-checked gate order for one Steane-code stabilizer measurement**. It is not unrestricted circuit synthesis, a new code, or a complete noisy fault-tolerant error-correction cycle.

The pipeline is:

`independent physics tests -> exhaustive fault certification -> nontriviality check -> REINFORCE training -> held-out baselines -> noisy component diagnostics -> report`

## Start here

Use the Mac instructions in `VS_CODE_SETUP.md`. Create a new folder/environment separate from `qram_project`. No QRAM files are imported. No Qiskit, PyTorch, Gymnasium, Stim, GPU, cloud account, or hardware access is required. NumPy and pytest are the only third-party dependencies.

After creating and activating `.venv`:

```bash
python -m pip install -r requirements.txt
python run_pipeline.py doctor
python -m pytest -q
python run_pipeline.py all --config configs/smoke.json --out runs/smoke
python run_pipeline.py all --config configs/full.json --out runs/full
```

The unit suite has **397 tests**. `all` repeats those tests and stops before training if they fail. An existing nonempty `all` output directory is not overwritten: choose `runs/full_2` for another run.

The smoke run checks the entire workflow with one short training run. The full run uses three training seeds, held-out and shifted noise contexts, and more Monte Carlo samples. Neither profile assumes that RL must beat a baseline.

## What the experiment actually does

Seven data qubits encode one logical qubit using the Steane code. The circuit measures the Z-type stabilizer acting on data qubits 0, 1, 2, and 3. A syndrome ancilla is prepared in |0>; a flag ancilla is prepared in |+>. Each data qubit controls one CNOT into the syndrome ancilla. The flag controls two CNOTs into that same syndrome ancilla. Finally, measure the syndrome in Z and the flag in X.

A schedule such as `0F12F3` means:

```text
data0 -> syndrome
flag  -> syndrome
data1 -> syndrome
data2 -> syndrome
flag  -> syndrome
data3 -> syndrome
```

We enumerate all 360 arrangements of the four distinct data couplings and two identical flag couplings. All implement the same ideal measurement; only 96 pass the specified single-fault and recovery checks. The other 264 are correctly rejected, not software errors.

The RL policy receives a synthetic noise-calibration vector and chooses one of the 96 certified schedules. It uses **one-step REINFORCE**, also called a contextual bandit. It does not invent gates or receive optimal-action labels during training. A small two-layer NumPy network and Adam optimizer are included, with numerical gradient tests. PPO is not needed for this one-decision task.

The objective is **C2**, the leading second-order logical-failure coefficient in the documented component experiment. Smaller is better. C2 is not itself a probability, a gate count, a fidelity, or a physical-device error rate.

**All selected circuits contain six CNOTs.** This project optimizes fault sensitivity, not CNOT count.

## The most important limitation

After the one noisy check, the diagnostic uses a hypothetical **perfect six-bit Steane syndrome and noiseless recovery**. This is a way to test the errors created by this component, not a model of an entire real error-correction cycle. The extracted noisy syndrome bit is checked for ideal measurement correctness but is not used by that perfect-recovery oracle. The flag is used.

Noise consists of independent stochastic Pauli errors at CNOTs, ancilla preparations, and readout. There is no idle noise, leakage, T1/T2 simulation, crosstalk, or restricted physical routing. See `SCIENTIFIC_SCOPE.md` for the complete contract before interpreting an error rate.

## Tests and certificates

The checks include:

- Steane stabilizer commutation, independence, distance three, and logical-operator recognition.
- A dense encoded-logical-map cross-check of stabilizer equivalence.
- Full ideal measurement operators on all 16 active-data basis inputs, not just one input state.
- Independent dense-vector checks of all 33,840 enumerated single-fault propagations across the 360 schedules.
- All 21 single-qubit incoming data errors, separately from circuit faults.
- Every certified schedule's recovery of each enumerated single fault with the perfect final syndrome.
- Rejection of a bare ancilla, misplaced flag, missing data coupling, and decoder that ignores the flag.
- REINFORCE finite-difference gradients, checkpoint round trips, reproducibility, noise probability checks, and a Monte Carlo experiment with an exactly known two-location error probability.

The word *certified* always refers to these explicit conditions, not to universal fault tolerance.

## Baselines and split discipline

The evaluator compares:

1. The fixed reference `0F12F3`.
2. The best constant schedule selected using training contexts only.
3. Random search over 16 candidates.
4. A deterministic greedy pair-swap search using at most 16 candidate evaluations.
5. The learned policy: one selected schedule per context.
6. Exhaustive search over all 96 certified schedules.

The exhaustive oracle is the minimum **within this finite library**. It is not the optimum over all possible quantum circuits. All methods share the same offline catalog and risk model. The catalog itself enumerates all candidates; therefore online selection speed does not erase the offline enumeration cost. Training and evaluation costs are recorded separately.

Training, validation, test, and shifted-test contexts use distinct random seeds. Validation alone selects checkpoints. Test and shifted-test data are not used for fitting the model or selecting a checkpoint. The best constant baseline is fitted on training contexts, not on the test set. Smoke and full profiles also use distinct data seeds.

The shifted set has broader variation in both gate error rates and Pauli biases. Generalization means new synthetic calibrations for the same code and circuit family, not new codes or larger circuit architectures.

## Output files

Each run directory contains:

| File | Meaning |
|---|---|
| `summary.md` | Main results table and interpretation |
| `console.log` | Full saved console output |
| `pytest.txt` | Test-suite result |
| `verification.json` | Ideal/fault certificates and negative controls |
| `candidate_certificates.csv` | All 360 accepted/rejected candidate records |
| `reference_circuit.stim` | Plain circuit export for inspection; Stim is not required |
| `diagnosis.json` | Validation-only check that one fixed action does not already solve the task |
| `training_seed*.csv` | Training and validation progress |
| `policy_seed*.npz` | Saved best-validation model; no pickle required |
| `evaluation.json` | Held-out metrics, bootstrap intervals, and timing scopes |
| `evaluation.csv` | Per-context, per-method results |
| `noise.json` | Monte Carlo counts, Wilson intervals, and model probability bounds |
| `environment.json` | Python/package versions and source-code hashes |
| `config.json` | The exact configuration used |

`noise.json` uses one predeclared test context, not every context. Identical circuits share Monte Carlo samples to avoid interpreting sampling fluctuations as a difference between methods.

## Reference execution included

`reference_runs/smoke/` and `reference_runs/full/` contain actual completed runs from this workspace, using Python 3.13.5, NumPy 2.3.5, and pytest 9.0.2 on Linux CPU. Both pipelines, including training and noisy sampling, were executed. The Mac installation itself has not been tested here.

In the reference full run, learned policies beat the best fixed schedule and the included greedy/random baselines on the in-distribution mean C2. On shifted noise, 16-candidate random search had lower mean C2 than the learned policies. Exhaustive search was the best by construction. See the supplied records rather than assuming learning always wins.

These are pilot results on an authored synthetic benchmark. They are not a publication-level novelty claim or evidence of practical quantum advantage. At this small size, exhaustive evaluation is itself cheap. Read `RESEARCH_NEXT_STEPS.md` before extending the experiment.

## Run individual stages

To work stage by stage, use the same config and output path throughout:

```bash
python run_pipeline.py verify --config configs/full.json --out runs/manual
python run_pipeline.py diagnose --config configs/full.json --out runs/manual
python run_pipeline.py train --config configs/full.json --out runs/manual
python run_pipeline.py evaluate --config configs/full.json --out runs/manual
python run_pipeline.py noise --config configs/full.json --out runs/manual
python run_pipeline.py report --config configs/full.json --out runs/manual
```

Do not use `all` on that nonempty manual directory. Use the individual stages to continue a partial run. Training restarts from the configured seed; optimizer-state resume is not implemented. Evaluation/noise reject mismatched model/catalog/config combinations.

## Sources and attribution

This is original demonstration code based on established flag-circuit and RL ideas; it is not a reproduction of any paper's results or implementation.

- Chao and Reichardt, *Quantum Error Correction with Only Two Extra Qubits*, PRL 121, 050502 (2018): https://arxiv.org/abs/1705.02329 . Motivation and the flag-QEC framework.
- Zen et al., *Quantum Circuit Discovery for Fault-Tolerant Logical State Preparation with Reinforcement Learning*, PRX 15, 041012 (2025): https://arxiv.org/abs/2402.17761 . Related, larger-scale RL circuit-design research. Its task differs from this pilot.
- Python virtual environments: https://docs.python.org/3.13/library/venv.html .
- VS Code Python setup: https://code.visualstudio.com/docs/python/python-tutorial .
- VS Code environment selection: https://code.visualstudio.com/docs/python/environments .
