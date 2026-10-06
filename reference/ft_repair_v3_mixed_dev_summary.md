# FT compiler repair v3 summary

Scope: operation-localized, richer-action counterexample-guided repair of compiler-introduced FT violations. V3 adds per-route path repair, operation-level precedence repair, verifier caching, and cross-layer routing/scheduling portfolio selection.

Safety remains lexicographic: only exact C1=0 with zero single-fault conflicts/failures and zero incoming-single-error failures is accepted.

## hw_id

### Multi-defect routing repair

- V3 success: 100.0% (1 cases)
- V2 success: n/a (0 cases)
- V3 mean exact verifier calls: 8.00
- V3 mean verifier-cache hits: 5.00
- Exact hidden changed-check recovery on V3 successes: 100.0%
- V3 success by hidden-defect count:
  - k=1: 100.0% (1 cases), mean calls 8.00

### Physical path-defect repair

- Cases: 0
- V3 success: n/a
- Mean witness-route recall on successes: n/a

### Parallel-schedule repair

- V3 portfolio success: n/a
- V3 pure operation-CEGIS success: n/a
- V2 pairwise portfolio success: n/a
- V3 mean exact calls: n/a
- V3 mean operation constraints on successes: n/a
- V3 safe repairs retaining true CX concurrency: n/a
- V3 mean retained speedup vs serial: n/a%
- V2 mean retained speedup vs serial: n/a%

### Mixed lowering + scheduling

- Staged V3 success: 100.0%
- Staged routing-stage success: 100.0%
- Staged scheduling-stage success: 100.0%
- Cross-layer portfolio success: 100.0%
- Cross-layer mean routing candidates evaluated: 1.00
- Cross-layer mean retained speedup: 7.85%

## Aggregate

- Routing V3 success: 100.0%
- Routing V2 success: n/a
- Path repair V3 success: n/a
- Schedule V3 success: n/a
- Schedule pure operation-CEGIS success: n/a
- Schedule V2 success: n/a
- Mixed staged V3 success: 100.0%
- Mixed cross-layer V3 success: 100.0%

## Interpretation constraints

- V3 still uses the Steane family and the fixed synthetic 12-node graph; this is not yet cross-code/cross-topology evidence.
- Operation-level precedence uses a bounded/global hitting-set heuristic when the atom universe is too large for exact subset enumeration; every proposed schedule is still accepted only after exact physical single-fault certification.
- Cross-layer V3 is a portfolio over multiple exactly certified routing repairs followed by exact schedule repair, not a monolithic joint SAT/SMT optimizer.
- Path alternatives remain bridge primitives of at most three hops on the existing graph.
- Verifier caching changes computational cost only; it never substitutes a heuristic score for the exact safety check.
