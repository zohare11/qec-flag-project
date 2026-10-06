"""Reproducible splits, REINFORCE training, and honest held-out baselines."""
from __future__ import annotations
from pathlib import Path
import csv
import json
import time
import numpy as np
from .agent import Policy, Adam
from .catalog import Catalog, greedy_choice
from .noise import sample_contexts


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError('Cannot write an empty table')
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def splits(config: dict):
    return {
        'train': sample_contexts(config['train_contexts'], config['data_seeds']['train']),
        'validation': sample_contexts(config['validation_contexts'], config['data_seeds']['validation']),
        'test': sample_contexts(config['test_contexts'], config['data_seeds']['test']),
        'shift': sample_contexts(config['test_contexts'], config['data_seeds']['shift'], 'shift'),
    }


def best_fixed_choice(catalog, training_contexts):
    # This is explicitly an OFFLINE trained baseline, not a test-set oracle.
    return int(catalog.costs(training_contexts).mean(axis=0).argmin())


def train(catalog: Catalog, config: dict, output: Path, seed: int) -> dict:
    datasets = splits(config)
    train_w, val_w = datasets['train'], datasets['validation']
    # Only validation uses oracle minima for early model selection.
    val_costs = catalog.costs(val_w)
    val_best = val_costs.min(axis=1)
    model = Policy(train_w.shape[1], len(catalog.labels), config['hidden'], seed)
    model.fit_scaler(train_w)
    optimizer = Adam(model.params, config['learning_rate'])
    rng = np.random.default_rng(seed + 7731)
    baseline = 0.0
    reward_variance = 1.0
    best_regret = float('inf')
    rows = []
    start = time.perf_counter()
    path = output / f'policy_seed{seed}.npz'
    for update in range(1, config['updates'] + 1):
        indices = rng.integers(len(train_w), size=config['batch_size'])
        contexts = train_w[indices]
        probs = model.forward(contexts)[2]
        actions = (np.cumsum(probs, axis=1) < rng.random((len(contexts), 1))).sum(axis=1)
        actions = actions.clip(max=len(catalog.labels) - 1)
        # Two evaluated actions per context: sampled and fixed reference.
        sampled = catalog.chosen_costs(contexts, actions)
        reference = catalog.chosen_costs(contexts, np.full(len(contexts), catalog.reference))
        reward = 1 - sampled / np.maximum(reference, 1e-12)
        advantage = (reward - baseline) / max(np.sqrt(reward_variance), 0.2)
        baseline = 0.98 * baseline + 0.02 * reward.mean()
        reward_variance = 0.98 * reward_variance + 0.02 * float(np.var(reward))
        loss, gradients, entropy = model.loss_gradient(contexts, actions, advantage, config['entropy_coefficient'])
        optimizer.step(model.params, gradients)
        if update == 1 or update % config['log_every'] == 0 or update == config['updates']:
            choices = model.predict(val_w)
            costs = val_costs[np.arange(len(val_w)), choices]
            regret = float(np.mean(costs / np.maximum(val_best, 1e-12) - 1))
            rows.append({'update': update, 'sampled_reward': float(reward.mean()), 'loss': loss,
                         'entropy': entropy, 'validation_relative_regret': regret,
                         'elapsed_seconds': time.perf_counter() - start})
            print(f'TRAIN seed={seed} update={update}/{config["updates"]} '
                  f'reward={reward.mean():.3f} validation_regret={100*regret:.2f}%', flush=True)
            if regret < best_regret:
                best_regret = regret
                model.save(path, {'schema': 1, 'catalog_fingerprint': catalog.fingerprint,
                                  'algorithm': 'one-step REINFORCE contextual bandit',
                                  'seed': seed, 'best_validation_update': update, 'config': config})
    write_csv(output / f'training_seed{seed}.csv', rows)
    summary = {'seed': seed, 'model_file': str(path), 'best_validation_regret': best_regret,
               'training_seconds': time.perf_counter() - start,
               'sampled_action_reward_evaluations': config['updates'] * config['batch_size'],
               'reference_control_variate_evaluations': config['updates'] * config['batch_size'],
               'test_used_for_training_or_checkpoint_selection': False}
    write_json(output / f'training_seed{seed}.json', summary)
    return summary


def bootstrap_mean_ci(values, seed: int = 991, samples: int = 1000):
    rng = np.random.default_rng(seed)
    indices = rng.integers(len(values), size=(samples, len(values)))
    means = np.asarray(values)[indices].mean(axis=1)
    return [float(v) for v in np.quantile(means, [0.025, 0.975])]


def evaluate(catalog: Catalog, config: dict, output: Path) -> dict:
    datasets = splits(config)
    fixed = best_fixed_choice(catalog, datasets['train'])
    policies = {}
    for seed in config['training_seeds']:
        model, metadata = Policy.load(output / f'policy_seed{seed}.npz')
        if metadata['catalog_fingerprint'] != catalog.fingerprint or metadata['config'] != config:
            raise ValueError('Checkpoint/config/catalog mismatch. Use the matching run directory.')
        policies[seed] = model
    summary, rows = {}, []
    for split in ('test', 'shift'):
        contexts = datasets[split]
        start = time.perf_counter()
        costs = catalog.costs(contexts)
        oracle_seconds = time.perf_counter() - start
        n = len(contexts)
        minimum = costs.min(axis=1)
        method_choices = {
            'reference': np.full(n, catalog.reference),
            'best_fixed_train': np.full(n, fixed),
            'exhaustive_oracle': costs.argmin(axis=1),
        }
        counts = {'reference': np.ones(n), 'best_fixed_train': np.ones(n),
                  'exhaustive_oracle': np.full(n, len(catalog.labels))}
        rng = np.random.default_rng(config['data_seeds'][split] + 712)
        random_choices = []
        budget = min(config['search_budget'], len(catalog.labels))
        for case in range(n):
            candidates = rng.choice(len(catalog.labels), size=budget, replace=False)
            random_choices.append(int(candidates[costs[case, candidates].argmin()]))
        method_choices['random_search'] = np.array(random_choices)
        counts['random_search'] = np.full(n, budget)
        greedy = [greedy_choice(catalog, row, budget) for row in costs]
        method_choices['greedy_search'] = np.array([r[0] for r in greedy])
        counts['greedy_search'] = np.array([r[1] for r in greedy])
        inference_times = {}
        for seed, model in policies.items():
            name = f'learned_seed{seed}'
            start = time.perf_counter()
            method_choices[name] = model.predict(contexts)
            inference_times[name] = time.perf_counter() - start
            counts[name] = np.ones(n)
        summary[split] = {'contexts': n, 'oracle_distinct_argmin_labels': len(set(costs.argmin(axis=1))),
                          'best_fixed_train': catalog.labels[fixed], 'oracle_batch_cost_seconds': oracle_seconds,
                          'policy_batch_inference_seconds': inference_times, 'methods': {}}
        fixed_costs = costs[:, fixed]
        for name, choices in method_choices.items():
            chosen_costs = costs[np.arange(n), choices]
            regret = chosen_costs / np.maximum(minimum, 1e-12) - 1
            improvement = 1 - chosen_costs / np.maximum(fixed_costs, 1e-12)
            summary[split]['methods'][name] = {
                'mean_C2': float(chosen_costs.mean()),
                'mean_relative_regret': float(regret.mean()),
                'oracle_match_fraction': float(np.mean(np.isclose(chosen_costs, minimum, atol=1e-10, rtol=1e-9))),
                'mean_relative_improvement_over_fixed': float(improvement.mean()),
                'paired_context_bootstrap95_improvement_over_fixed': bootstrap_mean_ci(improvement),
                'mean_candidate_evaluations_including_final_diagnostic': float(counts[name].mean()),
            }
            for case in range(n):
                rows.append({'split': split, 'case': case, 'method': name, 'schedule': catalog.labels[choices[case]],
                             'C2': float(chosen_costs[case]), 'oracle_C2': float(minimum[case]),
                             'relative_regret': float(regret[case]), 'candidate_evaluations': int(counts[name][case])})
    summary['scope'] = ('Finite certified gate-order library; C2 is a second-order coefficient with perfect final recovery. '
                        'All methods share the same offline catalog. Timing excludes catalog construction and training. '
                        'Bootstrap intervals vary contexts, not physical devices. No unrestricted circuit optimum is claimed.')
    write_json(output / 'evaluation.json', summary)
    write_csv(output / 'evaluation.csv', rows)
    for split in ('test', 'shift'):
        print(f'\nEVALUATION {split}: mean C2 / relative regret / exact-oracle matches')
        for name, result in summary[split]['methods'].items():
            print(f'  {name:20} {result["mean_C2"]:.5f} / {100*result["mean_relative_regret"]:6.2f}% / '
                  f'{100*result["oracle_match_fraction"]:5.1f}%')
    return summary
