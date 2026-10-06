"""Benchmark the counterexample-guided FT compiler repair fork."""
from __future__ import annotations

from pathlib import Path
import csv, json, time
from collections import Counter
import numpy as np

from qecflag.phase5_actions import ensure_hardware_action_table
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase7_routing import bridge_native_risk
from qecflag.phase10_scheduler import schedule_parallel, certify_parallel_schedule

from .routing_repair import logical_round_is_single_fault_ft, repair_routing
from .schedule_repair import repair_parallel_schedule


def _save_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('')
        return
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def _candidate_injections(project_root: Path, context, count: int) -> list[dict]:
    """Create controlled logically-FT/physically-unsafe compiler choices.

    Start from certified rounds and replace one local lowering choice by another
    Phase-4-certified action.  Keep only cases where the logical verifier still
    passes but bridge routing fails.  The injected check gives a known locality
    target without being exposed to the repair engine.
    """
    cat = ensure_catalog(project_root, progress=False)
    table = ensure_hardware_action_table(project_root)
    out = []
    # Spread injections across checks and different safe bases.
    for case_idx in range(max(count * 3, 6)):
        base_idx = case_idx % min(len(cat), max(1, count))
        labels, hubs = cat.labels_hubs(base_idx)
        ci = case_idx % 6
        found = None
        for action in range(table.n_actions):
            nl = list(labels); nh = list(hubs)
            nl[ci] = table.template_label(action); nh[ci] = table.hub(action)
            if nl[ci] == labels[ci] and int(nh[ci]) == int(hubs[ci]):
                continue
            if not logical_round_is_single_fault_ft(nl):
                continue
            risk = bridge_native_risk(nl, nh, context, compute_c2=False)
            passed = bool(
                risk.c1 == 0.0 and risk.decoder.single_fault_conflicts == 0
                and risk.decoder.single_fault_failures == 0 and risk.decoder.incoming_failures == 0
            )
            if not passed:
                found = {
                    'case': len(out), 'base_catalog_index': int(base_idx),
                    'injected_check': int(ci), 'injected_action': int(action),
                    'injected_hardware_label': table.labels[action],
                    'labels': list(nl), 'hubs': list(nh),
                    'base_labels': list(labels), 'base_hubs': list(hubs),
                    'bridge_c1_before_repair': float(risk.c1),
                }
                break
        if found is not None:
            sig = (tuple(found['labels']), tuple(found['hubs']))
            if all((tuple(x['labels']), tuple(x['hubs'])) != sig for x in out):
                out.append(found)
        if len(out) >= int(count):
            break
    return out


def _markdown(payload: dict) -> str:
    lines = ['# FT compiler repair fork summary', '',
             'Scope: exact single-fault counterexample detection, localization, and deterministic repair of compiler-introduced FT violations in the existing Steane/synthetic-hardware model.', '',
             'Safety is lexicographic: a repair is accepted only if C1=0 with zero single-fault conflicts/failures and zero incoming-single-error failures.', '']
    for fam, f in payload['families'].items():
        lines += [f'## {fam}', '']
        rr = f['routing']
        lines += [
            '### Routing/lowering repair', '',
            f"- Cases: {rr['cases']}",
            f"- Repair success: {rr['success_rate']*100:.1f}%",
            f"- Mean exact verifier calls: {rr['mean_verifier_calls']:.2f}",
            f"- Mean changed checks on successful repairs: {rr['mean_changed_checks']:.2f}",
            f"- Injected check recovered among changed checks: {rr['localization_hit_rate']*100:.1f}%",
            f"- Mean initial SWAP C1: {rr['mean_initial_swap_c1']:.6g}",
            f"- Mean final C1: {rr['mean_final_c1']:.6g}", '',
        ]
        sr = f['scheduling']
        lines += [
            '### Parallel-schedule repair', '',
            f"- Cases: {sr['cases']}",
            f"- Repair success: {sr['success_rate']*100:.1f}%",
            f"- Mean precedence constraints added: {sr['mean_constraints']:.2f}",
            f"- Mean exact verifier calls: {sr['mean_verifier_calls']:.2f}",
            f"- Repaired schedules retaining native-CX parallelism: {sr['parallel_safe_fraction']*100:.1f}%",
            f"- Mean repaired speedup vs serialized: {sr['mean_speedup_vs_serial_percent']:.2f}%",
            f"- Mean repaired speedup vs safe ancilla-overlap fallback: {sr['mean_speedup_vs_ancilla_percent']:.2f}%", '',
        ]
    a = payload['aggregate']
    lines += ['## Aggregate', '',
              f"- Routing repair success: {a['routing_success_rate']*100:.1f}%",
              f"- Scheduling repair success: {a['scheduling_success_rate']*100:.1f}%",
              f"- Safe repaired schedules with true CX concurrency: {a['parallel_safe_fraction']*100:.1f}%",
              '', '## Interpretation constraints', '',
              '- This is a deterministic counterexample-guided repair prototype, not an ML phase.',
              '- The benchmark still uses the Steane code, the synthetic 12-node graph, and the existing Pauli/Clifford fault model.',
              '- Routing repair cases are controlled compiler-choice injections: the logical circuit remains single-fault FT before physical lowering.',
              '- Scheduling repair adds check-pair precedence constraints suggested by exact failing physical-fault witnesses.',
              '- A successful repair demonstrates recovery of the modeled first-order FT guarantee; it does not establish general compiler completeness or device-level FT.',
              ]
    return '\n'.join(lines)


def run_all(project_root: Path, cfg: dict, out_dir: Path):
    root = Path(project_root); out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    families = list(cfg.get('families', ['hw_id', 'ood_hub0_bad', 'ood_logical_shift']))
    nctx = int(cfg.get('contexts_per_family', 1))
    routing_cases_n = int(cfg.get('routing_cases', 4))
    scheduling_cases_n = int(cfg.get('scheduling_cases', 4))
    schedule_method = str(cfg.get('schedule_method', 'asap'))
    max_edits = int(cfg.get('routing_max_edits', 2))
    max_calls = int(cfg.get('routing_max_verifier_calls', 24))
    max_constraints = int(cfg.get('schedule_max_constraints', 15))
    seed = int(cfg.get('seed', 11101))

    cat = ensure_catalog(root, progress=False)
    # Physical single-fault safety is structural for the strictly-positive
    # synthetic weights used here, so controlled unsafe injections are located
    # once at a nominal context and reused across calibration families.
    injection_context = sample_hardware_contexts(1, seed + 777, 'hw_id').context(0)
    injections = _candidate_injections(root, injection_context, routing_cases_n)
    family_payload = {}
    routing_rows: list[dict] = []
    scheduling_rows: list[dict] = []

    for fi, fam in enumerate(families):
        batch = sample_hardware_contexts(nctx, seed + 1000 * fi, fam)
        fam_r = []; fam_s = []
        for ci in range(nctx):
            ctx = batch.context(ci)
            for case in injections:
                r = repair_routing(
                    root, case['labels'], case['hubs'], ctx,
                    max_edits=max_edits, max_verifier_calls=max_calls,
                    witness_check_limit=int(cfg.get('witness_check_limit', 2)),
                )
                final_c1 = float(r.final_bridge.c1) if r.final_bridge is not None else float('nan')
                row = {
                    'family': fam, 'context': ci, 'case': case['case'],
                    'injected_check': case['injected_check'],
                    'success': int(r.success), 'verifier_calls': r.verifier_calls,
                    'changed_checks': len(r.changed_checks),
                    'localization_hit': int(case['injected_check'] in r.changed_checks),
                    'initial_swap_c1': r.initial_swap.c1,
                    'initial_bridge_c1': r.initial_bridge.c1,
                    'final_c1': final_c1,
                    'initial_swap_native_cx': r.initial_swap.native_cx,
                    'final_native_cx': r.final_bridge.native_cx if r.final_bridge else '',
                    'final_proxy_c2': r.final_proxy_c2 if r.final_proxy_c2 is not None else '',
                    'injected_hardware_label': case['injected_hardware_label'],
                    'repaired_labels': '|'.join(r.repaired_labels) if r.repaired_labels else '',
                    'repaired_hubs': ''.join(str(x) for x in r.repaired_hubs) if r.repaired_hubs else '',
                }
                fam_r.append(row); routing_rows.append(row)
                print(f"REPAIR routing {fam} ctx={ci} case={case['case']} success={r.success} calls={r.verifier_calls} edits={len(r.changed_checks)}")

            for si in range(min(scheduling_cases_n, len(cat))):
                labels, hubs = cat.labels_hubs(si)
                serial = schedule_parallel(labels, hubs, ctx, 'serialized')
                anc = schedule_parallel(labels, hubs, ctx, 'ancilla_overlap')
                c_serial = certify_parallel_schedule(serial, ctx)
                c_anc = certify_parallel_schedule(anc, ctx)
                if not c_serial.passed or not c_anc.passed:
                    raise RuntimeError('certified catalog regression: safe fallback failed')
                r = repair_parallel_schedule(
                    labels, hubs, ctx, schedule_method,
                    max_constraints=max_constraints,
                )
                final_dur = float(r.final_duration_ns) if r.final_duration_ns is not None else float('nan')
                speed_serial = (1.0 - final_dur / serial.duration_ns) * 100.0 if r.success else float('nan')
                speed_anc = (1.0 - final_dur / anc.duration_ns) * 100.0 if r.success else float('nan')
                row = {
                    'family': fam, 'context': ci, 'case': si, 'method': schedule_method,
                    'success': int(r.success), 'verifier_calls': r.verifier_calls,
                    'constraints': len(r.constraints), 'initial_c1': r.initial_c1,
                    'final_c1': r.final_c1 if r.final_c1 is not None else '',
                    'initial_duration_us': r.initial_duration_ns / 1000.0,
                    'final_duration_us': final_dur / 1000.0 if r.success else '',
                    'serialized_duration_us': serial.duration_ns / 1000.0,
                    'ancilla_overlap_duration_us': anc.duration_ns / 1000.0,
                    'speedup_vs_serial_percent': speed_serial,
                    'speedup_vs_ancilla_percent': speed_anc,
                    'initial_max_parallel_cx': r.initial_max_parallel_cx,
                    'final_max_parallel_cx': r.final_max_parallel_cx if r.final_max_parallel_cx is not None else '',
                    'retains_cx_parallelism': int(r.success and int(r.final_max_parallel_cx or 0) > 1),
                }
                fam_s.append(row); scheduling_rows.append(row)
                print(f"REPAIR schedule {fam} ctx={ci} case={si} success={r.success} constraints={len(r.constraints)} maxcx={r.final_max_parallel_cx}")

        def mean(rows, key, success_only=False):
            vals=[]
            for x in rows:
                if success_only and not x['success']: continue
                v=x[key]
                if v=='' or not np.isfinite(float(v)): continue
                vals.append(float(v))
            return float(np.mean(vals)) if vals else float('nan')
        routing_success = float(np.mean([x['success'] for x in fam_r])) if fam_r else float('nan')
        schedule_success = float(np.mean([x['success'] for x in fam_s])) if fam_s else float('nan')
        family_payload[fam] = {
            'routing': {
                'cases': len(fam_r), 'success_rate': routing_success,
                'mean_verifier_calls': mean(fam_r,'verifier_calls'),
                'mean_changed_checks': mean(fam_r,'changed_checks',True),
                'localization_hit_rate': mean(fam_r,'localization_hit',True),
                'mean_initial_swap_c1': mean(fam_r,'initial_swap_c1'),
                'mean_final_c1': mean(fam_r,'final_c1',True),
            },
            'scheduling': {
                'cases': len(fam_s), 'success_rate': schedule_success,
                'mean_constraints': mean(fam_s,'constraints',True),
                'mean_verifier_calls': mean(fam_s,'verifier_calls'),
                'parallel_safe_fraction': mean(fam_s,'retains_cx_parallelism',True),
                'mean_speedup_vs_serial_percent': mean(fam_s,'speedup_vs_serial_percent',True),
                'mean_speedup_vs_ancilla_percent': mean(fam_s,'speedup_vs_ancilla_percent',True),
            }
        }

    def rate(rows,key='success'):
        return float(np.mean([x[key] for x in rows])) if rows else float('nan')
    success_sched = [x for x in scheduling_rows if x['success']]
    payload = {
        'config': cfg,
        'families': family_payload,
        'aggregate': {
            'routing_success_rate': rate(routing_rows),
            'scheduling_success_rate': rate(scheduling_rows),
            'parallel_safe_fraction': float(np.mean([x['retains_cx_parallelism'] for x in success_sched])) if success_sched else float('nan'),
        },
        'elapsed_seconds': time.time() - t0,
    }
    _save_csv(out/'ft_repair_routing.csv', routing_rows)
    _save_csv(out/'ft_repair_scheduling.csv', scheduling_rows)
    (out/'ft_repair_results.json').write_text(json.dumps(payload, indent=2) + '\n')
    (out/'ft_repair_summary.md').write_text(_markdown(payload) + '\n')
    print('FT REPAIR REPORT:', out/'ft_repair_summary.md')
    return payload


def merge_family_results(out_dir: Path, family_dirs: list[Path], cfg: dict):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    families = {}; routing_rows=[]; scheduling_rows=[]; elapsed=0.0
    for d in family_dirs:
        d=Path(d)
        payload=json.loads((d/'ft_repair_results.json').read_text())
        families.update(payload.get('families',{})); elapsed += float(payload.get('elapsed_seconds',0.0))
        for name,target in [('ft_repair_routing.csv',routing_rows),('ft_repair_scheduling.csv',scheduling_rows)]:
            path=d/name
            if path.exists() and path.stat().st_size:
                with path.open() as f: target.extend(list(csv.DictReader(f)))
    def rate(rows,key='success'):
        if not rows: return float('nan')
        return float(np.mean([float(x[key]) for x in rows]))
    safe=[x for x in scheduling_rows if int(float(x.get('success',0)))==1]
    payload={
        'config':cfg,'families':families,
        'aggregate':{
            'routing_success_rate':rate(routing_rows),
            'scheduling_success_rate':rate(scheduling_rows),
            'parallel_safe_fraction':float(np.mean([float(x['retains_cx_parallelism']) for x in safe])) if safe else float('nan'),
        },
        'elapsed_seconds':elapsed,
    }
    _save_csv(out/'ft_repair_routing.csv',routing_rows)
    _save_csv(out/'ft_repair_scheduling.csv',scheduling_rows)
    (out/'ft_repair_results.json').write_text(json.dumps(payload,indent=2)+'\n')
    (out/'ft_repair_summary.md').write_text(_markdown(payload)+'\n')
    return payload
