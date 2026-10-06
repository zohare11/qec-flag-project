"""Training/evaluation pipeline for Phase-4 full-round proposal learning."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import json
import time
import numpy as np

from .agent import Adam
from .phase3_catalog import ensure_catalog
from .phase3_physics import quadratic_features
from .phase4_agent import RoundActorCritic, rollout_batch, greedy_choices, beam_candidates
from .phase4_env import RoundFeatureEncoder
from .phase4_noise import sample_round_contexts
from .phase4_physics import round_c2, round_risk, verification_summary
from .phase4_templates import ActionTable, ensure_action_table
from .phase4_simulation import simulate


@dataclass
class ProxyEvaluator:
    table: ActionTable
    selected_counts: np.ndarray
    reference_action: int

    @classmethod
    def build(cls, project_root: Path, table: ActionTable):
        catalog = ensure_catalog(project_root / 'cache' / 'phase3_expanded_catalog.npz', 'expanded', progress=False)
        counts = catalog.risk_counts[table.catalog_indices].astype(np.float32)
        ref = table.index('0A12A3')
        if ref is None:
            raise ValueError('Phase-4 action table must contain reference 0A12A3')
        return cls(table, counts, ref)

    def all_costs(self, contexts: np.ndarray) -> np.ndarray:
        x = np.asarray(contexts, dtype=np.float32)
        if x.ndim == 2:
            x = x[None, ...]
        feat = quadratic_features(x.reshape(-1, 96), dtype=np.float32)
        costs = feat @ self.selected_counts.T
        return costs.reshape(len(x), 6, self.table.n_actions).astype(np.float64)

    def rewards(self, contexts: np.ndarray, choices: np.ndarray) -> np.ndarray:
        costs = self.all_costs(contexts)
        row = np.arange(len(costs))[:, None]
        check = np.arange(6)[None, :]
        chosen = costs[row, check, np.asarray(choices, dtype=np.int64)]
        reference = costs[:, :, self.reference_action]
        eps = 1e-12
        return np.mean(np.log((reference + eps) / (chosen + eps)), axis=1)

    def local_greedy(self, contexts: np.ndarray) -> np.ndarray:
        return self.all_costs(contexts).argmin(axis=2)


def choices_to_labels(choices: np.ndarray, table: ActionTable) -> tuple[str, ...]:
    return tuple(table.labels[int(x)] for x in choices)


def _exact_rewards(contexts: np.ndarray, choices: np.ndarray, table: ActionTable,
                   reference_labels: tuple[str, ...]) -> np.ndarray:
    ref_risk = round_risk(reference_labels)
    result = np.empty(len(contexts), dtype=np.float64)
    for i, (context, choice) in enumerate(zip(contexts, choices)):
        labels = choices_to_labels(choice, table)
        selected = round_c2(labels, context)
        reference = ref_risk.c2(context)
        result[i] = np.log((reference + 1e-12) / (selected + 1e-12))
    return result


def _returns_for_rollout(reward: np.ndarray, episode_index: np.ndarray) -> np.ndarray:
    return np.asarray(reward, dtype=np.float64)[np.asarray(episode_index, dtype=np.int64)]


def train_one(project_root: Path, table: ActionTable, proxy: ProxyEvaluator, config: dict,
              seed: int, out_dir: Path) -> tuple[RoundActorCritic, RoundFeatureEncoder, dict]:
    rng = np.random.default_rng(seed)
    n_train = int(config['train_contexts'])
    train_contexts = sample_round_contexts(n_train, int(config['data_seed']) + seed * 1009, 'round_train')
    encoder = RoundFeatureEncoder(table)
    encoder.fit(train_contexts)
    model = RoundActorCritic(encoder.n_features, table.n_actions, int(config['hidden']), seed)
    optimizer = Adam(model.params, float(config['learning_rate']))
    batch_size = int(config['proxy_batch'])
    proxy_updates = int(config['proxy_updates'])
    log_every = max(1, int(config.get('log_every', 100)))
    log_rows = []

    for update in range(1, proxy_updates + 1):
        idx = rng.integers(len(train_contexts), size=batch_size)
        batch = train_contexts[idx]
        rollout = rollout_batch(model, encoder, batch, rng, deterministic=False)
        reward = proxy.rewards(batch, rollout.choices)
        returns = _returns_for_rollout(reward, rollout.episode_index)
        loss, grads, entropy, value_loss = model.gradient(
            rollout.features, rollout.actions, returns,
            entropy_coefficient=float(config['entropy']), value_coefficient=float(config['value_coefficient'])
        )
        optimizer.step(model.params, grads)
        if update == 1 or update % log_every == 0 or update == proxy_updates:
            row = {'stage': 'proxy', 'update': update, 'reward': float(reward.mean()),
                   'loss': loss, 'entropy': entropy, 'value_loss': value_loss}
            log_rows.append(row)
            print(f'P4 TRAIN seed={seed} proxy={update}/{proxy_updates} reward={row["reward"]:.3f} entropy={entropy:.3f}')

    # Small exact-C2 fine-tuning stage.  This is intentionally much smaller than
    # proxy pretraining because every terminal reward now performs full-round
    # malignant-pair analysis.
    exact_updates = int(config.get('exact_updates', 0))
    exact_batch = int(config.get('exact_batch', 4))
    reference_labels = ('0A12A3',) * 6
    for update in range(1, exact_updates + 1):
        idx = rng.integers(len(train_contexts), size=exact_batch)
        batch = train_contexts[idx]
        rollout = rollout_batch(model, encoder, batch, rng, deterministic=False)
        reward = _exact_rewards(batch, rollout.choices, table, reference_labels)
        returns = _returns_for_rollout(reward, rollout.episode_index)
        loss, grads, entropy, value_loss = model.gradient(
            rollout.features, rollout.actions, returns,
            entropy_coefficient=float(config['entropy_exact']), value_coefficient=float(config['value_coefficient'])
        )
        optimizer.step(model.params, grads)
        if update == 1 or update % max(1, log_every // 4) == 0 or update == exact_updates:
            row = {'stage': 'exact', 'update': update, 'reward': float(reward.mean()),
                   'loss': loss, 'entropy': entropy, 'value_loss': value_loss}
            log_rows.append(row)
            print(f'P4 TRAIN seed={seed} exact={update}/{exact_updates} reward={row["reward"]:.3f} entropy={entropy:.3f}')

    metadata = {
        'seed': seed, 'n_actions': table.n_actions,
        'proxy_updates': proxy_updates, 'exact_updates': exact_updates,
        'action_table_space': int(table.n_actions ** 6),
    }
    model.save(out_dir / f'phase4_policy_seed{seed}.npz', encoder, metadata)
    with (out_dir / f'phase4_training_seed{seed}.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['stage', 'update', 'reward', 'loss', 'entropy', 'value_loss'])
        writer.writeheader(); writer.writerows(log_rows)
    return model, encoder, metadata


def _exact_costs_for_choice_rows(context: np.ndarray, rows: list[tuple[int, ...]], table: ActionTable) -> np.ndarray:
    return np.asarray([round_c2(choices_to_labels(np.asarray(row), table), context) for row in rows], dtype=np.float64)


def _random_candidates(rng: np.random.Generator, n_actions: int, budget: int) -> list[tuple[int, ...]]:
    seen = set()
    while len(seen) < budget:
        seen.add(tuple(int(x) for x in rng.integers(n_actions, size=6)))
    return list(seen)


def _coordinate_candidates(local_costs: np.ndarray, greedy: np.ndarray, budget: int) -> list[tuple[int, ...]]:
    """Cheap-proxy coordinate neighborhood, truncated to the exact-evaluation budget."""
    candidates = [tuple(int(x) for x in greedy)]
    proposals = []
    base = float(sum(local_costs[c, greedy[c]] for c in range(6)))
    for check in range(6):
        ranked = np.argsort(local_costs[check])
        for action in ranked:
            if int(action) == int(greedy[check]):
                continue
            row = greedy.copy(); row[check] = int(action)
            proxy_total = base - local_costs[check, greedy[check]] + local_costs[check, action]
            proposals.append((float(proxy_total), tuple(int(x) for x in row)))
            if len(proposals) >= budget * 4:
                break
    proposals.sort(key=lambda item: item[0])
    for _, row in proposals:
        if row not in candidates:
            candidates.append(row)
        if len(candidates) >= budget:
            break
    return candidates


def _kind_fractions(choice_rows: list[tuple[int, ...]], table: ActionTable) -> dict:
    counts = {'A_only': 0, 'B_only': 0, 'A_and_B': 0}
    total = 0
    for row in choice_rows:
        for action in row:
            counts[str(table.kinds[int(action)])] += 1
            total += 1
    return {k: v / max(total, 1) for k, v in counts.items()}


def evaluate(project_root: Path, table: ActionTable, proxy: ProxyEvaluator,
             models: list[RoundActorCritic], encoders: list[RoundFeatureEncoder], config: dict,
             out_dir: Path, training_contexts_for_fixed: np.ndarray) -> dict:
    families = list(config['test_families'])
    n_test = int(config['test_contexts'])
    budget = int(config['search_budget'])
    rng = np.random.default_rng(int(config['evaluation_seed']))
    reference_choice = np.full(6, proxy.reference_action, dtype=np.int64)

    # Context-independent proxy-fixed schedule.
    mean_local = proxy.all_costs(training_contexts_for_fixed).mean(axis=0)
    fixed_choice = mean_local.argmin(axis=1)

    results = {}
    case_rows = []
    selected_for_noise = None

    for family_index, family in enumerate(families):
        contexts = sample_round_contexts(n_test, int(config['test_seed']) + 1000 * family_index, family)
        method_costs: dict[str, list[float]] = {
            'reference': [], 'proxy_fixed': [], 'local_greedy': [],
            'random_search': [], 'coordinate_search': [],
        }
        for s in range(len(models)):
            method_costs[f'policy_greedy_seed{s}'] = []
            method_costs[f'policy_beam_seed{s}'] = []
        method_choices: dict[str, list[tuple[int, ...]]] = {k: [] for k in method_costs}

        all_local_costs = proxy.all_costs(contexts)
        greedy_rows = all_local_costs.argmin(axis=2)
        policy_greedy_rows = [greedy_choices(m, e, contexts) for m, e in zip(models, encoders)]

        for ci, context in enumerate(contexts):
            ref_row = tuple(int(x) for x in reference_choice)
            fixed_row = tuple(int(x) for x in fixed_choice)
            local_row = tuple(int(x) for x in greedy_rows[ci])
            for name, row in [('reference', ref_row), ('proxy_fixed', fixed_row), ('local_greedy', local_row)]:
                cost = round_c2(choices_to_labels(np.asarray(row), table), context)
                method_costs[name].append(cost); method_choices[name].append(row)

            random_rows = _random_candidates(rng, table.n_actions, budget)
            random_costs = _exact_costs_for_choice_rows(context, random_rows, table)
            ri = int(np.argmin(random_costs))
            method_costs['random_search'].append(float(random_costs[ri])); method_choices['random_search'].append(random_rows[ri])

            coord_rows = _coordinate_candidates(all_local_costs[ci], greedy_rows[ci].copy(), budget)
            coord_costs = _exact_costs_for_choice_rows(context, coord_rows, table)
            qi = int(np.argmin(coord_costs))
            method_costs['coordinate_search'].append(float(coord_costs[qi])); method_choices['coordinate_search'].append(coord_rows[qi])

            for s, (model, encoder) in enumerate(zip(models, encoders)):
                g_row = tuple(int(x) for x in policy_greedy_rows[s][ci])
                g_cost = round_c2(choices_to_labels(np.asarray(g_row), table), context)
                method_costs[f'policy_greedy_seed{s}'].append(g_cost); method_choices[f'policy_greedy_seed{s}'].append(g_row)

                beam_rows = beam_candidates(model, encoder, context, budget)
                beam_costs = _exact_costs_for_choice_rows(context, beam_rows, table)
                bi = int(np.argmin(beam_costs))
                method_costs[f'policy_beam_seed{s}'].append(float(beam_costs[bi])); method_choices[f'policy_beam_seed{s}'].append(beam_rows[bi])

        # Seed-mean policy metrics for concise reporting.
        reference = np.asarray(method_costs['reference'])
        summary = {}
        for name, values in method_costs.items():
            arr = np.asarray(values, dtype=np.float64)
            summary[name] = {
                'mean_c2': float(arr.mean()), 'median_c2': float(np.median(arr)),
                'mean_improvement_vs_reference_pct': float(100 * np.mean((reference - arr) / np.maximum(reference, 1e-12))),
                'exact_evaluations_per_context': 1 if name in ('reference', 'proxy_fixed', 'local_greedy') or 'policy_greedy' in name else budget,
                'kind_fraction': _kind_fractions(method_choices[name], table),
            }
        for prefix in ('policy_greedy', 'policy_beam'):
            stack = np.stack([np.asarray(method_costs[f'{prefix}_seed{s}']) for s in range(len(models))])
            mean_per_context = stack.mean(axis=0)
            combined_choices = []
            for s in range(len(models)):
                combined_choices.extend(method_choices[f'{prefix}_seed{s}'])
            summary[f'{prefix}_seed_mean'] = {
                'mean_c2': float(mean_per_context.mean()), 'median_c2': float(np.median(mean_per_context)),
                'mean_improvement_vs_reference_pct': float(100 * np.mean((reference - mean_per_context) / np.maximum(reference, 1e-12))),
                'exact_evaluations_per_context': 1 if prefix == 'policy_greedy' else budget,
                'kind_fraction': _kind_fractions(combined_choices, table),
            }

        # Paired search comparisons, averaging policy seeds per context.
        beam_mean = np.stack([np.asarray(method_costs[f'policy_beam_seed{s}']) for s in range(len(models))]).mean(axis=0)
        greedy_mean = np.stack([np.asarray(method_costs[f'policy_greedy_seed{s}']) for s in range(len(models))]).mean(axis=0)
        random_arr = np.asarray(method_costs['random_search'])
        coord_arr = np.asarray(method_costs['coordinate_search'])
        summary['paired'] = {
            'policy_beam_vs_random_win_fraction': float(np.mean(beam_mean < random_arr)),
            'policy_beam_vs_random_mean_c2_change_pct': float(100 * (beam_mean.mean() / random_arr.mean() - 1)),
            'policy_beam_vs_coordinate_win_fraction': float(np.mean(beam_mean < coord_arr)),
            'policy_beam_vs_coordinate_mean_c2_change_pct': float(100 * (beam_mean.mean() / coord_arr.mean() - 1)),
            'policy_greedy_vs_local_greedy_win_fraction': float(np.mean(greedy_mean < np.asarray(method_costs['local_greedy']))),
        }
        results[family] = summary

        for ci in range(n_test):
            for name, values in method_costs.items():
                case_rows.append({'family': family, 'case': ci, 'method': name, 'c2': values[ci]})

        if family == 'round_id' and selected_for_noise is None:
            selected_for_noise = {
                'context': contexts[0],
                'reference': ref_row,
                'local_greedy': method_choices['local_greedy'][0],
                'random_search': method_choices['random_search'][0],
                'coordinate_search': method_choices['coordinate_search'][0],
                'policy_beam': method_choices['policy_beam_seed0'][0],
            }
        print(f'P4 EVAL {family}: beam={summary["policy_beam_seed_mean"]["mean_c2"]:.4g} random={summary["random_search"]["mean_c2"]:.4g} coord={summary["coordinate_search"]["mean_c2"]:.4g}')

    with (out_dir / 'phase4_cases.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['family', 'case', 'method', 'c2']); writer.writeheader(); writer.writerows(case_rows)
    return {'families': results, 'selected_for_noise': selected_for_noise}


def _noise_diagnostics(selected: dict, table: ActionTable, config: dict) -> list[dict]:
    if selected is None:
        return []
    context = selected['context']
    rows = []
    for method in ('reference', 'local_greedy', 'random_search', 'coordinate_search', 'policy_beam'):
        labels = choices_to_labels(np.asarray(selected[method]), table)
        for p in config['noise_p']:
            result = simulate(labels, context, float(p), int(config['noise_shots']),
                              int(config['noise_seed']) + len(rows))
            result.update({'method': method, 'labels': list(labels)})
            rows.append(result)
            print(f'P4 NOISE {method} p={p} failures={result["failures"]}/{result["shots"]}')
    return rows


def _markdown_report(table: ActionTable, verification: dict, evaluation: dict, noise_rows: list[dict], config: dict) -> str:
    lines = [
        '# Phase 4 summary', '',
        'Scope: one noisy full six-check Steane syndrome-extraction round with an explicit flag-aware lookup decoder and ideal initial/final boundaries.', '',
        'The learned model is a proposal policy. Policy-beam and random/coordinate search use the same exact full-round C2 evaluation budget.', '',
        f'- Local action table: {table.n_actions} certified templates ({ {str(k): int(v) for k, v in zip(*np.unique(table.kinds, return_counts=True))} })',
        f'- Full schedule space represented by the action table: {table.n_actions}^6 = {table.n_actions ** 6:,}',
        f'- Exact search budget per context: {config["search_budget"]} complete schedules',
        '- No exhaustive oracle is reported for the full Phase-4 space.', '',
        '## Verification', '',
        f'- Reference round single-fault conflicts: {verification["single_fault_conflicts"]}',
        f'- Reference round single-fault logical failures: {verification["single_fault_logical_failures"]}',
        f'- Reference round single incoming-error failures: {verification["single_incoming_error_failures"]}',
        f'- Reference round elementary fault outcomes: {verification["fault_count"]}',
        f'- Reference round malignant two-fault patterns: {verification["malignant_pair_count"]}', '',
    ]
    for family, summary in evaluation['families'].items():
        lines += [f'## {family}', '', '| Method | Mean C2 | Median C2 | Mean improvement vs reference | Exact full-round evaluations/context |',
                  '|---|---:|---:|---:|---:|']
        order = ['reference', 'proxy_fixed', 'local_greedy', 'random_search', 'coordinate_search',
                 'policy_greedy_seed_mean', 'policy_beam_seed_mean']
        for name in order:
            row = summary[name]
            lines.append(f'| {name} | {row["mean_c2"]:.6f} | {row["median_c2"]:.6f} | {row["mean_improvement_vs_reference_pct"]:.2f}% | {row["exact_evaluations_per_context"]} |')
        p = summary['paired']
        beam_kinds = summary['policy_beam_seed_mean']['kind_fraction']
        local_kinds = summary['local_greedy']['kind_fraction']
        lines += ['', f'- Policy-beam vs random: win fraction {100*p["policy_beam_vs_random_win_fraction"]:.1f}%; mean C2 change {p["policy_beam_vs_random_mean_c2_change_pct"]:.2f}%.',
                  f'- Policy-beam vs coordinate search: win fraction {100*p["policy_beam_vs_coordinate_win_fraction"]:.1f}%; mean C2 change {p["policy_beam_vs_coordinate_mean_c2_change_pct"]:.2f}%.',
                  f'- Policy-beam local-template mix: A-only {100*beam_kinds["A_only"]:.1f}%, B-only {100*beam_kinds["B_only"]:.1f}%, A+B {100*beam_kinds["A_and_B"]:.1f}%.',
                  f'- Local-greedy template mix: A-only {100*local_kinds["A_only"]:.1f}%, B-only {100*local_kinds["B_only"]:.1f}%, A+B {100*local_kinds["A_and_B"]:.1f}%.', '']

    lines += ['## Finite-p logical-memory diagnostics', '',
              'These rows use one predeclared `round_id` synthetic calibration. They are one-round memory experiments with an explicit decoder and ideal boundaries.', '',
              '| Method | p | failures/shots | logical failure rate | Wilson 95% interval |',
              '|---|---:|---:|---:|---:|']
    for row in noise_rows:
        lines.append(f'| {row["method"]} | {row["p"]} | {row["failures"]}/{row["shots"]} | {row["logical_failure_rate"]:.7f} | [{row["wilson95_low"]:.7f}, {row["wilson95_high"]:.7f}] |')
    lines += ['', '## Interpretation constraints', '',
              '- Ideal boundaries are used, analogous to a one-round memory experiment; this is not repeated fault-tolerant QEC.',
              '- The decoder is schedule-specific and built from all single-fault signatures; it is not PyMatching or a scalable general decoder.',
              '- Checks are serialized in X0,X1,X2,Z0,Z1,Z2 order; idle noise and hardware timing/connectivity are not modeled.',
              '- Calibration families are synthetic stress tests, not measured device data.',
              '- The 48-template local action table is an offline-pruned subset of the 4,896 Phase-3-certified templates.',
              '- C2 is a second-order logical-failure coefficient; finite-p diagnostics are separate Monte Carlo estimates.',
              '- FastSched (Ye, Pabla, Palsberg, 2026) already establishes RL for syndrome-extraction scheduling; Phase 4 instead tests calibration-conditioned flag-template proposals under a bounded exact-evaluation budget.', '']
    return '\n'.join(lines)


def run_all(project_root: Path, config: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    table = ensure_action_table(project_root)
    proxy = ProxyEvaluator.build(project_root, table)
    reference_labels = ('0A12A3',) * 6
    verification = verification_summary(reference_labels)
    if any(verification[k] for k in ('single_fault_conflicts', 'single_fault_logical_failures', 'single_incoming_error_failures')):
        raise RuntimeError(f'Phase-4 reference verification failed: {verification}')

    seeds = [int(x) for x in config['training_seeds']]
    models, encoders = [], []
    for seed in seeds:
        model, encoder, _ = train_one(project_root, table, proxy, config, seed, out_dir)
        models.append(model); encoders.append(encoder)

    fixed_contexts = sample_round_contexts(int(config['train_contexts']), int(config['data_seed']), 'round_train')
    evaluation = evaluate(project_root, table, proxy, models, encoders, config, out_dir, fixed_contexts)
    noise_rows = _noise_diagnostics(evaluation.pop('selected_for_noise'), table, config)
    payload = {
        'config': config,
        'action_table': table.metadata | {'labels': table.labels, 'kinds': table.kinds.tolist()},
        'verification': verification,
        'evaluation': evaluation,
        'noise': noise_rows,
        'elapsed_seconds': time.perf_counter() - start,
    }
    (out_dir / 'phase4_results.json').write_text(json.dumps(payload, indent=2) + '\n')
    report = _markdown_report(table, verification, evaluation, noise_rows, config)
    (out_dir / 'phase4_summary.md').write_text(report + '\n')
    print(f'PHASE 4 REPORT: {out_dir / "phase4_summary.md"}')
    return payload
