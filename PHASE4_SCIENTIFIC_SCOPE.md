# Phase 4 scientific scope

## Research question

Phase 4 asks whether a **calibration-conditioned learned proposal policy** can guide a small, exact search toward lower-error flag-based syndrome-extraction schedules for the full Steane code more efficiently than equally budgeted random or simple deterministic search.

This is deliberately narrower than "RL discovers fault-tolerant circuits." A September 2026 paper, Ye, Pabla, and Palsberg, *Reinforcement Learning for Syndrome Extraction* (FastSched), already establishes reinforcement learning as a method for syndrome-extraction scheduling. Phase 4 therefore focuses on a different controlled question: **noise-adaptive flag architecture/template selection under a fixed exact-evaluation budget**.

FastSched: <https://arxiv.org/abs/2609.12020>

Flag-based error-correction background includes Chao and Reichardt's flag-qubit work and Reichardt's Steane-specific constructions:

- <https://arxiv.org/abs/1705.02329>
- <https://arxiv.org/abs/1804.06995>

## Circuit being modeled

One extraction round measures all six Steane stabilizer generators:

1. X0
2. X1
3. X2
4. Z0
5. Z1
6. Z2

The three support sets are

- `{0,1,2,3}`
- `{0,1,4,5}`
- `{0,2,4,6}`

for both X- and Z-type generators.

For a Z check, data/flag controls target a syndrome ancilla prepared in `|0>` and measured in Z. For an X check, the Hadamard-dual orientation is used: the syndrome ancilla is prepared in `|+>`, controls the data/flag targets, and is measured in X.

Checks are **serialized** in X0,X1,X2,Z0,Z1,Z2 order. Phase 4 does not optimize global timing or parallel scheduling.

## Local action table and synthesis space

The Phase-3 expanded catalog contains 4,896 certified local flag schedules. To keep the actor output tractable, Phase 4 deterministically prunes that catalog to 48 local actions using a fixed synthetic design bank that is separate from test contexts:

- 16 A-only templates
- 16 B-only templates
- 16 A+B templates

A complete Phase-4 schedule chooses one of these 48 templates for each of six checks:

`48^6 = 12,230,590,464`

possible full-round schedules.

The learner therefore cannot be evaluated by exhaustive search over the complete Phase-4 space.

## Noise model

Each check receives a 96-feature synthetic Pauli calibration with the same semantics as Phase 3:

- syndrome / flag preparation terms
- six possible local CNOT-edge types, each with 15 non-identity two-qubit Pauli outcomes
- syndrome / flag readout terms

A complete calibration has shape `(6,96)`.

Noise families deliberately vary flag-A quality, flag-B quality, flag cleanliness, check hot spots, data-edge hot spots, readout error, and Pauli composition.

These contexts are **synthetic stress tests**, not IBM/Google calibration records and not claims about a particular device.

Idle error, leakage, crosstalk, scheduling-induced decoherence, and physical connectivity are not included.

## Ideal boundaries and decoder

Phase 4 removes the Phase-3 "perfect final recovery oracle" as the operational decoder.

Instead, the modeled memory experiment has:

- an ideal initial code boundary;
- one noisy complete six-check extraction round;
- an ideal final syndrome boundary.

The final ideal boundary is analogous to the ideal boundaries commonly used in one-round memory experiments. It is not a seventh noisy stabilizer-extraction round.

For each synthesized schedule, Phase 4 builds an **explicit schedule-specific lookup decoder** from:

- the no-fault case;
- every single incoming one-qubit Pauli error;
- every single elementary circuit fault.

The decoder sees the noisy six-check record, flag outcomes, and ideal final syndrome. Observations not present in its single-fault table use the Steane minimum-weight correction associated with the final boundary syndrome.

This decoder is useful for a small controlled study, but it is not a scalable decoder such as PyMatching or BP-OSD.

## Fault-tolerance checks

The reference full round and tested schedules are required to have:

- zero single-fault observation conflicts;
- zero single-fault logical failures;
- zero failures on the 21 single incoming data Pauli errors.

The full-round C2 score is then computed from **malignant pairs of faults at distinct circuit locations**.

## C2 objective

For a fixed calibration weight vector `w`, the leading logical-failure term is modeled as

`p_L(p,w) = C2(w) p^2 + O(p^3)`

under the documented independent Pauli fault model and ideal-boundary experiment.

C2 is not itself a probability or a hardware logical error rate.

The finite-p Monte Carlo diagnostics separately estimate the logical failure probability for selected schedules.

## Learning method

The Phase-4 actor makes six sequential choices, one local template per stabilizer check.

Training has two stages:

1. **proxy pretraining** using the sum/relative improvement of the already verified local Phase-3 C2 costs;
2. **small exact fine-tuning** using the full-round C2 score.

The policy is primarily evaluated as a **proposal distribution** rather than as a one-shot greedy optimizer.

At deployment/evaluation:

- `policy_greedy` proposes one complete schedule and evaluates it once;
- `policy_beam` proposes a small beam of complete schedules without querying full-round C2 during expansion, then exactly evaluates the same number of complete schedules as the random-search baseline.

## Baselines

Phase 4 includes:

- a fixed reference round;
- a context-independent proxy-fixed round;
- local proxy-greedy selection;
- equal-budget random search;
- equal-budget coordinate search around the local-greedy schedule;
- policy greedy;
- equal-budget policy beam.

There is **no global exhaustive oracle** for the 12.2-billion-schedule space.

## What a positive result would support

A positive result would support the limited claim that a learned noise-conditioned proposal can concentrate a bounded exact search on useful regions of this structured flag-schedule space.

It would not establish:

- unrestricted circuit discovery;
- a quantum-hardware advantage;
- a better method than FastSched in its setting;
- a complete repeated fault-tolerant Steane QEC cycle;
- robustness to real calibration drift;
- superiority of RL over all optimization methods.
