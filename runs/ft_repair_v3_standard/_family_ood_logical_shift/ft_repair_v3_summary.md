# FT compiler repair v3 summary

Scope: operation-localized, richer-action counterexample-guided repair of compiler-introduced FT violations. V3 adds per-route path repair, operation-level precedence repair, verifier caching, and cross-layer routing/scheduling portfolio selection.

Safety remains lexicographic: only exact C1=0 with zero single-fault conflicts/failures and zero incoming-single-error failures is accepted.

## ood_logical_shift

### Multi-defect routing repair

- V3 success: 66.7% (3 cases)
- V2 success: 66.7% (3 cases)
- V3 mean exact verifier calls: 41.00
- V3 mean verifier-cache hits: 19.67
- Exact hidden changed-check recovery on V3 successes: 100.0%
- V3 success by hidden-defect count:
  - k=1: 100.0% (1 cases), mean calls 11.00
  - k=2: 100.0% (1 cases), mean calls 56.00
  - k=3: 0.0% (1 cases), mean calls 56.00

### Physical path-defect repair

- Cases: 1
- V3 success: 100.0%
- Mean witness-route recall on successes: 100.0%

### Parallel-schedule repair

- V3 portfolio success: 100.0%
- V3 pure operation-CEGIS success: 0.0%
- V2 pairwise portfolio success: 0.0%
- V3 mean exact calls: 13.00
- V3 mean operation constraints on successes: 5.00
- V3 safe repairs retaining true CX concurrency: 0.0%
- V3 mean retained speedup vs serial: 0.00%
- V2 mean retained speedup vs serial: n/a%

### Mixed lowering + scheduling

- Staged V3 success: 100.0%
- Staged routing-stage success: 100.0%
- Staged scheduling-stage success: 100.0%
- Cross-layer portfolio success: 100.0%
- Cross-layer mean routing candidates evaluated: 3.00
- Cross-layer mean retained speedup: 0.00%

## Aggregate

- Routing V3 success: 66.7%
- Routing V2 success: 66.7%
- Path repair V3 success: 100.0%
- Schedule V3 success: 100.0%
- Schedule pure operation-CEGIS success: 0.0%
- Schedule V2 success: 0.0%
- Mixed staged V3 success: 100.0%
- Mixed cross-layer V3 success: 100.0%

## Interpretation constraints

- V3 still uses the Steane family and the fixed synthetic 12-node graph; this is not yet cross-code/cross-topology evidence.
- Operation-level precedence uses a bounded/global hitting-set heuristic when the atom universe is too large for exact subset enumeration; every proposed schedule is still accepted only after exact physical single-fault certification.
- Cross-layer V3 is a portfolio over multiple exactly certified routing repairs followed by exact schedule repair, not a monolithic joint SAT/SMT optimizer.
- Path alternatives remain bridge primitives of at most three hops on the existing graph.
- Verifier caching changes computational cost only; it never substitutes a heuristic score for the exact safety check.
