# Interpreting the pilot without repeating the QRAM mistake

## What the current deliverable establishes

The implementation supplies an auditable finite circuit family, ideal instrument tests, single-fault checks, full stabilizer-coset recovery checks, an exact small-instance objective, a learning algorithm with gradient tests, multiple classical baselines, independent train/validation/test splits, shifted-noise testing, Monte Carlo diagnostics, and saved provenance.

The authored benchmark has context-dependent choices: one constant circuit does not already solve all calibration cases. That was the first issue missing in the previous QRAM experiment.

The full reference run found that the learned models improve on the included best-fixed, greedy, and random baselines in the in-distribution mean C2. Under the shifted distribution, random search had lower mean C2. The exhaustive finite-library oracle wins by definition and remains inexpensive at this size. These findings should be described exactly at that level.

## Claims not supported

- Discovery of a new quantum error-correcting code.
- Discovery of the flag paradigm or a previously unknown flag circuit.
- Unrestricted circuit synthesis or sequential circuit discovery.
- A fully fault-tolerant noisy syndrome-extraction/recovery protocol.
- Generalization to larger codes, more qubits, or another connectivity graph.
- A useful hardware speedup, lower physical-qubit overhead, a higher threshold, or practical quantum advantage.
- A novel research contribution established merely by running this bundle.

## What a stronger follow-on would need

Choose one extension deliberately after reviewing the results and relevant literature with an advisor. Do not add every extension at once.

1. **A complete noisy protocol.** Specify all Steane stabilizer measurements, repeated/adaptive extraction, flag-conditioned control flow, and the recovery decoder. Include faults in every recovery and waiting operation. Replace the perfect final syndrome assumption with an implemented protocol. Repeat exhaustive one-fault correctness tests where tractable.

2. **Hardware constraints.** Start from an explicit permitted interaction graph and instruction durations. Insert actual routing gates, include their faults and idle noise, and re-certify the physical circuit. A graph restriction without checking added gates is not hardware-aware fault tolerance.

3. **A larger design space with a genuine decision problem.** More generators, code sizes, verification ancillas, or sequential gate construction may justify different optimization methods. Keep exact or lower-bound oracles for small cases. The existence of a larger space is not itself a proof that learning is useful.

4. **More competitive decision baselines.** Include analytic or interpretable calibration-aware ordering rules, stronger local search, and exact evaluation whenever it is affordable. The current finite library has a known quadratic objective, so direct evaluation is a particularly important competitor.

5. **A preregistered final test.** The supplied test sets and reference results are now visible. For a final study, select new untouched test seeds or externally specified calibration datasets before tuning extensions. Track method-development time, training evaluations, and total online cost, not just final circuit quality.

A course deliverable can already report a rigorous controlled pilot. A research paper would need a more consequential task, a precise literature gap, and independent comparisons. No future step guarantees a positive learning result.
