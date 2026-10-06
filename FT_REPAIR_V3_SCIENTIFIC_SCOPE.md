# FT Compiler Repair v3 Scientific Scope

## Research question

Can exact single-fault counterexamples from a physically compiled syndrome-extraction circuit be converted into sufficiently local compiler repair actions to restore first-order fault tolerance while preserving more routing/scheduling optimization than coarse whole-check repair?

## Hypotheses tested

### H1: physical witness localization is actionable below the check level

A failing native fault identifies a check, logical interaction, bridge gate, physical edge, Pauli outcome, observation, and residual logical class.  V3 tests whether route/gate-level localization can guide a repair without replacing an entire stabilizer check.

### H2: the repair language, not only localization, limits v2 routing success

V2 could change local template/hub choices.  V3 additionally allows a single physical bridge path to change.  If v3 repairs cases v2 cannot while witness localization remains accurate, this supports the claim that repair expressiveness was a genuine bottleneck.

### H3: whole-check pair precedence is overly conservative

V2 schedule repair can force the native-CX stream of check A before check B.  V3 can express precedence between individual physical operations.  The experiment measures whether this retains more safe concurrency/duration improvement.

### H4: downstream schedulability should influence lowering repair selection

Several serially safe lowerings may exist.  V3's cross-layer portfolio carries multiple exact-safe lowerings into schedule repair rather than choosing solely by the first serial repair found.

## Exact versus heuristic components

Exact/authoritative:

- Pauli propagation in the existing Clifford model;
- single native fault enumeration;
- decoder conflict/failure checks;
- incoming single-data-error checks;
- C1 evaluation;
- final acceptance/rejection of every repair.

Heuristic/proposal-only:

- physical route proxy;
- candidate path ordering;
- candidate template/hub ordering;
- large-universe greedy hitting-set fallback;
- cross-layer portfolio ranking.

The heuristic layer cannot mark an unsafe implementation as safe.

## Operation-level hitting-set caveat

With check-pair repair the universe contains only 15 atoms, so v2 can enumerate exact hitting sets.  Operation-level repair can expose more than 100 precedence atoms.  V3 therefore uses exact branch-and-bound only for small clause/atom sets and a deterministic weighted greedy cover for larger sets.  The resulting schedule is always exactly recertified.  The synthesis solution itself should not be described as globally minimum in the large-universe regime.

## Cross-layer caveat

The cross-layer method is a portfolio:

1. enumerate several exact-safe routing/lowering repairs;
2. repair scheduling for each candidate;
3. choose among exact-safe final implementations.

It is not a single joint SMT/SAT/ILP formulation over all routes, templates, hubs, and event times.  The staged pipeline remains a baseline.

## Controlled fault model

All prior limitations remain:

- Steane code only;
- fixed synthetic 12-node topology;
- Pauli/Clifford fault model;
- no leakage;
- no crosstalk;
- no pulse-level control;
- no named backend calibration;
- bridge paths are at most three hops;
- ideal memory boundaries where inherited from earlier phases.

## Development observations

These are implementation checks, not benchmark claims.

1. A deliberately unsafe alternative physical bridge path was found for a certified round.  Its initial C1 was approximately `0.779742`; v3 repaired it to `C1=0` by changing one physical route.  The hidden route appeared in the exact witness-route set.
2. On the deterministic schedule regression context, the robust v3 operation portfolio restored `C1=0`, retained `max_parallel_cx=2`, and retained a positive duration speedup.  Pure operation-CEGIS alone did not certify within the small development budget, so this remains an explicit ablation rather than being hidden.
3. A one-defect cross-layer development case produced multiple safe routing candidates with different downstream scheduling quality, validating the mechanics of portfolio selection.

These observations justify the standard benchmark but are not yet cross-family evidence.

## Criteria for continuing to topology generalization

The strongest reason to generalize would be a standard benchmark showing:

- routing repair substantially above v2, especially for k=2/3 hidden defects;
- high witness/check/route localization recall;
- path-defect repair with small edit sets;
- operation-level portfolio success at least comparable to v2 while retaining greater safe speedup or fewer coarse restrictions;
- mixed/cross-layer success clearly above the v2 staged result.

If those fail, the next work should improve repair expressiveness/search rather than adding another code or graph.
