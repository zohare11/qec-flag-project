"""Benchmark FT compiler repair v2 against the v1 witness-greedy prototype."""
from __future__ import annotations
from pathlib import Path
import csv, json, time, math
import numpy as np

from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase10_scheduler import schedule_parallel
from ftrepair.routing_repair import repair_routing
from ftrepair.schedule_repair import repair_parallel_schedule

from .mutations import generate_multidefect_cases
from .routing_cegis import repair_routing_multidefect
from .schedule_cegis import repair_parallel_schedule_portfolio, repair_parallel_schedule_cegis
from .mixed_repair import repair_mixed


def _save_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text(''); return
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)


def _mean(rows,key,pred=lambda r:True):
    vals=[]
    for r in rows:
        if not pred(r): continue
        try: v=float(r[key])
        except Exception: continue
        if math.isfinite(v): vals.append(v)
    return float(np.mean(vals)) if vals else float('nan')


def _rate(rows,key='success'):
    return _mean(rows,key)


def _set_metrics(changed, injected):
    c=set(map(int,changed)); i=set(map(int,injected))
    tp=len(c&i)
    recall=tp/len(i) if i else 1.0
    precision=tp/len(c) if c else (1.0 if not i else 0.0)
    return recall,precision,int(c==i)


def _family_summary(routing_v2, routing_v1, sched_v2, sched_pure, sched_v1, mixed):
    rv2s=[x for x in routing_v2 if x['success']]
    sv2s=[x for x in sched_v2 if x['success']]
    sps=[x for x in sched_pure if x['success']]
    sv1s=[x for x in sched_v1 if x['success']]
    mixs=[x for x in mixed if x['success']]
    return {
        'routing_v2':{
            'cases':len(routing_v2),'success_rate':_rate(routing_v2),
            'mean_verifier_calls':_mean(routing_v2,'verifier_calls'),
            'mean_changed_checks':_mean(rv2s,'changed_checks'),
            'mean_localization_recall':_mean(rv2s,'localization_recall'),
            'mean_localization_precision':_mean(rv2s,'localization_precision'),
            'exact_injected_set_rate':_mean(rv2s,'exact_injected_set'),
        },
        'routing_v1':{
            'cases':len(routing_v1),'success_rate':_rate(routing_v1),
            'mean_verifier_calls':_mean(routing_v1,'verifier_calls'),
            'mean_changed_checks':_mean([x for x in routing_v1 if x['success']],'changed_checks'),
        },
        'schedule_v2':{
            'cases':len(sched_v2),'success_rate':_rate(sched_v2),
            'mean_verifier_calls':_mean(sched_v2,'verifier_calls'),
            'mean_constraints':_mean(sv2s,'constraints'),
            'parallel_safe_fraction':_mean(sv2s,'retains_parallelism'),
            'mean_speedup_vs_serial_percent':_mean(sv2s,'speedup_vs_serial_percent'),
        },
        'schedule_pure':{
            'cases':len(sched_pure),'success_rate':_rate(sched_pure),
            'mean_verifier_calls':_mean(sched_pure,'verifier_calls'),
            'mean_constraints':_mean(sps,'constraints'),
            'parallel_safe_fraction':_mean(sps,'retains_parallelism'),
            'mean_speedup_vs_serial_percent':_mean(sps,'speedup_vs_serial_percent'),
        },
        'schedule_v1':{
            'cases':len(sched_v1),'success_rate':_rate(sched_v1),
            'mean_verifier_calls':_mean(sched_v1,'verifier_calls'),
            'mean_constraints':_mean(sv1s,'constraints'),
            'parallel_safe_fraction':_mean(sv1s,'retains_parallelism'),
            'mean_speedup_vs_serial_percent':_mean(sv1s,'speedup_vs_serial_percent'),
        },
        'mixed_v2':{
            'cases':len(mixed),'success_rate':_rate(mixed),
            'mean_total_verifier_calls':_mean(mixed,'total_verifier_calls'),
            'parallel_safe_fraction':_mean(mixs,'retains_parallelism'),
            'mean_speedup_vs_serial_percent':_mean(mixs,'speedup_vs_serial_percent'),
        },
    }


def _markdown(payload):
    lines=['# FT compiler repair v2 summary','',
           'Scope: multi-defect counterexample-guided repair of compiler-introduced fault-tolerance violations in the Steane/synthetic-hardware model.','',
           'V2 adds multi-defect lowering cases, exact minimum-hitting-set scheduling repair, and mixed lowering+scheduling repair. Safety remains lexicographic: no optimization objective can override C1=0 and the exact single-fault checks.','']
    for fam,f in payload['families'].items():
        lines += [f'## {fam}','']
        for title,key in [('Multi-defect routing CEGIS','routing_v2'),('Routing v1 baseline','routing_v1'),
                          ('V2 schedule portfolio','schedule_v2'),('Pure hitting-set ablation','schedule_pure'),('Witness-greedy schedule v1','schedule_v1'),
                          ('Mixed lowering + scheduling v2','mixed_v2')]:
            d=f[key]; lines += [f'### {title}','']
            lines.append(f"- Cases: {d['cases']}")
            lines.append(f"- Repair success: {d['success_rate']*100:.1f}%")
            if 'mean_verifier_calls' in d: lines.append(f"- Mean exact verifier calls: {d['mean_verifier_calls']:.2f}")
            if 'mean_total_verifier_calls' in d: lines.append(f"- Mean total exact verifier calls: {d['mean_total_verifier_calls']:.2f}")
            if 'mean_changed_checks' in d: lines.append(f"- Mean changed checks on successes: {d['mean_changed_checks']:.2f}")
            if 'mean_localization_recall' in d:
                lines.append(f"- Hidden injected-check recall: {d['mean_localization_recall']*100:.1f}%")
                lines.append(f"- Hidden injected-check precision: {d['mean_localization_precision']*100:.1f}%")
                lines.append(f"- Exact hidden defect-set recovery: {d['exact_injected_set_rate']*100:.1f}%")
            if 'mean_constraints' in d: lines.append(f"- Mean precedence constraints on successes: {d['mean_constraints']:.2f}")
            if 'parallel_safe_fraction' in d:
                lines.append(f"- Successful repairs retaining true CX parallelism: {d['parallel_safe_fraction']*100:.1f}%")
                lines.append(f"- Mean retained speedup vs serialized: {d['mean_speedup_vs_serial_percent']:.2f}%")
            lines.append('')
    a=payload['aggregate']
    lines += ['## Aggregate','',
              f"- V2 routing success: {a['routing_v2_success']*100:.1f}%",
              f"- V1 routing success: {a['routing_v1_success']*100:.1f}%",
              f"- V2 scheduling portfolio success: {a['schedule_v2_success']*100:.1f}%",
              f"- Pure hitting-set scheduling success: {a['schedule_pure_success']*100:.1f}%",
              f"- V1 scheduling success: {a['schedule_v1_success']*100:.1f}%",
              f"- V2 mixed-repair success: {a['mixed_v2_success']*100:.1f}%",'',
              '## Interpretation constraints','',
              '- This benchmark still uses one Steane-code family and one fixed 12-node physical graph; it is not yet a cross-code/cross-topology generalization result.',
              '- Multi-defect cases are controlled compiler mutations whose hidden locations are used only for evaluation, not by the repair algorithms.',
              '- The hitting-set solver reasons globally over accumulated physical-fault counterexamples, but pairwise check-precedence constraints are still a restricted repair language.',
              '- Exact single-fault certification remains authoritative; proxy costs are only used to order safe-search candidates.',
              '- Mixed repair is staged (lowering repair, then scheduling repair), not a complete joint optimizer.',
              ]
    return '\n'.join(lines)


def run_all(project_root: Path,cfg:dict,out_dir:Path):
    root=Path(project_root); out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); t0=time.time()
    fams=list(cfg.get('families',['hw_id','ood_edge_hotspot','ood_mixed']))
    nctx=int(cfg.get('contexts_per_family',1)); seed=int(cfg.get('seed',22101))
    defect_counts=tuple(cfg.get('defect_counts',[1,2,3])); cases_per=int(cfg.get('routing_cases_per_defect_count',2))
    sched_cases=int(cfg.get('scheduling_cases',2)); sched_methods=list(cfg.get('schedule_methods',['shortest_greedy']))
    mixed_cases=int(cfg.get('mixed_cases',2))
    max_edits=int(cfg.get('routing_max_edits',4)); max_calls=int(cfg.get('routing_max_verifier_calls',64))
    sched_max_calls=int(cfg.get('schedule_max_verifier_calls',20)); sched_max_constraints=int(cfg.get('schedule_max_constraints',15))

    nominal=sample_hardware_contexts(1,seed+777,'hw_id').context(0)
    cases=generate_multidefect_cases(root,nominal,defect_counts=defect_counts,cases_per_count=cases_per,bases=int(cfg.get('mutation_bases',8)))
    if not cases: raise RuntimeError('no multi-defect cases generated')
    cat=ensure_catalog(root,progress=False)

    all_r2=[]; all_r1=[]; all_s2=[]; all_sp=[]; all_s1=[]; all_m=[]; families={}
    for fi,fam in enumerate(fams):
        batch=sample_hardware_contexts(nctx,seed+1000*fi,fam)
        fr2=[];fr1=[];fs2=[];fsp=[];fs1=[];fm=[]
        for ci in range(nctx):
            ctx=batch.context(ci)
            for case in cases:
                r2=repair_routing_multidefect(root,case['labels'],case['hubs'],ctx,max_edits=max_edits,max_verifier_calls=max_calls,
                                              witness_check_limit=int(cfg.get('witness_check_limit',4)),alternatives_per_check=int(cfg.get('alternatives_per_check',6)))
                rec,prec,exact=_set_metrics(r2.changed_checks,case['injected_checks']) if r2.success else (0.0,0.0,0)
                row={'family':fam,'context':ci,'case':case['case'],'defect_count':case['defect_count'],
                     'injected_checks':'|'.join(map(str,case['injected_checks'])),'success':int(r2.success),
                     'verifier_calls':r2.verifier_calls,'changed_checks':len(r2.changed_checks),'localization_recall':rec,
                     'localization_precision':prec,'exact_injected_set':exact,'initial_c1':r2.initial_c1,
                     'final_c1':r2.final_c1 if r2.final_c1 is not None else ''}
                fr2.append(row);all_r2.append(row)
                # Existing v1 baseline is allowed the same edit/call budget.
                try:
                    r1=repair_routing(root,case['labels'],case['hubs'],ctx,max_edits=max_edits,max_verifier_calls=max_calls,witness_check_limit=int(cfg.get('witness_check_limit',4)))
                    row1={'family':fam,'context':ci,'case':case['case'],'defect_count':case['defect_count'],'success':int(r1.success),
                          'verifier_calls':r1.verifier_calls,'changed_checks':len(r1.changed_checks)}
                except Exception:
                    row1={'family':fam,'context':ci,'case':case['case'],'defect_count':case['defect_count'],'success':0,
                          'verifier_calls':max_calls,'changed_checks':''}
                fr1.append(row1);all_r1.append(row1)
                print(f'V2 routing {fam} ctx={ci} case={case["case"]} k={case["defect_count"]} success={r2.success} calls={r2.verifier_calls}')

            for si in range(min(sched_cases,len(cat))):
                labels,hubs=cat.labels_hubs(si)
                serial=schedule_parallel(labels,hubs,ctx,'serialized')
                for method in sched_methods:
                    r2=repair_parallel_schedule_portfolio(labels,hubs,ctx,method=method,max_constraints=sched_max_constraints,max_verifier_calls=sched_max_calls)
                    speed=(1-r2.final_duration_ns/serial.duration_ns)*100.0 if r2.success else float('nan')
                    row={'family':fam,'context':ci,'case':si,'method':method,'success':int(r2.success),'verifier_calls':r2.verifier_calls,
                         'constraints':len(r2.constraints),'retains_parallelism':int(r2.success and r2.final_max_parallel_cx>1),
                         'speedup_vs_serial_percent':speed,'final_c1':r2.final_c1}
                    fs2.append(row);all_s2.append(row)
                    if bool(cfg.get('run_pure_hittingset_ablation', True)):
                        rp=repair_parallel_schedule_cegis(labels,hubs,ctx,method=method,max_constraints=sched_max_constraints,max_verifier_calls=max(4,int(cfg.get('pure_hittingset_max_calls',10))))
                        speedp=(1-rp.final_duration_ns/serial.duration_ns)*100.0 if rp.success else float('nan')
                        rowp={'family':fam,'context':ci,'case':si,'method':method,'success':int(rp.success),'verifier_calls':rp.verifier_calls,
                              'constraints':len(rp.constraints),'retains_parallelism':int(rp.success and rp.final_max_parallel_cx>1),
                              'speedup_vs_serial_percent':speedp,'final_c1':rp.final_c1}
                        fsp.append(rowp);all_sp.append(rowp)
                    r1=repair_parallel_schedule(labels,hubs,ctx,method,max_constraints=sched_max_constraints)
                    speed1=(1-r1.final_duration_ns/serial.duration_ns)*100.0 if r1.success and r1.final_duration_ns is not None else float('nan')
                    row1={'family':fam,'context':ci,'case':si,'method':method,'success':int(r1.success),'verifier_calls':r1.verifier_calls,
                          'constraints':len(r1.constraints),'retains_parallelism':int(r1.success and int(r1.final_max_parallel_cx or 0)>1),
                          'speedup_vs_serial_percent':speed1,'final_c1':r1.final_c1 if r1.final_c1 is not None else ''}
                    fs1.append(row1);all_s1.append(row1)
                    print(f'V2 schedule {fam} ctx={ci} case={si} {method} success={r2.success} constraints={len(r2.constraints)}')

            for case in cases[:mixed_cases]:
                m=repair_mixed(root,case['labels'],case['hubs'],ctx,schedule_method=sched_methods[0],
                               routing_max_edits=max_edits,routing_max_calls=max_calls,
                               schedule_max_constraints=sched_max_constraints,schedule_max_calls=sched_max_calls)
                row={'family':fam,'context':ci,'case':case['case'],'defect_count':case['defect_count'],'success':int(m.success),
                     'routing_success':int(m.routing_success),'scheduling_success':int(m.scheduling_success),
                     'total_verifier_calls':m.total_verifier_calls,'changed_checks':len(m.changed_checks),
                     'constraints':len(m.precedence_constraints),'retains_parallelism':int(m.success and int(m.final_max_parallel_cx or 0)>1),
                     'speedup_vs_serial_percent':m.speedup_vs_serial_percent if m.speedup_vs_serial_percent is not None else ''}
                fm.append(row);all_m.append(row)

        families[fam]=_family_summary(fr2,fr1,fs2,fsp,fs1,fm)

    payload={'config':cfg,'generated_cases':[{
        'case':c['case'],'defect_count':c['defect_count'],'injected_checks':list(c['injected_checks']),'base_index':c['base_index']
    } for c in cases], 'families':families,
    'aggregate':{
        'routing_v2_success':_rate(all_r2),'routing_v1_success':_rate(all_r1),
        'schedule_v2_success':_rate(all_s2),'schedule_pure_success':_rate(all_sp),'schedule_v1_success':_rate(all_s1),
        'mixed_v2_success':_rate(all_m),
    },'elapsed_seconds':time.time()-t0}
    _save_csv(out/'ft_repair_v2_routing.csv',all_r2);_save_csv(out/'ft_repair_v2_routing_v1.csv',all_r1)
    _save_csv(out/'ft_repair_v2_scheduling.csv',all_s2);_save_csv(out/'ft_repair_v2_scheduling_pure.csv',all_sp);_save_csv(out/'ft_repair_v2_scheduling_v1.csv',all_s1)
    _save_csv(out/'ft_repair_v2_mixed.csv',all_m)
    (out/'ft_repair_v2_results.json').write_text(json.dumps(payload,indent=2)+'\n')
    (out/'ft_repair_v2_summary.md').write_text(_markdown(payload)+'\n')
    print('FT REPAIR V2 REPORT:',out/'ft_repair_v2_summary.md')
    return payload
