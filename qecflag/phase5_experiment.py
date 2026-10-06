"""Training/evaluation pipeline for Phase-5 hardware-aware proposal search."""
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
from .phase4_agent import RoundActorCritic
from .phase4_simulation import simulate as logical_simulate
from .phase5_actions import HardwareActionTable, ensure_hardware_action_table, actions_to_round
from .phase5_agent import rollout_batch, greedy_choices, beam_candidates
from .phase5_env import HardwareFeatureEncoder
from .phase5_hardware import (
    HardwareContext, hardware_round_metrics, local_hardware_effective_context,
    hardware_effective_context, topology_summary, build_local_route_cache,
)
from .phase5_noise import sample_hardware_contexts


@dataclass
class HardwareProxyEvaluator:
    table: HardwareActionTable
    risk_counts: np.ndarray
    reference_action: int

    @classmethod
    def build(cls, project_root: Path, table: HardwareActionTable):
        catalog = ensure_catalog(project_root / 'cache' / 'phase3_expanded_catalog.npz', 'expanded', progress=False)
        base_indices = table.phase4.catalog_indices[table.template_indices]
        counts = catalog.risk_counts[base_indices].astype(np.float32)
        ref = table.index('H0|0A12A3')
        if ref is None:
            raise ValueError('Hardware table must contain H0|0A12A3')
        return cls(table, counts, ref)

    def all_costs(self, batch) -> np.ndarray:
        out = np.empty((len(batch), 6, self.table.n_actions), dtype=np.float64)
        for i in range(len(batch)):
            context = batch.context(i)
            route_cache = build_local_route_cache(context)
            for check in range(6):
                for action in range(self.table.n_actions):
                    label = self.table.template_label(action)
                    hub = self.table.hub(action)
                    eff, _ = local_hardware_effective_context(check, label, hub, context, route_cache=route_cache)
                    feat = quadratic_features(eff[None, :], dtype=np.float32)[0]
                    out[i, check, action] = float(feat @ self.risk_counts[action])
        return out

    def local_greedy_from_costs(self, costs: np.ndarray) -> np.ndarray:
        return np.asarray(costs).argmin(axis=2)

    def rewards_from_costs(self, costs: np.ndarray, choices: np.ndarray) -> np.ndarray:
        row = np.arange(len(costs))[:, None]
        check = np.arange(6)[None, :]
        chosen = costs[row, check, np.asarray(choices, dtype=np.int64)]
        reference = costs[:, :, self.reference_action]
        return np.mean(np.log((reference + 1e-12) / (chosen + 1e-12)), axis=1)


def _save_model(model: RoundActorCritic, encoder: HardwareFeatureEncoder, path: Path, metadata: dict) -> None:
    np.savez_compressed(path, **model.params, feature_mean=encoder.mean, feature_scale=encoder.scale,
                        metadata=np.asarray(json.dumps(metadata)))


def _returns(reward: np.ndarray, episode_index: np.ndarray) -> np.ndarray:
    return np.asarray(reward)[np.asarray(episode_index, dtype=np.int64)]


def _exact_cost(actions, table: HardwareActionTable, context: HardwareContext):
    labels, hubs = actions_to_round(actions, table)
    return hardware_round_metrics(labels, hubs, context)


def _exact_rewards(batch, choices: np.ndarray, table: HardwareActionTable, reference_actions: tuple[int, ...]) -> np.ndarray:
    result = np.empty(len(batch), dtype=np.float64)
    for i in range(len(batch)):
        c = batch.context(i)
        selected = _exact_cost(choices[i], table, c).c2
        reference = _exact_cost(reference_actions, table, c).c2
        result[i] = np.log((reference + 1e-12) / (selected + 1e-12))
    return result


def train_one(project_root: Path, table: HardwareActionTable, proxy: HardwareProxyEvaluator,
              config: dict, seed: int, out_dir: Path, train=None, proxy_costs=None):
    rng = np.random.default_rng(seed)
    if train is None:
        train = sample_hardware_contexts(int(config['train_contexts']), int(config['data_seed']), 'hw_train')
    encoder = HardwareFeatureEncoder(table); encoder.fit(train)
    model = RoundActorCritic(encoder.n_features, table.n_actions, int(config['hidden']), seed)
    optimizer = Adam(model.params, float(config['learning_rate']))
    if proxy_costs is None:
        proxy_costs = proxy.all_costs(train)
    log_rows = []
    log_every = max(1, int(config.get('log_every', 100)))

    for update in range(1, int(config['proxy_updates']) + 1):
        idx = rng.integers(len(train), size=int(config['proxy_batch']))
        batch = train.take(idx)
        rollout = rollout_batch(model, encoder, batch, rng)
        reward = proxy.rewards_from_costs(proxy_costs[idx], rollout.choices)
        loss, grads, entropy, value_loss = model.gradient(
            rollout.features, rollout.actions, _returns(reward, rollout.episode_index),
            entropy_coefficient=float(config['entropy']), value_coefficient=float(config['value_coefficient'])
        )
        optimizer.step(model.params, grads)
        if update == 1 or update % log_every == 0 or update == int(config['proxy_updates']):
            log_rows.append({'stage':'proxy','update':update,'reward':float(reward.mean()),'loss':loss,'entropy':entropy,'value_loss':value_loss})
            print(f'P5 TRAIN seed={seed} proxy={update}/{config["proxy_updates"]} reward={reward.mean():.3f} entropy={entropy:.3f}')

    ref = tuple([proxy.reference_action] * 6)
    exact_updates = int(config.get('exact_updates', 0))
    for update in range(1, exact_updates + 1):
        idx = rng.integers(len(train), size=int(config.get('exact_batch', 2)))
        batch = train.take(idx)
        rollout = rollout_batch(model, encoder, batch, rng)
        reward = _exact_rewards(batch, rollout.choices, table, ref)
        loss, grads, entropy, value_loss = model.gradient(
            rollout.features, rollout.actions, _returns(reward, rollout.episode_index),
            entropy_coefficient=float(config['entropy_exact']), value_coefficient=float(config['value_coefficient'])
        )
        optimizer.step(model.params, grads)
        if update == 1 or update % max(1, log_every // 4) == 0 or update == exact_updates:
            log_rows.append({'stage':'exact','update':update,'reward':float(reward.mean()),'loss':loss,'entropy':entropy,'value_loss':value_loss})
            print(f'P5 TRAIN seed={seed} exact={update}/{exact_updates} reward={reward.mean():.3f} entropy={entropy:.3f}')

    metadata = {'seed':seed,'n_actions':table.n_actions,'schedule_space':int(table.n_actions ** 6),
                'proxy_updates':int(config['proxy_updates']),'exact_updates':exact_updates}
    _save_model(model, encoder, out_dir / f'phase5_policy_seed{seed}.npz', metadata)
    with (out_dir / f'phase5_training_seed{seed}.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['stage','update','reward','loss','entropy','value_loss']); w.writeheader(); w.writerows(log_rows)
    return model, encoder, metadata


def _random_candidates(rng, n_actions: int, budget: int):
    seen = set()
    while len(seen) < budget:
        seen.add(tuple(int(x) for x in rng.integers(n_actions, size=6)))
    return list(seen)


def _coordinate_candidates(local_costs: np.ndarray, greedy: np.ndarray, budget: int):
    candidates = [tuple(int(x) for x in greedy)]
    proposals = []
    base = float(sum(local_costs[c, greedy[c]] for c in range(6)))
    for check in range(6):
        ranked = np.argsort(local_costs[check])
        for action in ranked[:min(len(ranked), budget + 4)]:
            if int(action) == int(greedy[check]):
                continue
            row = greedy.copy(); row[check] = int(action)
            score = base - local_costs[check, greedy[check]] + local_costs[check, action]
            proposals.append((float(score), tuple(int(x) for x in row)))
    proposals.sort(key=lambda x: x[0])
    for _, row in proposals:
        if row not in candidates:
            candidates.append(row)
        if len(candidates) >= budget:
            break
    return candidates


def _routing_heuristic(context: HardwareContext, table: HardwareActionTable) -> tuple[int, ...]:
    """No logical C2: minimize native-CX count, then duration per check."""
    rows = []
    for check in range(6):
        best = None
        for action in range(table.n_actions):
            label = table.template_label(action); hub = table.hub(action)
            _eff, d = local_hardware_effective_context(check, label, hub, context)
            key = (d['native_cx'], d['duration_ns'], action)
            if best is None or key < best[0]:
                best = (key, action)
        rows.append(best[1])
    return tuple(rows)


def _summarize_metrics(metrics):
    c2 = np.asarray([m.c2 for m in metrics])
    cx = np.asarray([m.native_cx for m in metrics])
    dur = np.asarray([m.duration_ns for m in metrics])
    hub0 = np.asarray([m.hub0_fraction for m in metrics])
    two = np.asarray([m.two_flag_fraction for m in metrics])
    return {
        'mean_c2': float(c2.mean()), 'median_c2': float(np.median(c2)),
        'mean_native_cx': float(cx.mean()), 'mean_duration_us': float(dur.mean()/1000.0),
        'hub0_fraction': float(hub0.mean()), 'two_flag_fraction': float(two.mean()),
    }


def evaluate(project_root: Path, table: HardwareActionTable, proxy: HardwareProxyEvaluator,
             models, encoders, config: dict, out_dir: Path, fixed_train_batch) -> dict:
    budget = int(config['search_budget'])
    rng = np.random.default_rng(int(config['evaluation_seed']))
    train_costs = proxy.all_costs(fixed_train_batch)
    fixed = tuple(int(x) for x in train_costs.mean(axis=0).argmin(axis=1))
    reference = tuple([proxy.reference_action] * 6)
    results = {}; case_rows = []; selected = None

    for fi, family in enumerate(config['test_families']):
        batch = sample_hardware_contexts(int(config['test_contexts']), int(config['test_seed']) + fi*1000, family)
        local_costs_all = proxy.all_costs(batch)
        local_rows = local_costs_all.argmin(axis=2)
        policy_rows = [greedy_choices(m,e,batch) for m,e in zip(models,encoders)]
        metrics = {name: [] for name in ('reference','proxy_fixed','routing_heuristic','local_greedy','random_search','coordinate_search')}
        choices = {name: [] for name in metrics}
        for s in range(len(models)):
            metrics[f'policy_greedy_seed{s}']=[]; metrics[f'policy_beam_seed{s}']=[]
            choices[f'policy_greedy_seed{s}']=[]; choices[f'policy_beam_seed{s}']=[]

        for i in range(len(batch)):
            c = batch.context(i)
            basic = {
                'reference': reference,
                'proxy_fixed': fixed,
                'routing_heuristic': _routing_heuristic(c, table),
                'local_greedy': tuple(int(x) for x in local_rows[i]),
            }
            for name,row in basic.items():
                metrics[name].append(_exact_cost(row,table,c)); choices[name].append(row)

            rand_rows = _random_candidates(rng, table.n_actions, budget)
            rand_m = [_exact_cost(row,table,c) for row in rand_rows]
            j = int(np.argmin([m.c2 for m in rand_m])); metrics['random_search'].append(rand_m[j]); choices['random_search'].append(rand_rows[j])

            coord_rows = _coordinate_candidates(local_costs_all[i], local_rows[i].copy(), budget)
            coord_m = [_exact_cost(row,table,c) for row in coord_rows]
            j = int(np.argmin([m.c2 for m in coord_m])); metrics['coordinate_search'].append(coord_m[j]); choices['coordinate_search'].append(coord_rows[j])

            for s,(model,encoder) in enumerate(zip(models,encoders)):
                grow = tuple(int(x) for x in policy_rows[s][i])
                metrics[f'policy_greedy_seed{s}'].append(_exact_cost(grow,table,c)); choices[f'policy_greedy_seed{s}'].append(grow)
                brows = beam_candidates(model,encoder,c,budget)
                bm = [_exact_cost(row,table,c) for row in brows]
                j = int(np.argmin([m.c2 for m in bm])); metrics[f'policy_beam_seed{s}'].append(bm[j]); choices[f'policy_beam_seed{s}'].append(brows[j])

        summary = {name: _summarize_metrics(vals) for name,vals in metrics.items()}
        for prefix in ('policy_greedy','policy_beam'):
            # Per-context seed mean for C2, and aggregate physical metrics across all seeds.
            c2stack = np.stack([[m.c2 for m in metrics[f'{prefix}_seed{s}']] for s in range(len(models))])
            flat = [m for s in range(len(models)) for m in metrics[f'{prefix}_seed{s}']]
            phys = _summarize_metrics(flat)
            phys['mean_c2'] = float(c2stack.mean(axis=0).mean())
            phys['median_c2'] = float(np.median(c2stack.mean(axis=0)))
            summary[f'{prefix}_seed_mean'] = phys

        beam = np.stack([[m.c2 for m in metrics[f'policy_beam_seed{s}']] for s in range(len(models))]).mean(axis=0)
        random = np.asarray([m.c2 for m in metrics['random_search']])
        coord = np.asarray([m.c2 for m in metrics['coordinate_search']])
        local = np.asarray([m.c2 for m in metrics['local_greedy']])
        summary['paired'] = {
            'beam_vs_random_win_fraction': float(np.mean(beam < random)),
            'beam_vs_random_mean_change_pct': float(100*(beam.mean()/random.mean()-1)),
            'beam_vs_coordinate_win_fraction': float(np.mean(beam < coord)),
            'beam_vs_coordinate_mean_change_pct': float(100*(beam.mean()/coord.mean()-1)),
            'beam_vs_local_win_fraction': float(np.mean(beam < local)),
        }
        results[family]=summary
        for i in range(len(batch)):
            for name, vals in metrics.items():
                case_rows.append({'family':family,'case':i,'method':name,'c2':vals[i].c2,
                                  'native_cx':vals[i].native_cx,'duration_ns':vals[i].duration_ns})
        if family == 'hw_id' and selected is None:
            selected = {'context': batch.context(0)}
            for name in ('reference','local_greedy','random_search','coordinate_search','routing_heuristic'):
                selected[name]=choices[name][0]
            selected['policy_beam']=choices['policy_beam_seed0'][0]
        print(f'P5 EVAL {family}: beam={summary["policy_beam_seed_mean"]["mean_c2"]:.4g} random={summary["random_search"]["mean_c2"]:.4g} coord={summary["coordinate_search"]["mean_c2"]:.4g} local={summary["local_greedy"]["mean_c2"]:.4g}')

    with (out_dir/'phase5_cases.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['family','case','method','c2','native_cx','duration_ns']); w.writeheader(); w.writerows(case_rows)
    return {'families':results,'selected_for_noise':selected}


def _noise_diagnostics(selected, table: HardwareActionTable, config: dict):
    if selected is None: return []
    c = selected['context']; rows=[]
    for name in ('reference','routing_heuristic','local_greedy','random_search','coordinate_search','policy_beam'):
        labels,hubs = actions_to_round(selected[name],table)
        eff, details = hardware_effective_context(labels,hubs,c)
        for p in config['noise_p']:
            result = logical_simulate(labels,eff,float(p),int(config['noise_shots']),int(config['noise_seed'])+len(rows))
            result.update({'method':name,'labels':list(labels),'hubs':list(hubs),'native_cx':details['native_cx'],'duration_ns':details['duration_ns'],
                           'scope_note':'Monte Carlo on schedule-dependent effective logical fault weights; inserted routing CXs are not individually fault-enumerated.'})
            rows.append(result)
            print(f'P5 NOISE {name} p={p} failures={result["failures"]}/{result["shots"]}')
    return rows


def _markdown(table, evaluation, noise, config):
    lines=['# Phase 5 summary','',
           'Scope: hardware-aware proposal search for one noisy six-check Steane extraction round on a fixed synthetic 12-node nearest-neighbour graph.','',
           'Hardware routing and timing are represented by schedule-dependent effective logical fault weights. Inserted native routing gates are counted and timed, but not individually fault-enumerated. Lower hardware-aware C2 is better.','',
           f'- Hardware actions/check: {table.n_actions} = 48 certified local templates x 2 syndrome-hub placements',
           f'- Full schedule space: {table.n_actions}^6 = {table.n_actions**6:,}',
           f'- Exact hardware-aware C2 evaluation budget for random/coordinate/policy-beam: {config["search_budget"]} complete schedules/context','',
           '## Topology','', '```json', json.dumps(topology_summary(),indent=2), '```','']
    order=['reference','proxy_fixed','routing_heuristic','local_greedy','random_search','coordinate_search','policy_greedy_seed_mean','policy_beam_seed_mean']
    for family,s in evaluation['families'].items():
        lines += [f'## {family}','', '| Method | Mean C2 | Median C2 | Mean native CX | Mean duration (us) | Hub-0 use | Two-flag use |',
                  '|---|---:|---:|---:|---:|---:|---:|']
        for name in order:
            r=s[name]
            lines.append(f'| {name} | {r["mean_c2"]:.6f} | {r["median_c2"]:.6f} | {r["mean_native_cx"]:.1f} | {r["mean_duration_us"]:.3f} | {100*r["hub0_fraction"]:.1f}% | {100*r["two_flag_fraction"]:.1f}% |')
        p=s['paired']
        lines += ['', f'- Policy-beam vs random: win fraction {100*p["beam_vs_random_win_fraction"]:.1f}%; mean C2 change {p["beam_vs_random_mean_change_pct"]:.2f}%.',
                  f'- Policy-beam vs coordinate: win fraction {100*p["beam_vs_coordinate_win_fraction"]:.1f}%; mean C2 change {p["beam_vs_coordinate_mean_change_pct"]:.2f}%.',
                  f'- Policy-beam vs one-evaluation hardware local-greedy: win fraction {100*p["beam_vs_local_win_fraction"]:.1f}%.','']
    lines += ['## Finite-p reduced hardware diagnostics','',
              'These use one predeclared `hw_id` context. The schedule is first converted to effective logical fault weights; the reduced logical Monte Carlo is then run.','',
              '| Method | p | failures/shots | logical failure rate | 95% interval | native CX | duration (us) |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for r in noise:
        lines.append(f'| {r["method"]} | {r["p"]} | {r["failures"]}/{r["shots"]} | {r["logical_failure_rate"]:.7f} | [{r["wilson95_low"]:.7f}, {r["wilson95_high"]:.7f}] | {r["native_cx"]} | {r["duration_ns"]/1000:.3f} |')
    lines += ['', '## Interpretation constraints','',
              '- The 12-node graph and calibration families are synthetic controlled stress tests, not a named processor or measured backend.',
              '- Remote logical CNOTs use a SWAP-forward / CNOT / SWAP-back count-and-duration model. Routing-gate faults are collapsed into effective logical-location weights rather than explicitly propagated gate by gate.',
              '- Persistent data-qubit idle exposure is modeled approximately and folded into logical data-CNOT Pauli weights.',
              '- Checks remain serialized in X0,X1,X2,Z0,Z1,Z2 order; Phase 5 adds placement/routing/timing context but not parallel scheduling.',
              '- The decoder and ideal boundaries are inherited from Phase 4; this is still a one-round experiment, not repeated fault-tolerant memory.',
              '- A positive learned-search result would motivate explicit native-circuit fault simulation and repeated rounds; it would not establish hardware advantage.','']
    return '\n'.join(lines)


def run_all(project_root: Path, config: dict, out_dir: Path):
    out_dir.mkdir(parents=True,exist_ok=False); start=time.perf_counter()
    table=ensure_hardware_action_table(project_root); proxy=HardwareProxyEvaluator.build(project_root,table)
    fixed_train=sample_hardware_contexts(int(config['train_contexts']),int(config['data_seed']),'hw_train')
    shared_proxy_costs=proxy.all_costs(fixed_train)
    models=[]; encoders=[]
    for seed in [int(x) for x in config['training_seeds']]:
        m,e,_=train_one(project_root,table,proxy,config,seed,out_dir,train=fixed_train,proxy_costs=shared_proxy_costs); models.append(m); encoders.append(e)
    evaluation=evaluate(project_root,table,proxy,models,encoders,config,out_dir,fixed_train)
    noise=_noise_diagnostics(evaluation.pop('selected_for_noise'),table,config)
    payload={'config':config,'topology':topology_summary(),'action_count':table.n_actions,'schedule_space':int(table.n_actions**6),
             'evaluation':evaluation,'noise':noise,'elapsed_seconds':time.perf_counter()-start}
    (out_dir/'phase5_results.json').write_text(json.dumps(payload,indent=2)+'\n')
    (out_dir/'phase5_summary.md').write_text(_markdown(table,evaluation,noise,config)+'\n')
    print(f'PHASE 5 REPORT: {out_dir/"phase5_summary.md"}')
    return payload
