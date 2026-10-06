# FT compiler repair fork summary

Scope: exact single-fault counterexample detection, localization, and deterministic repair of compiler-introduced FT violations in the existing Steane/synthetic-hardware model.

Safety is lexicographic: a repair is accepted only if C1=0 with zero single-fault conflicts/failures and zero incoming-single-error failures.

## ood_mixed

### Routing/lowering repair

- Cases: 4
- Repair success: 100.0%
- Mean exact verifier calls: 3.00
- Mean changed checks on successful repairs: 1.00
- Injected check recovered among changed checks: 100.0%
- Mean initial SWAP C1: 40.8911
- Mean final C1: 0

### Parallel-schedule repair

- Cases: 4
- Repair success: 25.0%
- Mean precedence constraints added: 7.00
- Mean exact verifier calls: 8.75
- Repaired schedules retaining native-CX parallelism: 100.0%
- Mean repaired speedup vs serialized: 9.48%
- Mean repaired speedup vs safe ancilla-overlap fallback: 8.46%

## Aggregate

- Routing repair success: 100.0%
- Scheduling repair success: 25.0%
- Safe repaired schedules with true CX concurrency: 100.0%

## Interpretation constraints

- This is a deterministic counterexample-guided repair prototype, not an ML phase.
- The benchmark still uses the Steane code, the synthetic 12-node graph, and the existing Pauli/Clifford fault model.
- Routing repair cases are controlled compiler-choice injections: the logical circuit remains single-fault FT before physical lowering.
- Scheduling repair adds check-pair precedence constraints suggested by exact failing physical-fault witnesses.
- A successful repair demonstrates recovery of the modeled first-order FT guarantee; it does not establish general compiler completeness or device-level FT.
