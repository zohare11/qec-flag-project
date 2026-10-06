"""Phase 2: compare learning paradigms and robustness under synthetic noise shift."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import csv
import hashlib
import json
import time
import numpy as np
from .agent import Policy, Adam
from .catalog import Catalog, greedy_choice
from .phase2_models import Classifier, CostRegressor, oracle_soft_targets, relative_log_cost_targets
from .phase2_noise import sample_family, validate_batch


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError('Cannot write empty CSV')
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def stable_seed(base: int, tag: str) -> int:
    digest = hashlib.sha256(f'{base}:{tag}'.encode()).digest()
    return int.from_bytes(digest[:4], 'little')


def training_family(regime: str) -> str:
    if regime == 'narrow':
        return 'narrow'
    if regime == 'domain_randomized':
        return 'domain_randomized'
    raise ValueError(f'Unknown training regime {regime!r}')


def make_datasets(config: dict, regime: str) -> dict[str, np.ndarray]:
    family = training_family(regime)
    base = int(config['data_seed_base'])
    return {
        'train': validate_batch(sample_family(config['train_contexts'], stable_seed(base, f'{regime}:train'), family)),
        'validation': validate_batch(sample_family(config['validation_contexts'], stable_seed(base, f'{regime}:validation'), family)),
    }


def test_sets(config: dict) -> dict[str, np.ndarray]:
    base = int(config['data_seed_base'])
    return {
        family: validate_batch(sample_family(config['test_contexts'], stable_seed(base, f'test:{family}'), family))
        for family in config['test_families']
    }


def mean_relative_regret(catalog: Catalog, contexts: np.ndarray, choices: np.ndarray) -> float:
    costs = catalog.costs(contexts)
    chosen = costs[np.arange(len(costs)), choices]
    minimum = costs.min(axis=1)
    return float(np.mean(chosen / np.maximum(minimum, 1e-12) - 1))


def _save_meta(model, path: Path, catalog: Catalog, config: dict, regime: str, method: str, seed: int, update: int):
    model.save(path, {'schema': 2, 'phase': 2, 'catalog_fingerprint': catalog.fingerprint,
                      'config': config, 'regime': regime, 'method': method,
                      'seed': seed, 'best_validation_update': update})


def _curve_path(output: Path, regime: str, method: str, seed: int) -> Path:
    return output / 'training' / f'{regime}_{method}_seed{seed}.csv'


def train_reinforce(catalog: Catalog, config: dict, output: Path, regime: str, seed: int) -> dict:
    data = make_datasets(config, regime)
    train_w, val_w = data['train'], data['validation']
    val_costs = catalog.costs(val_w)
    val_best = val_costs.min(axis=1)
    model = Policy(train_w.shape[1], len(catalog.labels), config['hidden'], seed)
    model.fit_scaler(train_w)
    optimizer = Adam(model.params, config['reinforce_learning_rate'])
    rng = np.random.default_rng(stable_seed(seed + 7000, f'{regime}:reinforce'))
    baseline, reward_variance = 0.0, 1.0
    best_regret = float('inf')
    rows = []
    start = time.perf_counter()
    path = output / 'models' / f'{regime}_reinforce_seed{seed}.npz'
    for update in range(1, config['reinforce_updates'] + 1):
        idx = rng.integers(len(train_w), size=config['batch_size'])
        contexts = train_w[idx]
        probs = model.forward(contexts)[2]
        actions = (np.cumsum(probs, axis=1) < rng.random((len(contexts), 1))).sum(axis=1)
        actions = actions.clip(max=len(catalog.labels) - 1)
        sampled = catalog.chosen_costs(contexts, actions)
        reference = catalog.chosen_costs(contexts, np.full(len(contexts), catalog.reference))
        reward = 1 - sampled / np.maximum(reference, 1e-12)
        advantage = (reward - baseline) / max(np.sqrt(reward_variance), 0.2)
        baseline = 0.98 * baseline + 0.02 * reward.mean()
        reward_variance = 0.98 * reward_variance + 0.02 * float(np.var(reward))
        loss, gradients, entropy = model.loss_gradient(contexts, actions, advantage, config['entropy_coefficient'])
        optimizer.step(model.params, gradients)
        if update == 1 or update % config['log_every'] == 0 or update == config['reinforce_updates']:
            choices = model.predict(val_w)
            chosen = val_costs[np.arange(len(val_w)), choices]
            regret = float(np.mean(chosen / np.maximum(val_best, 1e-12) - 1))
            rows.append({'update': update, 'training_objective': float(reward.mean()), 'loss': loss,
                         'auxiliary': entropy, 'validation_relative_regret': regret})
            print(f'PHASE2 {regime} reinforce seed={seed} update={update}/{config["reinforce_updates"]} '
                  f'validation_regret={100*regret:.2f}%', flush=True)
            if regret < best_regret:
                best_regret = regret
                _save_meta(model, path, catalog, config, regime, 'reinforce', seed, update)
    write_csv(_curve_path(output, regime, 'reinforce', seed), rows)
    return {'method': 'reinforce', 'regime': regime, 'seed': seed, 'best_validation_regret': best_regret,
            'checkpoint': str(path), 'training_seconds': time.perf_counter() - start,
            'training_information': 'sampled action cost + fixed-reference cost only; no oracle argmin labels',
            'action_cost_evaluations': config['reinforce_updates'] * config['batch_size'] * 2}


def train_classifier(catalog: Catalog, config: dict, output: Path, regime: str, seed: int) -> dict:
    data = make_datasets(config, regime)
    train_w, val_w = data['train'], data['validation']
    train_costs = catalog.costs(train_w)
    val_costs = catalog.costs(val_w)
    targets = oracle_soft_targets(train_costs)
    val_best = val_costs.min(axis=1)
    model = Classifier(train_w.shape[1], len(catalog.labels), config['hidden'], seed + 10000)
    model.fit_scaler(train_w)
    optimizer = Adam(model.params, config['supervised_learning_rate'])
    rng = np.random.default_rng(stable_seed(seed + 17000, f'{regime}:classifier'))
    best_regret = float('inf')
    rows = []
    start = time.perf_counter()
    path = output / 'models' / f'{regime}_classifier_seed{seed}.npz'
    for update in range(1, config['supervised_updates'] + 1):
        idx = rng.integers(len(train_w), size=config['batch_size'])
        loss, gradients, train_acc = model.loss_gradient(train_w[idx], targets[idx], config['label_smoothing'])
        optimizer.step(model.params, gradients)
        if update == 1 or update % config['log_every'] == 0 or update == config['supervised_updates']:
            choices = model.predict(val_w)
            chosen = val_costs[np.arange(len(val_w)), choices]
            regret = float(np.mean(chosen / np.maximum(val_best, 1e-12) - 1))
            rows.append({'update': update, 'training_objective': train_acc, 'loss': loss,
                         'auxiliary': train_acc, 'validation_relative_regret': regret})
            print(f'PHASE2 {regime} classifier seed={seed} update={update}/{config["supervised_updates"]} '
                  f'validation_regret={100*regret:.2f}%', flush=True)
            if regret < best_regret:
                best_regret = regret
                _save_meta(model, path, catalog, config, regime, 'classifier', seed, update)
    write_csv(_curve_path(output, regime, 'classifier', seed), rows)
    return {'method': 'classifier', 'regime': regime, 'seed': seed, 'best_validation_regret': best_regret,
            'checkpoint': str(path), 'training_seconds': time.perf_counter() - start,
            'training_information': 'full 96-action oracle costs reduced to tied-argmin soft labels',
            'action_cost_evaluations': len(train_w) * len(catalog.labels)}


def train_cost_regressor(catalog: Catalog, config: dict, output: Path, regime: str, seed: int) -> dict:
    data = make_datasets(config, regime)
    train_w, val_w = data['train'], data['validation']
    train_costs = catalog.costs(train_w)
    val_costs = catalog.costs(val_w)
    targets = relative_log_cost_targets(train_costs, catalog.reference)
    val_best = val_costs.min(axis=1)
    model = CostRegressor(train_w.shape[1], len(catalog.labels), config['hidden'], seed + 20000)
    model.fit_scaler(train_w)
    optimizer = Adam(model.params, config['regression_learning_rate'])
    rng = np.random.default_rng(stable_seed(seed + 27000, f'{regime}:regressor'))
    best_regret = float('inf')
    rows = []
    start = time.perf_counter()
    path = output / 'models' / f'{regime}_cost_regressor_seed{seed}.npz'
    for update in range(1, config['supervised_updates'] + 1):
        idx = rng.integers(len(train_w), size=config['batch_size'])
        loss, gradients = model.loss_gradient(train_w[idx], targets[idx])
        optimizer.step(model.params, gradients)
        if update == 1 or update % config['log_every'] == 0 or update == config['supervised_updates']:
            choices = model.predict(val_w)
            chosen = val_costs[np.arange(len(val_w)), choices]
            regret = float(np.mean(chosen / np.maximum(val_best, 1e-12) - 1))
            rows.append({'update': update, 'training_objective': -loss, 'loss': loss,
                         'auxiliary': loss, 'validation_relative_regret': regret})
            print(f'PHASE2 {regime} cost_regressor seed={seed} update={update}/{config["supervised_updates"]} '
                  f'validation_regret={100*regret:.2f}%', flush=True)
            if regret < best_regret:
                best_regret = regret
                _save_meta(model, path, catalog, config, regime, 'cost_regressor', seed, update)
    write_csv(_curve_path(output, regime, 'cost_regressor', seed), rows)
    return {'method': 'cost_regressor', 'regime': regime, 'seed': seed, 'best_validation_regret': best_regret,
            'checkpoint': str(path), 'training_seconds': time.perf_counter() - start,
            'training_information': 'full 96-action C2 vector; predicts log cost relative to reference',
            'action_cost_evaluations': len(train_w) * len(catalog.labels)}


def train_phase2(catalog: Catalog, config: dict, output: Path) -> list[dict]:
    summaries = []
    for regime in config['training_regimes']:
        for seed in config['training_seeds']:
            summaries.append(train_reinforce(catalog, config, output, regime, seed))
            summaries.append(train_classifier(catalog, config, output, regime, seed))
            summaries.append(train_cost_regressor(catalog, config, output, regime, seed))
    write_json(output / 'training_summary.json', summaries)
    return summaries


def _load_models(catalog: Catalog, config: dict, output: Path, regime: str):
    result = {'reinforce': {}, 'classifier': {}, 'cost_regressor': {}}
    classes = {'reinforce': Policy, 'classifier': Classifier, 'cost_regressor': CostRegressor}
    for method, cls in classes.items():
        for seed in config['training_seeds']:
            path = output / 'models' / f'{regime}_{method}_seed{seed}.npz'
            model, meta = cls.load(path)
            if meta.get('phase') != 2 or meta['catalog_fingerprint'] != catalog.fingerprint or meta['config'] != config:
                raise ValueError(f'Checkpoint mismatch: {path}')
            if meta['regime'] != regime or meta['method'] != method:
                raise ValueError(f'Checkpoint metadata mismatch: {path}')
            result[method][seed] = model
    return result


def bootstrap_mean_ci(values: np.ndarray, seed: int, samples: int = 1500) -> list[float]:
    values = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    idx = rng.integers(len(values), size=(samples, len(values)))
    return [float(v) for v in np.quantile(values[idx].mean(axis=1), [0.025, 0.975])]


def _method_stats(costs: np.ndarray, choices: np.ndarray, minimum: np.ndarray, fixed_costs: np.ndarray) -> dict:
    chosen = costs[np.arange(len(costs)), choices]
    regret = chosen / np.maximum(minimum, 1e-12) - 1
    improvement = 1 - chosen / np.maximum(fixed_costs, 1e-12)
    return {'mean_C2': float(chosen.mean()), 'mean_relative_regret': float(regret.mean()),
            'oracle_match_fraction': float(np.mean(np.isclose(chosen, minimum, atol=1e-10, rtol=1e-9))),
            'mean_relative_improvement_over_fixed': float(improvement.mean()),
            '_costs': chosen, '_regret': regret}


def evaluate_phase2(catalog: Catalog, config: dict, output: Path) -> dict:
    tests = test_sets(config)
    result = {'scope': ('Phase-2 synthetic robustness study over the same finite 96-schedule certified library. '
                        'C2 assumes the documented one-check independent-Pauli model and perfect final recovery. '
                        'Supervised methods receive full offline oracle-cost information; REINFORCE does not.'),
              'families': list(tests), 'regimes': {}}
    detailed_rows = []
    seed_rows = []
    budget = min(config['search_budget'], len(catalog.labels))

    for regime in config['training_regimes']:
        train_data = make_datasets(config, regime)['train']
        train_costs = catalog.costs(train_data)
        fixed = int(train_costs.mean(axis=0).argmin())
        models = _load_models(catalog, config, output, regime)
        result['regimes'][regime] = {'best_fixed_train': catalog.labels[fixed], 'families': {}}
        for family, contexts in tests.items():
            costs = catalog.costs(contexts)
            minimum = costs.min(axis=1)
            fixed_costs = costs[:, fixed]
            n = len(contexts)
            methods: dict[str, np.ndarray] = {
                'reference': np.full(n, catalog.reference),
                'best_fixed_train': np.full(n, fixed),
                'exhaustive_oracle': costs.argmin(axis=1),
            }
            # Same random/greedy comparison for both training regimes.
            rng = np.random.default_rng(stable_seed(config['data_seed_base'], f'random:{family}'))
            random_choice = []
            for case in range(n):
                candidates = rng.choice(len(catalog.labels), size=budget, replace=False)
                random_choice.append(int(candidates[costs[case, candidates].argmin()]))
            methods['random_search'] = np.asarray(random_choice, dtype=int)
            methods['greedy_search'] = np.asarray([greedy_choice(catalog, row, budget)[0] for row in costs], dtype=int)
            for method, per_seed in models.items():
                for seed, model in per_seed.items():
                    methods[f'{method}_seed{seed}'] = model.predict(contexts)

            family_summary = {'contexts': n, 'distinct_oracle_argmin_labels': int(len(set(costs.argmin(axis=1)))),
                              'methods': {}, 'seed_aggregates': {}}
            stats_cache = {}
            for name, choices in methods.items():
                stats = _method_stats(costs, choices, minimum, fixed_costs)
                stats_cache[name] = stats
                clean = {k: v for k, v in stats.items() if not k.startswith('_')}
                family_summary['methods'][name] = clean
                for case in range(n):
                    detailed_rows.append({'regime': regime, 'family': family, 'case': case, 'method': name,
                                          'schedule': catalog.labels[int(choices[case])], 'C2': float(stats['_costs'][case]),
                                          'oracle_C2': float(minimum[case]), 'relative_regret': float(stats['_regret'][case])})

            # Aggregate learned methods across independent training seeds before bootstrapping contexts.
            random_cost = stats_cache['random_search']['_costs']
            for method in ('reinforce', 'classifier', 'cost_regressor'):
                names = [f'{method}_seed{s}' for s in config['training_seeds']]
                per_seed_costs = np.vstack([stats_cache[name]['_costs'] for name in names])
                per_seed_regret = np.vstack([stats_cache[name]['_regret'] for name in names])
                context_mean_cost = per_seed_costs.mean(axis=0)
                context_mean_regret = per_seed_regret.mean(axis=0)
                difference_vs_random = context_mean_cost - random_cost
                aggregate = {
                    'mean_C2_across_seeds': float(context_mean_cost.mean()),
                    'mean_relative_regret_across_seeds': float(context_mean_regret.mean()),
                    'mean_C2_difference_vs_random_search': float(difference_vs_random.mean()),
                    'paired_bootstrap95_C2_difference_vs_random_search': bootstrap_mean_ci(
                        difference_vs_random, stable_seed(config['data_seed_base'], f'boot:{regime}:{family}:{method}')),
                    'seed_mean_C2': {str(s): family_summary['methods'][f'{method}_seed{s}']['mean_C2']
                                     for s in config['training_seeds']},
                }
                family_summary['seed_aggregates'][method] = aggregate
                seed_rows.append({'regime': regime, 'family': family, 'method': method,
                                  'mean_C2': aggregate['mean_C2_across_seeds'],
                                  'mean_relative_regret': aggregate['mean_relative_regret_across_seeds'],
                                  'mean_C2_difference_vs_random_search': aggregate['mean_C2_difference_vs_random_search']})
            result['regimes'][regime]['families'][family] = family_summary

    # Cross-regime robustness summary for each learning paradigm.
    ood = [f for f in config['test_families'] if f != 'narrow']
    robustness = {}
    for method in ('reinforce', 'classifier', 'cost_regressor'):
        robustness[method] = {}
        for regime in config['training_regimes']:
            fam = result['regimes'][regime]['families']
            robustness[method][regime] = {
                'ID_narrow_mean_regret': fam['narrow']['seed_aggregates'][method]['mean_relative_regret_across_seeds'],
                'OOD_macro_mean_regret': float(np.mean([
                    fam[f]['seed_aggregates'][method]['mean_relative_regret_across_seeds'] for f in ood
                ])),
            }
        if 'narrow' in robustness[method] and 'domain_randomized' in robustness[method]:
            robustness[method]['domain_randomization_OOD_regret_reduction'] = (
                robustness[method]['narrow']['OOD_macro_mean_regret'] -
                robustness[method]['domain_randomized']['OOD_macro_mean_regret'])
    result['robustness'] = robustness
    write_json(output / 'phase2_evaluation.json', result)
    write_csv(output / 'phase2_evaluation_cases.csv', detailed_rows)
    write_csv(output / 'phase2_seed_aggregates.csv', seed_rows)
    return result


def _escape(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def write_learning_curve_svg(output: Path, config: dict, regime: str) -> None:
    methods = ('reinforce', 'classifier', 'cost_regressor')
    series = {}
    for method in methods:
        by_update = {}
        for seed in config['training_seeds']:
            path = _curve_path(output, regime, method, seed)
            with path.open() as handle:
                for row in csv.DictReader(handle):
                    by_update.setdefault(int(row['update']), []).append(float(row['validation_relative_regret']))
        series[method] = [(u, float(np.mean(by_update[u]))) for u in sorted(by_update)]
    width, height, left, top, plot_w, plot_h = 900, 520, 85, 50, 760, 390
    max_x = max(x for values in series.values() for x, _ in values)
    max_y = max(y for values in series.values() for _, y in values) * 1.05
    max_y = max(max_y, 0.01)
    colors = {'reinforce': '#1f77b4', 'classifier': '#d62728', 'cost_regressor': '#2ca02c'}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{width/2}" y="26" text-anchor="middle" font-family="sans-serif" font-size="18">Phase 2 validation regret: {_escape(regime)}</text>',
             f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="black"/>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="black"/>']
    for tick in range(6):
        yv = max_y * tick / 5
        y = top + plot_h - plot_h * tick / 5
        parts.append(f'<line x1="{left-5}" y1="{y:.1f}" x2="{left}" y2="{y:.1f}" stroke="black"/>')
        parts.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11">{100*yv:.1f}%</text>')
    for tick in range(6):
        xv = max_x * tick / 5
        x = left + plot_w * tick / 5
        parts.append(f'<text x="{x:.1f}" y="{top+plot_h+24}" text-anchor="middle" font-family="sans-serif" font-size="11">{int(xv)}</text>')
    for idx, (method, values) in enumerate(series.items()):
        pts = []
        for xval, yval in values:
            x = left + plot_w * xval / max_x
            y = top + plot_h - plot_h * yval / max_y
            pts.append(f'{x:.2f},{y:.2f}')
        parts.append(f'<polyline fill="none" stroke="{colors[method]}" stroke-width="2.5" points="{" ".join(pts)}"/>')
        parts.append(f'<line x1="{left+520}" y1="{top+20+idx*24}" x2="{left+550}" y2="{top+20+idx*24}" stroke="{colors[method]}" stroke-width="3"/>')
        parts.append(f'<text x="{left+560}" y="{top+24+idx*24}" font-family="sans-serif" font-size="12">{_escape(method)}</text>')
    parts += [f'<text x="{left+plot_w/2}" y="{height-20}" text-anchor="middle" font-family="sans-serif" font-size="12">training update</text>',
              f'<text transform="translate(18 {top+plot_h/2}) rotate(-90)" text-anchor="middle" font-family="sans-serif" font-size="12">mean validation relative regret</text>', '</svg>']
    (output / f'learning_curves_{regime}.svg').write_text('\n'.join(parts))


def write_robustness_svg(output: Path, evaluation: dict) -> None:
    methods = ('reinforce', 'classifier', 'cost_regressor')
    regimes = ('narrow', 'domain_randomized')
    values = {(m, r): evaluation['robustness'][m][r]['OOD_macro_mean_regret'] for m in methods for r in regimes}
    width, height = 900, 520
    left, top, plot_w, plot_h = 90, 60, 750, 360
    max_y = max(values.values()) * 1.15
    colors = {'narrow': '#777777', 'domain_randomized': '#1f77b4'}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{width/2}" y="28" text-anchor="middle" font-family="sans-serif" font-size="18">OOD macro-mean regret by training regime</text>',
             f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="black"/>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="black"/>']
    for tick in range(6):
        yv = max_y * tick / 5
        y = top + plot_h - plot_h * tick / 5
        parts.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11">{100*yv:.1f}%</text>')
    group_w = plot_w / len(methods)
    bar_w = 62
    for i, method in enumerate(methods):
        center = left + group_w * (i + 0.5)
        for j, regime in enumerate(regimes):
            value = values[(method, regime)]
            x = center + (j - 0.5) * 76 - bar_w/2
            h = plot_h * value / max_y
            y = top + plot_h - h
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" fill="{colors[regime]}"/>')
            parts.append(f'<text x="{x+bar_w/2:.1f}" y="{y-5:.1f}" text-anchor="middle" font-family="sans-serif" font-size="10">{100*value:.1f}%</text>')
        parts.append(f'<text x="{center:.1f}" y="{top+plot_h+24}" text-anchor="middle" font-family="sans-serif" font-size="11">{_escape(method)}</text>')
    for j, regime in enumerate(regimes):
        parts.append(f'<rect x="{left+510+j*150}" y="{top+8}" width="14" height="14" fill="{colors[regime]}"/>')
        parts.append(f'<text x="{left+530+j*150}" y="{top+20}" font-family="sans-serif" font-size="11">{_escape(regime)}</text>')
    parts.append('</svg>')
    (output / 'robustness.svg').write_text('\n'.join(parts))


def write_phase2_report(output: Path, evaluation: dict, config: dict) -> None:
    lines = ['# Phase 2 summary', '',
             'Question: which learning paradigm works best for noise-conditioned selection, and does domain-randomized training improve robustness?', '',
             'C2 is a second-order logical-failure coefficient for the same one-check model with perfect final recovery. Lower is better.', '',
             'Supervised classifier and cost-regressor training use full offline 96-action oracle costs. REINFORCE does not receive oracle argmin labels.', '']
    for regime in config['training_regimes']:
        lines += [f'## Training regime: {regime}', '']
        for family in config['test_families']:
            fam = evaluation['regimes'][regime]['families'][family]
            lines += [f'### Test family: {family}', '',
                      '| Method | Mean C2 | Mean relative regret |', '|---|---:|---:|']
            for name in ('reference', 'best_fixed_train', 'random_search', 'greedy_search', 'exhaustive_oracle'):
                r = fam['methods'][name]
                lines.append(f'| {name} | {r["mean_C2"]:.6f} | {100*r["mean_relative_regret"]:.2f}% |')
            for method in ('reinforce', 'classifier', 'cost_regressor'):
                r = fam['seed_aggregates'][method]
                lines.append(f'| {method} (seed mean) | {r["mean_C2_across_seeds"]:.6f} | {100*r["mean_relative_regret_across_seeds"]:.2f}% |')
            lines.append('')
    lines += ['## Robustness macro-summary', '',
              '| Learning method | Narrow-trained ID regret | Narrow-trained OOD regret | Domain-randomized ID regret | Domain-randomized OOD regret | OOD regret reduction from domain randomization |',
              '|---|---:|---:|---:|---:|---:|']
    for method in ('reinforce', 'classifier', 'cost_regressor'):
        r = evaluation['robustness'][method]
        gain = r.get('domain_randomization_OOD_regret_reduction', float('nan'))
        lines.append(f'| {method} | {100*r["narrow"]["ID_narrow_mean_regret"]:.2f}% | '
                     f'{100*r["narrow"]["OOD_macro_mean_regret"]:.2f}% | '
                     f'{100*r["domain_randomized"]["ID_narrow_mean_regret"]:.2f}% | '
                     f'{100*r["domain_randomized"]["OOD_macro_mean_regret"]:.2f}% | {100*gain:.2f} pp |')
    lines += ['', '## Interpretation rules', '',
              '- Supervised models have a stronger training-information advantage: their labels require offline evaluation of all 96 schedules.',
              '- REINFORCE uses sampled-action feedback plus a fixed-reference control variate, so its training-information budget is different.',
              '- Random and greedy search evaluate candidate schedules online; a learned model performs one policy inference plus the selected-circuit diagnostic.',
              '- Exhaustive search is still cheap for this 96-circuit pilot and remains the exact oracle only within this finite library.',
              '- OOD families are synthetic stress tests, not measured hardware distributions.',
              '- This phase tests method choice and generalization; it does not establish unrestricted circuit synthesis, hardware advantage, or full QEC-cycle fault tolerance.', '',
              'See `learning_curves_narrow.svg`, `learning_curves_domain_randomized.svg`, and `robustness.svg` for plots.']
    (output / 'phase2_summary.md').write_text('\n'.join(lines) + '\n')
