"""Training, baselines, evaluation, and reporting for Phase 3A/3B."""
from __future__ import annotations
from pathlib import Path
import csv
import json
import math
import shutil
import time
import numpy as np

from .agent import Adam
from .phase3_agent import ActorCritic, rollout_batch, greedy_labels, beam_candidates
from .phase3_catalog import ensure_catalog, SynthesisCatalog, catalog_verification_summary
from .phase3_env import FeatureEncoder
from .phase3_noise import sample_contexts
from .phase3_physics import schedule_from_label, decoder_and_certificate, ideal_dense_error
from .phase3_simulation import simulate


def stable_seed(base: int, text: str) -> int:
    value = int(base) & 0xffffffff
    for byte in text.encode():
        value = (value * 1664525 + byte + 1013904223) & 0xffffffff
    return value


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def _selected_costs(catalog: SynthesisCatalog, contexts: np.ndarray, labels: list[str]) -> tuple[np.ndarray, np.ndarray]:
    indices = np.array([catalog.index(x) if catalog.index(x) is not None else -1 for x in labels], dtype=int)
    costs = np.full(len(indices), np.inf)
    valid = indices >= 0
    if np.any(valid):
        costs[valid] = catalog.chosen_costs(contexts[valid], indices[valid])
    return costs, valid


def terminal_rewards(catalog: SynthesisCatalog, contexts: np.ndarray, labels: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    costs, valid = _selected_costs(catalog, contexts, labels)
    ref = catalog.chosen_costs(contexts, np.full(len(contexts), catalog.reference, dtype=int))
    reward = np.full(len(contexts), -1.0, dtype=np.float64)
    ratio_log = np.log(np.maximum(ref[valid], 1e-12) / np.maximum(costs[valid], 1e-12))
    reward[valid] = 1.0 + np.tanh(ratio_log)
    return reward, costs, valid


def evaluate_policy_no_oracle(model: ActorCritic, encoder: FeatureEncoder, catalog: SynthesisCatalog,
                              contexts: np.ndarray, mode: str) -> tuple[float, float, float]:
    labels = greedy_labels(model, encoder, contexts, mode)
    costs, valid = _selected_costs(catalog, contexts, labels)
    ref = catalog.chosen_costs(contexts, np.full(len(contexts), catalog.reference, dtype=int))
    safe = np.where(valid, costs, ref * 10)
    score = float(np.mean(np.log(np.maximum(safe, 1e-12) / np.maximum(ref, 1e-12))))
    return score, float(np.mean(safe)), float(np.mean(valid))


def train_actor_critic(catalog: SynthesisCatalog, mode: str, config: dict, seed: int,
                       output: Path, tag: str, family: str) -> dict:
    train = sample_contexts(config['train_contexts'], stable_seed(config['data_seed'], f'{tag}:train'), family)
    val = sample_contexts(config['validation_contexts'], stable_seed(config['data_seed'], f'{tag}:val'), family)
    encoder = FeatureEncoder(); encoder.fit(train)
    model = ActorCritic(encoder.n_features, hidden=config['hidden'], seed=seed)
    optimizer = Adam(model.params, learning_rate=config['learning_rate'])
    rng = np.random.default_rng(seed)
    best_score = np.inf
    best_params = None
    rows = []

    for update in range(1, config['updates'] + 1):
        idx = rng.integers(len(train), size=config['batch_episodes'])
        contexts = train[idx]
        rollout = rollout_batch(model, encoder, contexts, mode, rng, deterministic=False)
        reward, _, valid = terminal_rewards(catalog, contexts, rollout.labels)
        returns = reward[rollout.episode_index]
        loss, grads, entropy, value_loss = model.gradient(
            rollout.features, rollout.masks, rollout.actions, returns,
            entropy_coefficient=config['entropy_coefficient'], value_coefficient=config['value_coefficient'])
        optimizer.step(model.params, grads)

        if update == 1 or update % config['eval_every'] == 0 or update == config['updates']:
            val_score, val_cost, val_valid = evaluate_policy_no_oracle(model, encoder, catalog, val, mode)
            row = {'update': update, 'loss': loss, 'entropy': entropy, 'value_loss': value_loss,
                   'train_certified_fraction': float(valid.mean()), 'validation_log_cost_vs_reference': val_score,
                   'validation_mean_C2': val_cost, 'validation_certified_fraction': val_valid}
            rows.append(row)
            print(f'P3 TRAIN {tag} seed={seed} update={update}/{config["updates"]} '
                  f'valid={100*valid.mean():.1f}% val_log_ratio={val_score:.4f}')
            if val_score < best_score:
                best_score = val_score
                best_params = {k: v.copy() for k, v in model.params.items()}
    if best_params is not None:
        model.params = best_params
    model_path = output / f'phase3_{tag}_seed{seed}.npz'
    model.save(model_path, encoder, {'mode': mode, 'seed': seed, 'family': family,
                                     'catalog_fingerprint': catalog.fingerprint,
                                     'best_validation_log_cost_vs_reference': best_score})
    write_csv(output / f'phase3_training_{tag}_seed{seed}.csv', rows)
    return {'seed': seed, 'model_path': model_path.name, 'best_validation_log_cost_vs_reference': best_score}


def _random_search_choices(costs: np.ndarray, budget: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n, actions = costs.shape
    result = np.empty(n, dtype=int)
    for row in range(n):
        sample = rng.choice(actions, size=min(budget, actions), replace=False)
        result[row] = int(sample[np.argmin(costs[row, sample])])
    return result


def _beam_choices(model, encoder, catalog, contexts, mode, width: int) -> tuple[np.ndarray, np.ndarray]:
    choices = np.full(len(contexts), catalog.reference, dtype=int)
    evaluated = np.zeros(len(contexts), dtype=int)
    for i, context in enumerate(contexts):
        labels = beam_candidates(model, encoder, context, mode, width)
        indices = np.array([catalog.index(x) for x in labels if catalog.index(x) is not None], dtype=int)
        if len(indices):
            local = catalog.chosen_costs(np.repeat(context[None, :], len(indices), axis=0), indices)
            choices[i] = int(indices[np.argmin(local)])
            evaluated[i] = len(indices)
    return choices, evaluated


def _stats(costs: np.ndarray, choices: np.ndarray, oracle: np.ndarray) -> dict:
    chosen = costs[np.arange(len(costs)), choices]
    optimum = costs[np.arange(len(costs)), oracle]
    regret = chosen / np.maximum(optimum, 1e-12) - 1
    return {'mean_C2': float(chosen.mean()), 'mean_relative_regret': float(regret.mean()),
            'oracle_match_fraction': float(np.mean(choices == oracle))}


def evaluate_phase(catalog: SynthesisCatalog, mode: str, config: dict, output: Path,
                   tag: str, train_family: str, test_families: list[str]) -> dict:
    train = sample_contexts(config['train_contexts'], stable_seed(config['data_seed'], f'{tag}:train'), train_family)
    mean_feature = __import__('qecflag.phase3_physics', fromlist=['quadratic_features']).quadratic_features(train).mean(axis=0)
    fixed = int(np.argmin(catalog._float_counts() @ mean_feature))

    models = []
    for seed in config['training_seeds']:
        path = output / f'phase3_{tag}_seed{seed}.npz'
        model, encoder, metadata = ActorCritic.load(path)
        if metadata['catalog_fingerprint'] != catalog.fingerprint:
            raise ValueError('Model/catalog fingerprint mismatch')
        models.append((seed, model, encoder))

    result = {'tag': tag, 'mode': mode, 'train_family': train_family,
              'best_fixed_label': catalog.labels[fixed], 'families': {}}
    rows = []
    for family in test_families:
        contexts = sample_contexts(config['test_contexts'], stable_seed(config['data_seed'], f'{tag}:test:{family}'), family)
        costs = catalog.all_costs(contexts)
        oracle = costs.argmin(axis=1)
        methods: dict[str, np.ndarray] = {
            'reference': np.full(len(contexts), catalog.reference, dtype=int),
            'best_fixed_train': np.full(len(contexts), fixed, dtype=int),
            'random_search': _random_search_choices(costs, config['search_budget'],
                                                    stable_seed(config['data_seed'], f'{tag}:random:{family}')),
            'exhaustive_oracle': oracle,
        }
        if mode == 'expanded':
            one = np.flatnonzero(np.isin(catalog.kinds, ['A_only', 'B_only']))
            methods['one_flag_oracle'] = one[costs[:, one].argmin(axis=1)]
        beam_evals = {}
        for seed, model, encoder in models:
            labels = greedy_labels(model, encoder, contexts, mode)
            greedy_idx = np.array([catalog.index(x) if catalog.index(x) is not None else catalog.reference for x in labels])
            methods[f'policy_greedy_seed{seed}'] = greedy_idx
            beam, evaluated = _beam_choices(model, encoder, catalog, contexts, mode, config['search_budget'])
            methods[f'policy_beam_seed{seed}'] = beam
            beam_evals[str(seed)] = float(evaluated.mean())

        fam = {'contexts': len(contexts), 'methods': {}, 'beam_mean_exact_evaluations': beam_evals, 'seed_aggregates': {}}
        for name, choices in methods.items():
            fam['methods'][name] = _stats(costs, choices, oracle)
            for case, choice in enumerate(choices):
                rows.append({'phase': tag, 'family': family, 'case': case, 'method': name,
                             'schedule': catalog.labels[int(choice)], 'kind': str(catalog.kinds[int(choice)]),
                             'C2': float(costs[case, choice]), 'oracle_C2': float(costs[case, oracle[case]])})
        for prefix in ('policy_greedy', 'policy_beam'):
            names = [f'{prefix}_seed{s}' for s in config['training_seeds']]
            fam['seed_aggregates'][prefix] = {
                'mean_C2': float(np.mean([fam['methods'][n]['mean_C2'] for n in names])),
                'mean_relative_regret': float(np.mean([fam['methods'][n]['mean_relative_regret'] for n in names])),
                'oracle_match_fraction': float(np.mean([fam['methods'][n]['oracle_match_fraction'] for n in names])),
            }

        if mode == 'expanded':
            kinds = catalog.kinds[oracle]
            fam['oracle_kind_fraction'] = {kind: float(np.mean(kinds == kind))
                                           for kind in ('A_only', 'B_only', 'A_and_B')}
            one_choice = methods['one_flag_oracle']
            one_cost = costs[np.arange(len(costs)), one_choice]
            exp_cost = costs[np.arange(len(costs)), oracle]
            fam['expanded_vs_one_flag'] = {
                'fraction_expanded_oracle_uses_two_flags': float(np.mean(kinds == 'A_and_B')),
                'fraction_expanded_improves_C2_over_best_one_flag': float(np.mean(exp_cost < one_cost - 1e-10)),
                'mean_relative_C2_improvement_when_better': float(np.mean(
                    np.where(exp_cost < one_cost - 1e-10, (one_cost-exp_cost)/np.maximum(one_cost,1e-12), 0.0))),
            }
        result['families'][family] = fam
    write_json(output / f'phase3_{tag}_evaluation.json', result)
    write_csv(output / f'phase3_{tag}_cases.csv', rows)
    return result


def run_diagnostics(catalog: SynthesisCatalog, config: dict, output: Path, evaluation: dict,
                    tag: str, family: str) -> dict:
    contexts = sample_contexts(1, stable_seed(config['data_seed'], f'{tag}:diagnostic:{family}'), family)
    context = contexts[0]
    costs = catalog.all_costs(contexts)[0]
    oracle_idx = int(np.argmin(costs))
    # Use first policy seed greedy choice.
    seed = config['training_seeds'][0]
    model, encoder, _ = ActorCritic.load(output / f'phase3_{tag}_seed{seed}.npz')
    label = greedy_labels(model, encoder, contexts, 'single_A' if tag == '3A' else 'expanded')[0]
    learned_idx = catalog.index(label)
    if learned_idx is None:
        learned_idx = catalog.reference
    selected = {'reference': catalog.reference, 'learned_greedy': learned_idx, 'oracle': oracle_idx}
    if tag == '3B':
        one = np.flatnonzero(np.isin(catalog.kinds, ['A_only', 'B_only']))
        selected['one_flag_oracle'] = int(one[np.argmin(costs[one])])
    rows = []
    for name, idx in selected.items():
        schedule = schedule_from_label(catalog.labels[idx])
        decoder, report = decoder_and_certificate(schedule)
        for p in config['diagnostic_p']:
            # Common random-number seed across methods at a given p. Identical
            # schedules then produce identical diagnostics, and comparisons have lower
            # Monte Carlo noise than method-specific seeds.
            sim = simulate(schedule, decoder, context, p, config['diagnostic_shots'],
                           stable_seed(config['data_seed'], f'{tag}:{family}:{p}'))
            rows.append({'method': name, 'label': catalog.labels[idx], 'kind': str(catalog.kinds[idx]),
                         'C2': float(costs[idx]), **sim})
    write_json(output / f'phase3_{tag}_noise.json', {'family': family, 'rows': rows})
    return {'family': family, 'rows': rows}


def markdown_summary(verify_a: dict, verify_b: dict, eval_a: dict, eval_b: dict,
                     noise_a: dict, noise_b: dict) -> str:
    out = ['# Phase 3 summary', '',
           'Scope: sequential synthesis of interaction schedules for one flagged Steane Z-check. '
           'This is not unrestricted circuit synthesis or a full noisy QEC cycle.', '',
           'Lower C2 is better. Policy-greedy uses no online C2 search; policy-beam and random search '
           'use the stated finite exact-evaluation budget.', '',
           '## Verification', '',
           f"- Phase 3A: {verify_a['certified_schedules']} certified of {verify_a['candidate_schedules']} candidates.",
           f"- Phase 3B: {verify_b['certified_schedules']} certified of {verify_b['candidate_schedules']} candidates.",
           f"- Phase 3B certified kinds: {verify_b['certified_by_kind']}.", '',
           '## Phase 3A — reconstruct the known one-flag family sequentially', '']
    for family, fam in eval_a['families'].items():
        out += [f'### {family}', '', '| Method | Mean C2 | Mean relative regret | Oracle match |',
                '|---|---:|---:|---:|']
        for name, s in fam['methods'].items():
            if name.startswith('policy_greedy_seed') or name.startswith('policy_beam_seed'):
                continue
            out.append(f"| {name} | {s['mean_C2']:.6f} | {100*s['mean_relative_regret']:.2f}% | {100*s['oracle_match_fraction']:.2f}% |")
        for name, s in fam['seed_aggregates'].items():
            out.append(f"| {name} (seed mean) | {s['mean_C2']:.6f} | {100*s['mean_relative_regret']:.2f}% | {100*s['oracle_match_fraction']:.2f}% |")
        out.append('')
    out += ['## Phase 3B — choose flag ancilla(s) and synthesize the schedule', '']
    for family, fam in eval_b['families'].items():
        out += [f'### {family}', '', '| Method | Mean C2 | Mean relative regret | Oracle match |',
                '|---|---:|---:|---:|']
        for name, s in fam['methods'].items():
            if name.startswith('policy_greedy_seed') or name.startswith('policy_beam_seed'):
                continue
            out.append(f"| {name} | {s['mean_C2']:.6f} | {100*s['mean_relative_regret']:.2f}% | {100*s['oracle_match_fraction']:.2f}% |")
        for name, s in fam['seed_aggregates'].items():
            out.append(f"| {name} (seed mean) | {s['mean_C2']:.6f} | {100*s['mean_relative_regret']:.2f}% | {100*s['oracle_match_fraction']:.2f}% |")
        fractions = fam.get('oracle_kind_fraction', {})
        if fractions:
            out += ['', 'Expanded-oracle circuit type: ' + ', '.join(f'{k}={100*v:.1f}%' for k,v in fractions.items()) + '.']
        comp = fam.get('expanded_vs_one_flag')
        if comp:
            out.append(f"Two flags are oracle-selected in {100*comp['fraction_expanded_oracle_uses_two_flags']:.1f}% of contexts; "
                       f"the expanded catalog strictly improves over the best one-flag schedule in "
                       f"{100*comp['fraction_expanded_improves_C2_over_best_one_flag']:.1f}%.")
        out.append('')
    out += ['## Finite-p diagnostics', '',
            'These use one predeclared synthetic context per phase and ideal final recovery; they are component diagnostics only.', '']
    for tag, noise in [('3A', noise_a), ('3B', noise_b)]:
        out += [f'### Phase {tag}', '', '| Method | Schedule | Kind | p | failures/shots | rate | 95% interval |',
                '|---|---|---|---:|---:|---:|---:|']
        for r in noise['rows']:
            out.append(f"| {r['method']} | {r['label']} | {r['kind']} | {r['p']:.4g} | {r['failures']}/{r['shots']} | "
                       f"{r['rate_with_perfect_final_recovery']:.7f} | [{r['wilson95_low']:.7f}, {r['wilson95_high']:.7f}] |")
        out.append('')
    out += ['## Interpretation constraints', '',
            '- The policy synthesizes an ordered interaction schedule inside a fixed grammar; it does not invent arbitrary gates.',
            '- Exact exhaustive oracles are retained because both pilot spaces are still small enough to enumerate.',
            '- Phase 3B adds a second available flag ancilla and variable one-flag/two-flag schedules; this is a real expansion of the candidate family.',
            '- Synthetic noise families are controlled stress tests, not device calibration data.',
            '- Certification assumes an ideal final syndrome and perfect recovery after this one check.',
            '- A positive result here motivates larger synthesis spaces; it does not establish hardware or fault-tolerant quantum-computing advantage.', '']
    return '\n'.join(out)


def run_all(config: dict, output: Path, cache_dir: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    cat_a = ensure_catalog(cache_dir / 'phase3_singleA_catalog.npz', 'single_A', progress=True)
    cat_b = ensure_catalog(cache_dir / 'phase3_expanded_catalog.npz', 'expanded', progress=True)
    verify_a = catalog_verification_summary(cat_a)
    verify_b = catalog_verification_summary(cat_b)
    # Independent ideal dense checks on representative certified circuits.
    for catalog, summary in ((cat_a, verify_a), (cat_b, verify_b)):
        sample_labels = [catalog.labels[0], catalog.labels[len(catalog.labels)//2], catalog.labels[-1]]
        summary['representative_dense_ideal_max_error'] = max(ideal_dense_error(schedule_from_label(x)) for x in sample_labels)
    write_json(output / 'phase3_verification.json', {'phase3A': verify_a, 'phase3B': verify_b})

    cfg_a = {**config['phase3A'], 'training_seeds': config['training_seeds']}
    cfg_b = {**config['phase3B'], 'training_seeds': config['training_seeds']}
    training = {'3A': [], '3B': []}
    for seed in config['training_seeds']:
        training['3A'].append(train_actor_critic(cat_a, 'single_A', cfg_a, seed, output, '3A', 'single_narrow'))
        training['3B'].append(train_actor_critic(cat_b, 'expanded', cfg_b, seed, output, '3B', 'synthesis_train'))
    write_json(output / 'phase3_training_summary.json', training)

    eval_a = evaluate_phase(cat_a, 'single_A', cfg_a, output, '3A', 'single_narrow',
                            cfg_a['test_families'])
    eval_b = evaluate_phase(cat_b, 'expanded', cfg_b, output, '3B', 'synthesis_train',
                            cfg_b['test_families'])
    noise_a = run_diagnostics(cat_a, cfg_a, output, eval_a, '3A', cfg_a['diagnostic_family'])
    noise_b = run_diagnostics(cat_b, cfg_b, output, eval_b, '3B', cfg_b['diagnostic_family'])
    summary = markdown_summary(verify_a, verify_b, eval_a, eval_b, noise_a, noise_b)
    (output / 'phase3_summary.md').write_text(summary)
    return {'verification': {'3A': verify_a, '3B': verify_b}, 'evaluation': {'3A': eval_a, '3B': eval_b}}
