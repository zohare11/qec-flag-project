# FT compiler repair v2 summary

Scope: multi-defect counterexample-guided repair of compiler-introduced fault-tolerance violations in the Steane/synthetic-hardware model.

V2 adds multi-defect lowering cases, exact minimum-hitting-set scheduling repair, and mixed lowering+scheduling repair. Safety remains lexicographic: no optimization objective can override C1=0 and the exact single-fault checks.

## ood_edge_hotspot

### Multi-defect routing CEGIS

- Cases: 6
- Repair success: 66.7%
- Mean exact verifier calls: 26.67
- Mean changed checks on successes: 1.50
- Hidden injected-check recall: 100.0%
- Hidden injected-check precision: 100.0%
- Exact hidden defect-set recovery: 100.0%

### Routing v1 baseline

- Cases: 6
- Repair success: 33.3%
- Mean exact verifier calls: 43.67
- Mean changed checks on successes: 1.00

### V2 schedule portfolio

- Cases: 4
- Repair success: 100.0%
- Mean exact verifier calls: 19.25
- Mean precedence constraints on successes: 4.75
- Successful repairs retaining true CX parallelism: 50.0%
- Mean retained speedup vs serialized: 8.79%

### Pure hitting-set ablation

- Cases: 4
- Repair success: 50.0%
- Mean exact verifier calls: 4.75
- Mean precedence constraints on successes: 9.00
- Successful repairs retaining true CX parallelism: 0.0%
- Mean retained speedup vs serialized: 1.21%

### Witness-greedy schedule v1

- Cases: 4
- Repair success: 100.0%
- Mean exact verifier calls: 9.50
- Mean precedence constraints on successes: 8.50
- Successful repairs retaining true CX parallelism: 50.0%
- Mean retained speedup vs serialized: 5.85%

### Mixed lowering + scheduling v2

- Cases: 2
- Repair success: 50.0%
- Mean total exact verifier calls: 23.00
- Successful repairs retaining true CX parallelism: 100.0%
- Mean retained speedup vs serialized: 9.73%

## Aggregate

- V2 routing success: 66.7%
- V1 routing success: 33.3%
- V2 scheduling portfolio success: 100.0%
- Pure hitting-set scheduling success: 50.0%
- V1 scheduling success: 100.0%
- V2 mixed-repair success: 50.0%

## Interpretation constraints

- This benchmark still uses one Steane-code family and one fixed 12-node physical graph; it is not yet a cross-code/cross-topology generalization result.
- Multi-defect cases are controlled compiler mutations whose hidden locations are used only for evaluation, not by the repair algorithms.
- The hitting-set solver reasons globally over accumulated physical-fault counterexamples, but pairwise check-precedence constraints are still a restricted repair language.
- Exact single-fault certification remains authoritative; proxy costs are only used to order safe-search candidates.
- Mixed repair is staged (lowering repair, then scheduling repair), not a complete joint optimizer.
