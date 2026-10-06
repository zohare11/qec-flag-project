# FT compiler repair v2 summary

Scope: multi-defect counterexample-guided repair of compiler-introduced fault-tolerance violations in the Steane/synthetic-hardware model.

V2 adds multi-defect lowering cases, exact minimum-hitting-set scheduling repair, and mixed lowering+scheduling repair. Safety remains lexicographic: no optimization objective can override C1=0 and the exact single-fault checks.

## hw_id

### Multi-defect routing CEGIS

- Cases: 1
- Repair success: 100.0%
- Mean exact verifier calls: 2.00
- Mean changed checks on successes: 1.00
- Hidden injected-check recall: 100.0%
- Hidden injected-check precision: 100.0%
- Exact hidden defect-set recovery: 100.0%

### Routing v1 baseline

- Cases: 1
- Repair success: 100.0%
- Mean exact verifier calls: 3.00
- Mean changed checks on successes: 1.00

### V2 schedule portfolio

- Cases: 1
- Repair success: 100.0%
- Mean exact verifier calls: 22.00
- Mean precedence constraints on successes: 4.00
- Successful repairs retaining true CX parallelism: 100.0%
- Mean retained speedup vs serialized: 16.23%

### Pure hitting-set ablation

- Cases: 1
- Repair success: 0.0%
- Mean exact verifier calls: 3.00
- Mean precedence constraints on successes: nan
- Successful repairs retaining true CX parallelism: nan%
- Mean retained speedup vs serialized: nan%

### Witness-greedy schedule v1

- Cases: 1
- Repair success: 100.0%
- Mean exact verifier calls: 9.00
- Mean precedence constraints on successes: 8.00
- Successful repairs retaining true CX parallelism: 100.0%
- Mean retained speedup vs serialized: 11.67%

### Mixed lowering + scheduling v2

- Cases: 0
- Repair success: nan%
- Mean total exact verifier calls: nan
- Successful repairs retaining true CX parallelism: nan%
- Mean retained speedup vs serialized: nan%

## Aggregate

- V2 routing success: 100.0%
- V1 routing success: 100.0%
- V2 scheduling portfolio success: 100.0%
- Pure hitting-set scheduling success: 0.0%
- V1 scheduling success: 100.0%
- V2 mixed-repair success: nan%

## Interpretation constraints

- This benchmark still uses one Steane-code family and one fixed 12-node physical graph; it is not yet a cross-code/cross-topology generalization result.
- Multi-defect cases are controlled compiler mutations whose hidden locations are used only for evaluation, not by the repair algorithms.
- The hitting-set solver reasons globally over accumulated physical-fault counterexamples, but pairwise check-precedence constraints are still a restricted repair language.
- Exact single-fault certification remains authoritative; proxy costs are only used to order safe-search candidates.
- Mixed repair is staged (lowering repair, then scheduling repair), not a complete joint optimizer.
