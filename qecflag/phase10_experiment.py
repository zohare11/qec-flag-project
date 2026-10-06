"""Phase 10 experiment: deterministic parallel scheduling under FT certification."""
from __future__ import annotations

from pathlib import Path
import csv, json, time
import numpy as np

from .phase5_noise import sample_hardware_contexts
from .phase8_experiment import ensure_continuous_catalog, _choose_proxy, _labels_hubs
from .phase10_scheduler import (
    schedule_parallel, local_priority_search, beam_priority_search,
    certify_parallel_schedule, summarize_schedule,
)
from .phase10_repeated import simulate_parallel_detector_sweep

METHODS = (
    'serialized', 'ancilla_overlap', 'asap', 'shortest_greedy',
    'critical_greedy', 'noise_greedy', 'css_block', 'local_search', 'beam_search',
)


def _save_csv(path: Path, rows: list[dict]):
    if not rows:
        path.write_text(''); return
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with path.open('w', newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)


def _build_methods(labels,hubs,ctx,beam_width:int):
    out={}
    for method in ('serialized','ancilla_overlap','asap','shortest_greedy','critical_greedy','noise_greedy','css_block'):
        out[method]=schedule_parallel(labels,hubs,ctx,method)
    out['local_search']=local_priority_search(labels,hubs,ctx)
    out['beam_search']=beam_priority_search(labels,hubs,ctx,width=beam_width)[0]
    return out


def _timeline_rows(family:int|str, context_index:int, method:str, schedule):
    rows=[]
    for se in schedule.events:
        ev=se.event
        rows.append({
            'family':family,'context':context_index,'method':method,'uid':ev.uid,'check':ev.check,'seq':ev.seq,
            'kind':ev.kind,'start_us':se.start_ns/1000.0,'stop_us':se.stop_ns/1000.0,
            'duration_ns':ev.duration_ns,'resources':' '.join(map(str,ev.resources)),
            'control':ev.control,'target':ev.target,'edge_id':ev.edge_id,'route':ev.route,'gate':ev.gate,'token':ev.token,
        })
    return rows


def _markdown(payload:dict)->str:
    cfg=payload['config']
    lines=['# Phase 10 summary','',
      'Scope: deterministic resource-constrained parallel scheduling of Phase-9 physically certified Steane extraction circuits.','',
      'The logical circuit and bridge routes are fixed before scheduling. Operations from different checks may overlap only when physical-qubit resources are disjoint, and every selected schedule is re-certified under its actual event order.','',
      f"- Repeated extraction rounds for logical diagnostics: {cfg.get('rounds',3)}",
      f"- Phase-8/9 physical catalog size: {payload['catalog_size']}",
      '- Hard admissibility rule: ideal circuit preserved, C1=0, zero single-fault conflicts/failures, zero incoming-single-error failures.',
      '- No learned policy is trained in Phase 10.','']
    for fam, block in payload['families'].items():
        lines += [f'## {fam}','',
                  '| Method | Duration (us) | vs serial | Data idle (us) | Max parallel CX | C1 | FT pass |',
                  '|---|---:|---:|---:|---:|---:|---:|']
        rows=block['schedule_rows']
        serial=np.mean([r['duration_us'] for r in rows if r['method']=='serialized'])
        for method in METHODS:
            rr=[r for r in rows if r['method']==method]
            if not rr: continue
            dur=float(np.mean([r['duration_us'] for r in rr])); idle=float(np.mean([r['total_data_idle_us'] for r in rr]))
            c1=float(np.mean([r['c1'] for r in rr])); ft=float(np.mean([bool(r['ft_pass']) for r in rr]))
            maxcx=float(np.mean([r['max_parallel_cx'] for r in rr])); change=(dur/serial-1.0)*100.0 if serial else float('nan')
            lines.append(f'| {method} | {dur:.3f} | {change:+.2f}% | {idle:.3f} | {maxcx:.2f} | {c1:.6g} | {ft:.0%} |')
        lines += ['',f"- FT-safe methods/context mean: {block['safe_method_count_mean']:.2f} / {len(METHODS)}.",
                  f"- Aggressive schedules with native-CX concurrency that remained FT: {block['aggressive_safe_count']} / {block['aggressive_checked_count']}.",
                  f"- Best FT-safe mean duration: {block['best_safe_duration_us']:.3f} us ({block['best_safe_speedup_percent']:.2f}% faster than serialized).",'']
        if block.get('repeated_rows'):
            lines += ['### Repeated-round detector diagnostics','',
                      '| Method | p | Mean logical failure rate |', '|---|---:|---:|']
            methods=sorted({r['method'] for r in block['repeated_rows']})
            ps=sorted({r['p'] for r in block['repeated_rows']})
            for method in methods:
                for p in ps:
                    vals=[r['logical_failure_rate'] for r in block['repeated_rows'] if r['method']==method and r['p']==p]
                    if vals: lines.append(f'| {method} | {p:g} | {np.mean(vals):.7f} |')
            lines.append('')
    lines += ['## Interpretation constraints','',
      '- Phase 10 parallelizes already-certified bridge-routed operations; it does not redesign stabilizer circuits or routing primitives.',
      '- Prep, native-CX, and measurement operations have explicit durations. Same-check order is fixed; overlapping operations must use disjoint physical qubits.',
      '- Data idling is derived from the actual parallel timeline at every event boundary.',
      '- Resource-valid parallelism is not assumed fault tolerant. Every reported schedule is independently single-fault re-certified after reordering.',
      '- The beam baseline searches static check-priority permutations, not arbitrary gate permutations and not a learned policy.',
      '- Three-round logical diagnostics use the Phase-9 order-2 detector-hypergraph decoder and an ideal final memory-boundary syndrome.',
      '- Hardware topology/calibrations remain synthetic; no crosstalk, leakage, pulse-level constraints, or real-backend calibration is modeled.','']
    return '\n'.join(lines)


def run_all(project_root:Path,cfg:dict,out_dir:Path):
    t0=time.time(); root=Path(project_root); out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    cat=ensure_continuous_catalog(root,progress=True); entries=cat['entries']
    seed=int(cfg.get('seed',10201)); nctx=int(cfg.get('contexts_per_family',1)); budget=int(cfg.get('search_budget',4))
    beam_width=int(cfg.get('beam_width',8)); rounds=int(cfg.get('rounds',3)); ps=[float(x) for x in cfg.get('p',[2e-4])]
    shots=int(cfg.get('shots',3000)); families=list(cfg.get('families',['hw_id']))
    repeated_requested=set(cfg.get('repeated_methods',['serialized','ancilla_overlap']))

    all_schedule_rows=[]; all_repeated_rows=[]; timeline=[]; family_payload={}
    canonical_slots={'hw_id':0,'ood_idle_hotspot':1,'ood_slow_link':2,'ood_logical_shift':3,'ood_mixed':4,
                     'ood_hub0_bad':5,'ood_hub1_bad':6,'ood_edge_hotspot':7}
    for fi,fam in enumerate(families):
        slot=canonical_slots.get(fam,fi); batch=sample_hardware_contexts(nctx,seed+100*slot+10,fam)
        fam_sched=[]; fam_rep=[]; aggressive_safe=0; aggressive_checked=0; best_safe=[]
        for ci in range(nctx):
            ctx=batch.context(ci)
            circuit=_choose_proxy(entries,ctx,budget)[0]
            labels,hubs=_labels_hubs(circuit)
            schedules=_build_methods(labels,hubs,ctx,beam_width)
            certs={}
            context_safe_durations=[]
            for method,s in schedules.items():
                cert=certify_parallel_schedule(s,ctx); certs[method]=cert
                metrics=summarize_schedule(s,ctx)
                row={'family':fam,'context':ci,'method':method,**metrics,
                     'ft_pass':bool(cert.passed),'ideal_ok':bool(cert.ideal_ok),'c1':float(cert.c1),
                     'single_fault_conflicts':int(cert.conflicts),'single_fault_failures':int(cert.single_fault_failures),
                     'incoming_failures':int(cert.incoming_failures),'fault_outcomes':int(cert.fault_outcomes),
                     'physical_fault_locations':int(cert.physical_fault_locations)}
                fam_sched.append(row); all_schedule_rows.append(row)
                if ci==0: timeline.extend(_timeline_rows(fam,ci,method,s))
                if s.max_parallel_cx>1:
                    aggressive_checked += 1; aggressive_safe += int(cert.passed)
                if cert.passed: context_safe_durations.append(s.duration_ns)
            if context_safe_durations:
                best_safe.append(min(context_safe_durations))
            # Always diagnose serial and ancilla-overlap if safe. If some truly
            # CX-parallel schedule is safe, also diagnose the fastest one.
            diag_methods=set(repeated_requested)
            cx_safe=[(s.duration_ns,m) for m,s in schedules.items() if s.max_parallel_cx>1 and certs[m].passed]
            if cx_safe: diag_methods.add(min(cx_safe)[1])
            for method in sorted(diag_methods):
                if method not in schedules or not certs[method].passed:
                    continue
                s=schedules[method]
                seeds=[seed+100000*slot+10000*ci+100*pi+sum(ord(ch) for ch in method)%97 for pi in range(len(ps))]
                sweep=simulate_parallel_detector_sweep(
                    s,ctx,rounds,ps,shots,seeds,
                    reference_p=float(cfg.get('detector_reference_p',2e-4)),
                )
                for r in sweep:
                    row={'family':fam,'context':ci,'method':method,**r}; fam_rep.append(row); all_repeated_rows.append(row)
            print(f"P10 EVAL {fam} {ci+1}/{nctx}: safe={[m for m in schedules if certs[m].passed]}")
        serial_mean=float(np.mean([r['duration_us'] for r in fam_sched if r['method']=='serialized']))
        best_mean=float(np.mean(best_safe))/1000.0 if best_safe else float('nan')
        family_payload[fam]={
            'schedule_rows':fam_sched,'repeated_rows':fam_rep,
            'safe_method_count_mean':float(np.mean([sum(r['ft_pass'] for r in fam_sched if r['context']==ci) for ci in range(nctx)])),
            'aggressive_safe_count':int(aggressive_safe),'aggressive_checked_count':int(aggressive_checked),
            'best_safe_duration_us':best_mean,
            'best_safe_speedup_percent':float((1.0-best_mean/serial_mean)*100.0) if serial_mean else float('nan'),
        }

    _save_csv(out/'phase10_schedule_metrics.csv',all_schedule_rows)
    _save_csv(out/'phase10_repeated_detector.csv',all_repeated_rows)
    _save_csv(out/'phase10_timeline_first_context.csv',timeline)
    payload={'config':cfg,'catalog_size':len(entries),'families':family_payload,'elapsed_seconds':time.time()-t0}
    (out/'phase10_results.json').write_text(json.dumps(payload,indent=2)+'\n')
    (out/'phase10_summary.md').write_text(_markdown(payload)+'\n')
    print('PHASE 10 REPORT:',out/'phase10_summary.md')
    return payload


def merge_family_results(out_dir:Path, family_dirs:list[Path], cfg:dict):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    families={}; catalog_size=0; elapsed=0.0; sched=[]; rep=[]; timeline=[]
    for d in family_dirs:
        p=json.loads((Path(d)/'phase10_results.json').read_text())
        catalog_size=max(catalog_size,int(p.get('catalog_size',0))); elapsed += float(p.get('elapsed_seconds',0.0))
        families.update(p['families'])
        for name,target in [('phase10_schedule_metrics.csv',sched),('phase10_repeated_detector.csv',rep),('phase10_timeline_first_context.csv',timeline)]:
            path=Path(d)/name
            if path.exists() and path.stat().st_size:
                with path.open() as f: target.extend(list(csv.DictReader(f)))
    payload={'config':cfg,'catalog_size':catalog_size,'families':families,'elapsed_seconds':elapsed}
    _save_csv(out/'phase10_schedule_metrics.csv',sched); _save_csv(out/'phase10_repeated_detector.csv',rep); _save_csv(out/'phase10_timeline_first_context.csv',timeline)
    (out/'phase10_results.json').write_text(json.dumps(payload,indent=2)+'\n')
    (out/'phase10_summary.md').write_text(_markdown(payload)+'\n')
    return payload
