"""Phase 6 experiment: validate Phase-5 surrogate rankings with explicit native faults."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import csv, json, time
import numpy as np

from .phase4_agent import RoundActorCritic
from .phase5_actions import ensure_hardware_action_table, actions_to_round
from .phase5_agent import beam_candidates
from .phase5_env import HardwareFeatureEncoder
from .phase5_experiment import HardwareProxyEvaluator, _random_candidates, _coordinate_candidates
from .phase5_hardware import hardware_round_metrics
from .phase5_noise import sample_hardware_contexts
from .phase6_native import explicit_native_risk, simulate_native_finite_p


def load_phase5_models(run_dir: Path, table, max_models: int | None = None):
    paths = sorted(run_dir.glob('phase5_policy_seed*.npz'))
    if max_models is not None:
        paths = paths[:int(max_models)]
    if not paths:
        raise FileNotFoundError(f'No phase5_policy_seed*.npz files found in {run_dir}')
    models, encoders, names = [], [], []
    for path in paths:
        with np.load(path, allow_pickle=False) as saved:
            model = RoundActorCritic(saved['w1'].shape[0], saved['ba'].shape[0], saved['w1'].shape[1])
            for key in model.params:
                model.params[key] = saved[key].copy()
            encoder = HardwareFeatureEncoder(table)
            encoder.mean = saved['feature_mean'].copy()
            encoder.scale = saved['feature_scale'].copy()
        models.append(model); encoders.append(encoder); names.append(path.stem.replace('phase5_policy_', ''))
    return models, encoders, names


def _surrogate(actions, table, context):
    labels, hubs = actions_to_round(actions, table)
    return hardware_round_metrics(labels, hubs, context)


def _rankdata(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    order = np.argsort(x, kind='mergesort')
    ranks = np.empty(len(x), dtype=np.float64)
    i = 0
    while i < len(x):
        j = i + 1
        while j < len(x) and x[order[j]] == x[order[i]]:
            j += 1
        ranks[order[i:j]] = 0.5 * (i + j - 1) + 1.0
        i = j
    return ranks


def _spearman(x, y) -> float:
    rx, ry = _rankdata(np.asarray(x)), _rankdata(np.asarray(y))
    if np.std(rx) == 0 or np.std(ry) == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def _select_candidates(project_root: Path, table, proxy, models, encoders,
                       batch, budget: int, rng: np.random.Generator):
    local_costs_all = proxy.all_costs(batch)
    local_rows = local_costs_all.argmin(axis=2)
    result = []
    for i in range(len(batch)):
        context = batch.context(i)
        methods = {
            'reference': tuple([proxy.reference_action] * 6),
            'local_greedy': tuple(int(x) for x in local_rows[i]),
        }
        rand_rows = _random_candidates(rng, table.n_actions, budget)
        rand_cost = [_surrogate(r, table, context).c2 for r in rand_rows]
        methods['random_search'] = rand_rows[int(np.argmin(rand_cost))]

        coord_rows = _coordinate_candidates(local_costs_all[i], local_rows[i].copy(), budget)
        coord_cost = [_surrogate(r, table, context).c2 for r in coord_rows]
        methods['coordinate_search'] = coord_rows[int(np.argmin(coord_cost))]

        for s, (model, encoder) in enumerate(zip(models, encoders)):
            rows = beam_candidates(model, encoder, context, budget)
            costs = [_surrogate(r, table, context).c2 for r in rows]
            methods[f'policy_beam_seed{s}'] = rows[int(np.argmin(costs))]
        result.append(methods)
    return result


def _method_summary(rows: list[dict], method: str, p_ref: float) -> dict:
    x = [r for r in rows if r['method'] == method]
    def arr(key): return np.asarray([r[key] for r in x], dtype=np.float64)
    score = arr('native_score')
    return {
        'cases': len(x),
        'mean_surrogate_c2': float(arr('surrogate_c2').mean()),
        'mean_native_c1': float(arr('native_c1').mean()),
        'median_native_c1': float(np.median(arr('native_c1'))),
        'mean_native_c2': float(arr('native_c2').mean()),
        'mean_native_score': float(score.mean()),
        'median_native_score': float(np.median(score)),
        'single_fault_ft_pass_fraction': float(arr('native_ft_pass').mean()),
        'mean_single_fault_failure_count': float(arr('single_fault_failures').mean()),
        'mean_native_cx': float(arr('native_cx').mean()),
        'mean_duration_us': float(arr('duration_ns').mean() / 1000.0),
        'p_ref': float(p_ref),
    }


def evaluate_native(project_root: Path, phase5_run: Path, config: dict, out_dir: Path) -> dict:
    table = ensure_hardware_action_table(project_root)
    proxy = HardwareProxyEvaluator.build(project_root, table)
    models, encoders, model_names = load_phase5_models(
        phase5_run, table, max_models=int(config.get('max_models', 3))
    )
    rng = np.random.default_rng(int(config['evaluation_seed']))
    budget = int(config['search_budget'])
    p_ref = float(config['p_ref'])
    pair_block = int(config.get('pair_block', 96))
    all_rows: list[dict] = []
    family_summaries = {}
    first_hw = None

    for fi, family in enumerate(config['families']):
        batch = sample_hardware_contexts(
            int(config['contexts_per_family']), int(config['test_seed']) + fi * 1000, family
        )
        selections = _select_candidates(project_root, table, proxy, models, encoders, batch, budget, rng)
        family_rows = []
        correlations = []
        winner_agreement = []
        for i in range(len(batch)):
            context = batch.context(i)
            methods = selections[i]
            local_context_rows = []
            print(f'P6 {family} context {i+1}/{len(batch)}: explicit native validation of {len(methods)} selected schedules')
            for method, actions in methods.items():
                labels, hubs = actions_to_round(actions, table)
                surrogate = hardware_round_metrics(labels, hubs, context)
                risk = explicit_native_risk(labels, hubs, context, pair_block=pair_block)
                native_score = risk.small_p(p_ref)
                row = {
                    'family': family, 'case': i, 'method': method,
                    'actions': list(actions), 'labels': list(labels), 'hubs': list(hubs),
                    'surrogate_c2': surrogate.c2,
                    'native_c1': risk.c1, 'native_c2': risk.c2,
                    'native_score': native_score,
                    'native_ft_pass': int(risk.fault_tolerant_single_fault),
                    'decoder_conflicts': risk.decoder.single_fault_conflicts,
                    'single_fault_failures': risk.decoder.single_fault_failures,
                    'incoming_failures': risk.decoder.incoming_failures,
                    'fault_outcomes': len(risk.records.data),
                    'physical_locations': int(len(np.unique(risk.records.location))),
                    'malignant_pair_count': risk.malignant_pair_count,
                    'native_cx': risk.plan.native_cx,
                    'duration_ns': risk.plan.duration_ns,
                }
                family_rows.append(row); all_rows.append(row); local_context_rows.append(row)
                if first_hw is None and family == 'hw_id':
                    first_hw = {'context': context, 'rows': {}}
                if first_hw is not None and family == 'hw_id' and i == 0:
                    first_hw['rows'][method] = (labels, hubs, risk)
            surrogate_values = [r['surrogate_c2'] for r in local_context_rows]
            native_values = [r['native_score'] for r in local_context_rows]
            correlations.append(_spearman(surrogate_values, native_values))
            winner_agreement.append(int(np.argmin(surrogate_values) == np.argmin(native_values)))

        methods = sorted({r['method'] for r in family_rows})
        summary = {m: _method_summary(family_rows, m, p_ref) for m in methods}
        policy_methods = [m for m in methods if m.startswith('policy_beam_seed')]
        # Per-context policy-seed mean, to match earlier phase reporting style.
        policy_scores = []
        for case in range(len(batch)):
            vals = [r['native_score'] for r in family_rows if r['case'] == case and r['method'] in policy_methods]
            policy_scores.append(float(np.mean(vals)))
        coord = np.asarray([r['native_score'] for r in family_rows if r['method'] == 'coordinate_search'])
        local = np.asarray([r['native_score'] for r in family_rows if r['method'] == 'local_greedy'])
        random = np.asarray([r['native_score'] for r in family_rows if r['method'] == 'random_search'])
        policy = np.asarray(policy_scores)
        summary['validation'] = {
            'mean_spearman_surrogate_vs_native_across_methods': float(np.mean(correlations)),
            'surrogate_native_winner_agreement_fraction': float(np.mean(winner_agreement)),
            'policy_seed_mean_vs_coordinate_win_fraction': float(np.mean(policy < coord)),
            'policy_seed_mean_vs_coordinate_mean_change_pct': float(100 * (policy.mean() / coord.mean() - 1)),
            'policy_seed_mean_vs_local_win_fraction': float(np.mean(policy < local)),
            'policy_seed_mean_vs_random_win_fraction': float(np.mean(policy < random)),
        }
        family_summaries[family] = summary
        print(f'P6 SUMMARY {family}: rank-r={summary["validation"]["mean_spearman_surrogate_vs_native_across_methods"]:.3f} winner-agree={summary["validation"]["surrogate_native_winner_agreement_fraction"]:.2f}')

    with (out_dir / 'phase6_cases.csv').open('w', newline='') as f:
        fields = [
            'family','case','method','surrogate_c2','native_c1','native_c2','native_score','native_ft_pass',
            'decoder_conflicts','single_fault_failures','incoming_failures','fault_outcomes','physical_locations',
            'malignant_pair_count','native_cx','duration_ns'
        ]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in all_rows:
            w.writerow({k: r[k] for k in fields})
    return {
        'families': family_summaries,
        'rows': all_rows,
        'model_names': model_names,
        'first_hw': first_hw,
    }


def finite_p_diagnostics(selected, config: dict) -> list[dict]:
    if selected is None:
        return []
    wanted = ['reference', 'local_greedy', 'coordinate_search', 'policy_beam_seed0']
    rows = []
    for method in wanted:
        if method not in selected['rows']:
            continue
        labels, hubs, risk = selected['rows'][method]
        for p in config['noise_p']:
            r = simulate_native_finite_p(
                risk, float(p), int(config['noise_shots']), int(config['noise_seed']) + len(rows)
            )
            r.update({'method': method, 'labels': list(labels), 'hubs': list(hubs)})
            rows.append(r)
            print(f'P6 NOISE {method} p={p}: {r["failures"]}/{r["shots"]}')
    return rows


def _markdown(payload: dict) -> str:
    cfg = payload['config']
    lines = [
        '# Phase 6 summary','',
        'Scope: explicit native-routed-CNOT fault validation of schedules selected by the Phase-5 hardware-aware search pipeline.','',
        'Every routed SWAP is expanded into native CNOTs and every native CNOT receives its own 15-outcome Pauli fault location. Data idle faults are explicit at route boundaries. Lower native small-p score is better.','',
        f'- Validation reference p: {cfg["p_ref"]}; native score = p*C1 + p^2*C2.',
        f'- Phase-5 bounded-search budget used to select candidates before native validation: {cfg["search_budget"]}.',
        '- Phase 6 does not retrain the policy; it validates schedules proposed by saved Phase-5 models.','',
    ]
    for family, summary in payload['evaluation']['families'].items():
        lines += [f'## {family}','',
                  '| Method | Surrogate C2 | Native C1 | Native C2 | Native small-p score | Single-fault FT pass | Native CX | Duration (us) |',
                  '|---|---:|---:|---:|---:|---:|---:|---:|']
        methods = [m for m in summary if m != 'validation']
        order = ['reference','local_greedy','random_search','coordinate_search'] + sorted([m for m in methods if m.startswith('policy_beam_seed')])
        for m in order:
            if m not in summary: continue
            r = summary[m]
            lines.append(
                f'| {m} | {r["mean_surrogate_c2"]:.6f} | {r["mean_native_c1"]:.6f} | {r["mean_native_c2"]:.6f} | '
                f'{r["mean_native_score"]:.8f} | {100*r["single_fault_ft_pass_fraction"]:.1f}% | {r["mean_native_cx"]:.1f} | {r["mean_duration_us"]:.3f} |'
            )
        v = summary['validation']
        lines += ['',
                  f'- Mean within-context Spearman rank correlation, surrogate C2 vs explicit native score: {v["mean_spearman_surrogate_vs_native_across_methods"]:.3f}.',
                  f'- Surrogate and native models select the same best listed method in {100*v["surrogate_native_winner_agreement_fraction"]:.1f}% of contexts.',
                  f'- Policy-seed mean vs coordinate: win fraction {100*v["policy_seed_mean_vs_coordinate_win_fraction"]:.1f}%; mean native-score change {v["policy_seed_mean_vs_coordinate_mean_change_pct"]:.2f}%.',
                  f'- Policy-seed mean vs local greedy: win fraction {100*v["policy_seed_mean_vs_local_win_fraction"]:.1f}%.',
                  f'- Policy-seed mean vs random search: win fraction {100*v["policy_seed_mean_vs_random_win_fraction"]:.1f}%.','']
    lines += ['## Explicit finite-p native diagnostics','',
              'These use the first fresh `hw_id` validation context. Faults are sampled directly at native CNOT, preparation/readout, and route-boundary idle locations.','',
              '| Method | p | failures/shots | logical failure rate | 95% interval | C1 | C2 |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for r in payload['noise']:
        lines.append(f'| {r["method"]} | {r["p"]} | {r["failures"]}/{r["shots"]} | {r["logical_failure_rate"]:.7f} | [{r["wilson95_low"]:.7f}, {r["wilson95_high"]:.7f}] | {r["c1"]:.6f} | {r["c2"]:.6f} |')
    lines += ['', '## Interpretation constraints','',
              '- The hardware graph and calibration families remain synthetic; this is not a named device calibration.',
              '- Routing CNOT faults are now propagated gate by gate. This is the main Phase-6 upgrade over Phase 5.',
              '- Idle faults are explicit once per route boundary for nonparticipating persistent data qubits, but continuous-time idling during each individual native sub-gate is still approximated.',
              '- The native two-qubit Pauli channel on each routed CNOT reuses the corresponding logical-interaction 15-outcome profile, scaled by the physical-edge multiplier.',
              '- The schedule-specific decoder still uses the noisy extraction record plus an ideal final memory-boundary syndrome.',
              '- Any nonzero native C1 or failure of the single-fault checks means the routed implementation is not first-order fault tolerant under this model; C2 alone must not then be treated as the leading logical-failure term.',
              '- Phase 6 is a validation study, not a new RL training phase.','']
    return '\n'.join(lines)


def run_all(project_root: Path, phase5_run: Path, config: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    evaluation = evaluate_native(project_root, phase5_run, config, out_dir)
    selected = evaluation.pop('first_hw')
    noise = finite_p_diagnostics(selected, config)
    payload = {
        'config': config,
        'phase5_run': str(phase5_run),
        'evaluation': {'families': evaluation['families'], 'model_names': evaluation['model_names']},
        'noise': noise,
        'elapsed_seconds': time.perf_counter() - start,
    }
    (out_dir / 'phase6_results.json').write_text(json.dumps(payload, indent=2) + '\n')
    (out_dir / 'phase6_summary.md').write_text(_markdown(payload) + '\n')
    print(f'PHASE 6 REPORT: {out_dir / "phase6_summary.md"}')
    return payload
