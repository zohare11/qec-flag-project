"""Phase-7 experiment: forensic diagnosis + certified physical routing."""
from __future__ import annotations

from pathlib import Path
import csv, json, time
import numpy as np

from .phase5_actions import ensure_hardware_action_table, actions_to_round
from .phase5_noise import sample_hardware_contexts
from .phase6_native import explicit_native_risk, simulate_native_finite_p
from .phase7_catalog import ensure_catalog
from .phase7_forensics import forensic_comparison
from .phase7_routing import bridge_native_risk, bridge_proxy_metrics


def _method_row(family: str, context_index: int, method: str, risk, p_ref: float,
                evaluated: int) -> dict:
    return {
        'family': family, 'context_index': int(context_index), 'method': method,
        'c1': float(risk.c1), 'c2': float(risk.c2),
        'small_p_score': float(risk.small_p(p_ref)),
        'ft_pass': bool(risk.fault_tolerant_single_fault),
        'single_fault_conflicts': int(risk.decoder.single_fault_conflicts),
        'single_fault_failures': int(risk.decoder.single_fault_failures),
        'incoming_failures': int(risk.decoder.incoming_failures),
        'native_cx': int(risk.plan.native_cx),
        'duration_us': float(risk.plan.duration_ns / 1000.0),
        'exact_native_evaluations': int(evaluated),
        'labels': '|'.join(risk.plan.labels),
        'hubs': ''.join(str(x) for x in risk.plan.hubs),
    }


def _best_exact(candidates, context, p_ref: float, pair_block: int, cache=None):
    best = None
    cache = {} if cache is None else cache
    for idx in candidates:
        labels, hubs = idx
        key_id = (tuple(labels), tuple(hubs))
        risk = cache.get(key_id)
        if risk is None:
            risk = bridge_native_risk(labels, hubs, context, pair_block=pair_block)
            cache[key_id] = risk
        key = (not risk.fault_tolerant_single_fault, risk.c1, risk.small_p(p_ref), risk.c2,
               risk.plan.native_cx, risk.plan.duration_ns, labels, hubs)
        if best is None or key < best[0]:
            best = (key, risk)
    return best[1]


def _catalog_rounds(catalog):
    return [catalog.labels_hubs(i) for i in range(len(catalog))]


def _choose_fixed(catalog, train_contexts) -> tuple[tuple[str, ...], tuple[int, ...]]:
    rounds = _catalog_rounds(catalog)
    scores = np.zeros(len(rounds), dtype=np.float64)
    for i, (labels, hubs) in enumerate(rounds):
        scores[i] = np.mean([bridge_proxy_metrics(labels, hubs, c).c2 for c in train_contexts])
    return rounds[int(np.argmin(scores))]


def _proxy_candidates(catalog, context, budget: int):
    scored = []
    for i in range(len(catalog)):
        labels, hubs = catalog.labels_hubs(i)
        m = bridge_proxy_metrics(labels, hubs, context)
        scored.append((m.c2, m.native_cx, m.duration_ns, i))
    scored.sort()
    return [catalog.labels_hubs(i) for *_rest, i in scored[:int(budget)]]


def _random_candidates(catalog, budget: int, rng: np.random.Generator):
    k = min(int(budget), len(catalog))
    idx = rng.choice(len(catalog), size=k, replace=False)
    return [catalog.labels_hubs(int(i)) for i in idx]


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text('')
        return
    keys = list(rows[0])
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader(); w.writerows(rows)


def _aggregate(rows: list[dict]) -> dict:
    out = {}
    families = sorted({r['family'] for r in rows})
    for fam in families:
        out[fam] = {}
        methods = sorted({r['method'] for r in rows if r['family'] == fam})
        for method in methods:
            rr = [r for r in rows if r['family'] == fam and r['method'] == method]
            out[fam][method] = {
                'mean_c1': float(np.mean([r['c1'] for r in rr])),
                'mean_c2': float(np.mean([r['c2'] for r in rr])),
                'mean_small_p_score': float(np.mean([r['small_p_score'] for r in rr])),
                'ft_pass_fraction': float(np.mean([r['ft_pass'] for r in rr])),
                'mean_native_cx': float(np.mean([r['native_cx'] for r in rr])),
                'mean_duration_us': float(np.mean([r['duration_us'] for r in rr])),
                'mean_exact_evaluations': float(np.mean([r['exact_native_evaluations'] for r in rr])),
            }
    return out


def _markdown(summary: dict, out_dir: Path) -> str:
    lines = ['# Phase 7 summary', '',
             'Scope: exact first-order fault forensics plus single-fault-certified nearest-neighbour bridge routing on the same synthetic 12-node graph.', '',
             'The routing primitive is not assumed safe. Complete routed rounds enter the certified catalog only after exhaustive single-native-fault and incoming-single-data-error checks.', '',
             f"- Certified catalog size: {summary['catalog']['catalog_size']}",
             f"- Certified homogeneous rounds: {summary['catalog']['certified_homogeneous']}",
             f"- Validation p: {summary['config']['p_ref']}",
             f"- Exact evaluation budget for proxy/random certified search: {summary['config']['search_budget']}", '',
             '## Phase 7A forensic result', '']
    f = summary['forensics']
    logical = f['logical_unrouted_control']
    swap = f['swap_restore']; bridge = f['bridge_same_logical_schedule']
    lines += [
        f"- Unrouted logical control: conflicts={logical['single_fault_conflicts']}, single-fault logical failures={logical['single_fault_logical_failures']}, incoming failures={logical['single_incoming_error_failures']}.",
        f"- Naive SWAP routing: C1={swap['c1']:.6f}, single-fault failures={swap['single_fault_failures']}, conflicts={swap['conflicts']}.",
        f"- Same logical schedule with bridge routing: C1={bridge['c1']:.6f}, single-fault failures={bridge['single_fault_failures']}, conflicts={bridge['conflicts']}.",
        f"- Naive SWAP failing-fault stages: {swap['failure_summary']['by_stage']}.", '',
        '## Phase 7B certified routing', ''
    ]
    for family, methods in summary['aggregate'].items():
        lines += [f'### {family}', '',
                  '| Method | Mean C1 | Mean C2 | Mean small-p score | FT pass | Mean native CX | Mean duration (us) | Exact evals/context |',
                  '|---|---:|---:|---:|---:|---:|---:|---:|']
        order = ['naive_swap_reference', 'bridge_same_reference', 'certified_fixed', 'certified_random_search', 'certified_proxy_search']
        for method in order:
            if method not in methods: continue
            x = methods[method]
            lines.append(f"| {method} | {x['mean_c1']:.6f} | {x['mean_c2']:.6f} | {x['mean_small_p_score']:.8f} | {100*x['ft_pass_fraction']:.1f}% | {x['mean_native_cx']:.1f} | {x['mean_duration_us']:.3f} | {x['mean_exact_evaluations']:.1f} |")
        lines.append('')
    if summary.get('finite_p'):
        lines += ['## Explicit finite-p diagnostics', '',
                  '| Method | p | failures/shots | logical failure rate | 95% interval | C1 | C2 |',
                  '|---|---:|---:|---:|---:|---:|---:|']
        for r in summary['finite_p']:
            lines.append(f"| {r['method']} | {r['p']} | {r['failures']}/{r['shots']} | {r['logical_failure_rate']:.7f} | [{r['wilson95_low']:.7f}, {r['wilson95_high']:.7f}] | {r['c1']:.6f} | {r['c2']:.6f} |")
        lines.append('')
    lines += ['## Interpretation constraints', '',
              '- Phase 7 uses a bridge-CNOT primitive along deterministic paths that prefer no interior data qubits; the primitive itself is not declared fault tolerant.',
              '- Fault tolerance is enforced at the complete routed-round level: catalog entries require C1=0, zero single-fault decoder conflicts/failures, and zero incoming-single-error failures.',
              '- The certified catalog is a deliberately small structured family, not an exhaustive search over all physical circuits.',
              '- The 12-node graph and calibration families remain synthetic.',
              '- Native CNOT faults are explicit. Data idle faults remain discretized at route boundaries rather than continuously scheduled per sub-gate.',
              '- This is one serialized Steane extraction round with an ideal final memory boundary, not repeated fault-tolerant memory.', '']
    return '\n'.join(lines)


def run_all(project_root: Path, cfg: dict, out_dir: Path) -> dict:
    t0 = time.time(); project_root = Path(project_root); out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    table = ensure_hardware_action_table(project_root)
    catalog = ensure_catalog(project_root, progress=True)

    p_ref = float(cfg.get('p_ref', 2e-4)); pair_block = int(cfg.get('pair_block', 128))
    budget = int(cfg.get('search_budget', 4)); nctx = int(cfg.get('contexts_per_family', 1))
    families = list(cfg.get('families', ['hw_id']))
    seed = int(cfg.get('evaluation_seed', 7201)); rng = np.random.default_rng(seed + 991)

    ref_action = table.index('H0|0A12A3')
    if ref_action is None: raise RuntimeError('Reference hardware action missing')
    ref_labels, ref_hubs = actions_to_round((ref_action,) * 6, table)
    forensic_context = sample_hardware_contexts(1, seed + 1, 'hw_id').context(0)
    forensics = forensic_comparison(ref_labels, ref_hubs, forensic_context, pair_block=pair_block)
    (out_dir / 'phase7_forensics.json').write_text(json.dumps(forensics, indent=2) + '\n')
    forensic_rows = []
    for router, key in [('swap_restore', 'swap_restore'), ('bridge', 'bridge_same_logical_schedule')]:
        for row in forensics[key]['failures']:
            rr = dict(row); rr['router'] = router; forensic_rows.append(rr)
    _write_csv(out_dir / 'phase7_failing_faults.csv', forensic_rows)

    ntrain = int(cfg.get('fixed_train_contexts', 4))
    train_batch = sample_hardware_contexts(ntrain, seed + 2, 'hw_train')
    fixed = _choose_fixed(catalog, [train_batch.context(i) for i in range(ntrain)])

    rows: list[dict] = []
    first_hw = None; first_proxy_risk = None; first_random_risk = None
    for fi, family in enumerate(families):
        batch = sample_hardware_contexts(nctx, seed + 100 * fi + 10, family)
        for i in range(nctx):
            context = batch.context(i)
            if first_hw is None and family == 'hw_id': first_hw = context
            naive = explicit_native_risk(ref_labels, ref_hubs, context, pair_block=pair_block)
            bridge_ref = bridge_native_risk(ref_labels, ref_hubs, context, pair_block=pair_block)
            bridge_cache = {}
            fixed_key = (tuple(fixed[0]), tuple(fixed[1]))
            fixed_risk = bridge_native_risk(fixed[0], fixed[1], context, pair_block=pair_block)
            bridge_cache[fixed_key] = fixed_risk
            proxy_candidates = _proxy_candidates(catalog, context, budget)
            random_candidates = _random_candidates(catalog, budget, rng)
            proxy_risk = _best_exact(proxy_candidates, context, p_ref, pair_block, cache=bridge_cache)
            random_risk = _best_exact(random_candidates, context, p_ref, pair_block, cache=bridge_cache)
            if first_proxy_risk is None and family == 'hw_id':
                first_proxy_risk = proxy_risk; first_random_risk = random_risk
            rows += [
                _method_row(family, i, 'naive_swap_reference', naive, p_ref, 1),
                _method_row(family, i, 'bridge_same_reference', bridge_ref, p_ref, 1),
                _method_row(family, i, 'certified_fixed', fixed_risk, p_ref, 1),
                _method_row(family, i, 'certified_random_search', random_risk, p_ref, min(budget, len(catalog))),
                _method_row(family, i, 'certified_proxy_search', proxy_risk, p_ref, min(budget, len(catalog))),
            ]
            print(f'P7 EVAL {family} {i+1}/{nctx}: proxy_C2={proxy_risk.c2:.6g} random_C2={random_risk.c2:.6g}')

    _write_csv(out_dir / 'phase7_evaluation.csv', rows)
    aggregate = _aggregate(rows)

    finite = []
    if first_hw is not None and first_proxy_risk is not None:
        noise_ps = [float(x) for x in cfg.get('noise_p', [])]
        shots = int(cfg.get('noise_shots', 0)); noise_seed = int(cfg.get('noise_seed', seed + 700))
        if shots > 0:
            risks = {
                'naive_swap_reference': explicit_native_risk(ref_labels, ref_hubs, first_hw, pair_block=pair_block),
                'certified_proxy_search': first_proxy_risk,
                'certified_random_search': first_random_risk,
            }
            for mi, (name, risk) in enumerate(risks.items()):
                for pi, p in enumerate(noise_ps):
                    r = simulate_native_finite_p(risk, p, shots, noise_seed + 100 * mi + pi)
                    r['method'] = name; finite.append(r)

    payload = {
        'config': cfg,
        'catalog': catalog.metadata,
        'fixed_round': {'labels': list(fixed[0]), 'hubs': list(fixed[1])},
        'forensics': forensics,
        'aggregate': aggregate,
        'finite_p': finite,
        'elapsed_seconds': time.time() - t0,
    }
    (out_dir / 'phase7_results.json').write_text(json.dumps(payload, indent=2) + '\n')
    md = _markdown(payload, out_dir)
    (out_dir / 'phase7_summary.md').write_text(md + '\n')
    print(f'PHASE 7 REPORT: {out_dir / "phase7_summary.md"}')
    return payload
