# FT compiler repair fork summary

Scope: exact single-fault counterexample detection, localization, and deterministic repair of compiler-introduced FT violations in the existing Steane/synthetic-hardware model.

Safety is lexicographic: a repair is accepted only if C1=0 with zero single-fault conflicts/failures and zero incoming-single-error failures.

## ood_hub1_bad

### Routing/lowering repair

- Cases: 4
- Repair success: 100.0%
- Mean exact verifier calls: 3.00
- Mean changed checks on successful repairs: 1.00
- Injected check recovered among changed checks: 100.0%
- Mean initial SWAP C1: 59.2918
- Mean final C1: 0

### Parallel-schedule repair

- Cases: 4
- Repair success: 0.0%
- Mean precedence constraints added: nan
- Mean exact verifier calls: 9.50
- Repaired schedules retaining native-CX parallelism: nan%
- Mean repaired speedup vs serialized: nan%
- Mean repaired speedup vs safe ancilla-overlap fallback: nan%

## Aggregate

- Routing repair success: 100.0%
- Scheduling repair success: 0.0%
- Safe repaired schedules with true CX concurrency: nan%

## Interpretation constraints

- This is a deterministic counterexample-guided repair prototype, not an ML phase.
- The benchmark still uses the Steane code, the synthetic 12-node graph, and the existing Pauli/Clifford fault model.
- Routing repair cases are controlled compiler-choice injections: the logical circuit remains single-fault FT before physical lowering.
- Scheduling repair adds check-pair precedence constraints suggested by exact failing physical-fault witnesses.
- A successful repair demonstrates recovery of the modeled first-order FT guarantee; it does not establish general compiler completeness or device-level FT.
