"""Benchmark harness for FT compiler repair v3."""
from __future__ import annotations
from pathlib import Path
import csv,json,time,math
import numpy as np

from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase10_scheduler import schedule_parallel
from ftrepair_v2.routing_cegis import repair_routing_multidefect
from ftrepair_v2.schedule_cegis import repair_parallel_schedule_portfolio as repair_schedule_v2

from .model import RoutingState, edit_atoms
from .mutations import generate_check_choice_cases, generate_path_defect_cases
from .routing_cegis import repair_routing_v3
from .op_scheduler import repair_operation_schedule_portfolio, repair_operation_schedule
from .cross_layer import repair_staged_v3, repair_cross_layer_portfolio


def _save_csv(path:Path,rows:list[dict]):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:path.write_text('');return
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def _mean(rows,key,pred=lambda r:True):
    vals=[]
    for r in rows:
        if not pred(r):continue
        try:v=float(r[key])
        except Exception:continue
        if math.isfinite(v):vals.append(v)
    return float(np.mean(vals)) if vals else float('nan')


def _rate(rows,key='success'):return _mean(rows,key)


def _set_metrics(found,hidden):
    f=set(found);h=set(hidden);tp=len(f&h)
    return (tp/len(h) if h else 1.0,
            tp/len(f) if f else (1.0 if not h else 0.0),
            int(f==h))


def _by_defect_count(rows):
    out={}
    for k in sorted(set(int(r['defect_count']) for r in rows if str(r.get('defect_count',''))!='')):
        rr=[r for r in rows if int(r['defect_count'])==k]
        out[str(k)]={'cases':len(rr),'success_rate':_rate(rr),'mean_calls':_mean(rr,'verifier_calls')}
    return out


def _family_summary(r3,r2,path3,s3,spure,s2,staged,joint):
    s3ok=[x for x in s3 if x['success']];s2ok=[x for x in s2 if x['success']];jointok=[x for x in joint if x['success']]
    return {
      'routing_v3':{'cases':len(r3),'success_rate':_rate(r3),'mean_verifier_calls':_mean(r3,'verifier_calls'),
        'mean_cache_hits':_mean(r3,'cache_hits'),'mean_edit_count':_mean([x for x in r3 if x['success']],'edit_count'),
        'mean_changed_check_recall':_mean([x for x in r3 if x['success']],'changed_check_recall'),
        'mean_changed_check_precision':_mean([x for x in r3 if x['success']],'changed_check_precision'),
        'exact_hidden_check_set_rate':_mean([x for x in r3 if x['success']],'exact_hidden_check_set'),
        'by_defect_count':_by_defect_count(r3)},
      'routing_v2':{'cases':len(r2),'success_rate':_rate(r2),'mean_verifier_calls':_mean(r2,'verifier_calls'),
        'by_defect_count':_by_defect_count(r2)},
      'path_repair_v3':{'cases':len(path3),'success_rate':_rate(path3),'mean_verifier_calls':_mean(path3,'verifier_calls'),
        'mean_route_localization_recall':_mean([x for x in path3 if x['success']],'witness_route_recall')},
      'schedule_v3':{'cases':len(s3),'success_rate':_rate(s3),'mean_verifier_calls':_mean(s3,'verifier_calls'),
        'mean_cache_hits':_mean(s3,'cache_hits'),'mean_constraints':_mean(s3ok,'constraints'),
        'parallel_safe_fraction':_mean(s3ok,'retains_parallelism'),'mean_speedup_vs_serial_percent':_mean(s3ok,'speedup_vs_serial_percent')},
      'schedule_v3_pure':{'cases':len(spure),'success_rate':_rate(spure),'mean_verifier_calls':_mean(spure,'verifier_calls'),
        'mean_constraints':_mean([x for x in spure if x['success']],'constraints'),
        'mean_speedup_vs_serial_percent':_mean([x for x in spure if x['success']],'speedup_vs_serial_percent')},
      'schedule_v2':{'cases':len(s2),'success_rate':_rate(s2),'mean_verifier_calls':_mean(s2,'verifier_calls'),
        'mean_constraints':_mean(s2ok,'constraints'),'mean_speedup_vs_serial_percent':_mean(s2ok,'speedup_vs_serial_percent')},
      'mixed_staged_v3':{'cases':len(staged),'success_rate':_rate(staged),'routing_stage_success':_mean(staged,'routing_success'),
        'schedule_stage_success':_mean(staged,'scheduling_success'),'mean_total_calls':_mean(staged,'total_verifier_calls')},
      'mixed_cross_layer_v3':{'cases':len(joint),'success_rate':_rate(joint),'mean_total_calls':_mean(joint,'total_verifier_calls'),
        'mean_routing_candidates':_mean(joint,'routing_candidates_found'),'parallel_safe_fraction':_mean(jointok,'retains_parallelism'),
        'mean_speedup_vs_serial_percent':_mean(jointok,'speedup_vs_serial_percent'),
        'mean_total_compiler_edits':_mean(jointok,'total_compiler_edits')},
    }


def _pct(x):
    try:
        if not math.isfinite(float(x)):return 'n/a'
        return f'{100*float(x):.1f}%'
    except Exception:return 'n/a'


def _fmt(x,d=2):
    try:
        if not math.isfinite(float(x)):return 'n/a'
        return f'{float(x):.{d}f}'
    except Exception:return 'n/a'


def _markdown(payload):
    lines=['# FT compiler repair v3 summary','',
      'Scope: operation-localized, richer-action counterexample-guided repair of compiler-introduced FT violations. V3 adds per-route path repair, operation-level precedence repair, verifier caching, and cross-layer routing/scheduling portfolio selection.','',
      'Safety remains lexicographic: only exact C1=0 with zero single-fault conflicts/failures and zero incoming-single-error failures is accepted.','']
    for fam,s in payload['families'].items():
        lines += [f'## {fam}','', '### Multi-defect routing repair', '',
          f"- V3 success: {_pct(s['routing_v3']['success_rate'])} ({s['routing_v3']['cases']} cases)",
          f"- V2 success: {_pct(s['routing_v2']['success_rate'])} ({s['routing_v2']['cases']} cases)",
          f"- V3 mean exact verifier calls: {_fmt(s['routing_v3']['mean_verifier_calls'])}",
          f"- V3 mean verifier-cache hits: {_fmt(s['routing_v3']['mean_cache_hits'])}",
          f"- Exact hidden changed-check recovery on V3 successes: {_pct(s['routing_v3']['exact_hidden_check_set_rate'])}",
          '- V3 success by hidden-defect count:']
        for k,v in s['routing_v3']['by_defect_count'].items():
            lines.append(f"  - k={k}: {_pct(v['success_rate'])} ({v['cases']} cases), mean calls {_fmt(v['mean_calls'])}")
        lines += ['', '### Physical path-defect repair', '',
          f"- Cases: {s['path_repair_v3']['cases']}",
          f"- V3 success: {_pct(s['path_repair_v3']['success_rate'])}",
          f"- Mean witness-route recall on successes: {_pct(s['path_repair_v3']['mean_route_localization_recall'])}",
          '', '### Parallel-schedule repair','',
          f"- V3 portfolio success: {_pct(s['schedule_v3']['success_rate'])}",
          f"- V3 pure operation-CEGIS success: {_pct(s['schedule_v3_pure']['success_rate'])}",
          f"- V2 pairwise portfolio success: {_pct(s['schedule_v2']['success_rate'])}",
          f"- V3 mean exact calls: {_fmt(s['schedule_v3']['mean_verifier_calls'])}",
          f"- V3 mean operation constraints on successes: {_fmt(s['schedule_v3']['mean_constraints'])}",
          f"- V3 safe repairs retaining true CX concurrency: {_pct(s['schedule_v3']['parallel_safe_fraction'])}",
          f"- V3 mean retained speedup vs serial: {_fmt(s['schedule_v3']['mean_speedup_vs_serial_percent'])}%",
          f"- V2 mean retained speedup vs serial: {_fmt(s['schedule_v2']['mean_speedup_vs_serial_percent'])}%",
          '', '### Mixed lowering + scheduling','',
          f"- Staged V3 success: {_pct(s['mixed_staged_v3']['success_rate'])}",
          f"- Staged routing-stage success: {_pct(s['mixed_staged_v3']['routing_stage_success'])}",
          f"- Staged scheduling-stage success: {_pct(s['mixed_staged_v3']['schedule_stage_success'])}",
          f"- Cross-layer portfolio success: {_pct(s['mixed_cross_layer_v3']['success_rate'])}",
          f"- Cross-layer mean routing candidates evaluated: {_fmt(s['mixed_cross_layer_v3']['mean_routing_candidates'])}",
          f"- Cross-layer mean retained speedup: {_fmt(s['mixed_cross_layer_v3']['mean_speedup_vs_serial_percent'])}%",'']
    a=payload['aggregate']
    lines += ['## Aggregate','',
      f"- Routing V3 success: {_pct(a['routing_v3_success'])}",f"- Routing V2 success: {_pct(a['routing_v2_success'])}",
      f"- Path repair V3 success: {_pct(a['path_v3_success'])}",f"- Schedule V3 success: {_pct(a['schedule_v3_success'])}",
      f"- Schedule pure operation-CEGIS success: {_pct(a['schedule_pure_success'])}",f"- Schedule V2 success: {_pct(a['schedule_v2_success'])}",
      f"- Mixed staged V3 success: {_pct(a['mixed_staged_success'])}",f"- Mixed cross-layer V3 success: {_pct(a['mixed_cross_layer_success'])}",'',
      '## Interpretation constraints','',
      '- V3 still uses the Steane family and the fixed synthetic 12-node graph; this is not yet cross-code/cross-topology evidence.',
      '- Operation-level precedence uses a bounded/global hitting-set heuristic when the atom universe is too large for exact subset enumeration; every proposed schedule is still accepted only after exact physical single-fault certification.',
      '- Cross-layer V3 is a portfolio over multiple exactly certified routing repairs followed by exact schedule repair, not a monolithic joint SAT/SMT optimizer.',
      '- Path alternatives remain bridge primitives of at most three hops on the existing graph.',
      '- Verifier caching changes computational cost only; it never substitutes a heuristic score for the exact safety check.']
    return '\n'.join(lines)


def run_all(project_root:Path,cfg:dict,out_dir:Path):
    root=Path(project_root);out=Path(out_dir);out.mkdir(parents=True,exist_ok=True);t0=time.time()
    fams=list(cfg.get('families',['hw_id']));nctx=int(cfg.get('contexts_per_family',1));seed=int(cfg.get('seed',33101))
    defect_counts=tuple(cfg.get('defect_counts',[1,2,3]));cases_per=int(cfg.get('routing_cases_per_defect_count',2));bases=int(cfg.get('mutation_bases',6))
    rmax=int(cfg.get('routing_max_verifier_calls',48));rmaxedits=int(cfg.get('routing_max_edits',5))
    sched_cases=int(cfg.get('scheduling_cases',1));sched_methods=list(cfg.get('schedule_methods',['shortest_greedy']));smax=int(cfg.get('schedule_max_verifier_calls',32))
    mixed_cases=int(cfg.get('mixed_cases',1));joint_solutions=int(cfg.get('cross_layer_routing_solutions',2))
    nominal=sample_hardware_contexts(1,seed+777,'hw_id').context(0)
    cases=generate_check_choice_cases(root,nominal,defect_counts,cases_per,bases)
    path_cases=[]
    if bool(cfg.get('run_path_defect_benchmark',True)):
        path_cases=generate_path_defect_cases(root,nominal,defect_counts=tuple(cfg.get('path_defect_counts',[1])),
            cases_per_count=int(cfg.get('path_cases_per_defect_count',1)),bases=int(cfg.get('path_mutation_bases',2)),
            max_paths_per_route=int(cfg.get('path_alternatives_per_route',4)))
    cat=ensure_catalog(root,progress=False)
    all_r3=[];all_r2=[];all_p3=[];all_s3=[];all_sp=[];all_s2=[];all_st=[];all_j=[];families={}
    for fi,fam in enumerate(fams):
        batch=sample_hardware_contexts(nctx,seed+1000*fi,fam)
        fr3=[];fr2=[];fp3=[];fs3=[];fsp=[];fs2=[];fst=[];fj=[]
        for ci in range(nctx):
            ctx=batch.context(ci)
            for case in cases:
                st=case['state']
                r3=repair_routing_v3(root,st,None,ctx,max_edits=rmaxedits,max_verifier_calls=rmax,
                    path_alternatives_per_route=int(cfg.get('path_alternatives_per_route',4)),
                    check_alternatives_per_check=int(cfg.get('check_alternatives_per_check',8)),max_solutions=2)
                rec,prec,exact=_set_metrics(r3.changed_checks,case['injected_checks']) if r3.success else (0,0,0)
                wrec,wprec,wexact=_set_metrics(r3.witness_checks_seen,case['injected_checks'])
                row={'family':fam,'context':ci,'case':case['case'],'defect_type':'check_choice','defect_count':case['defect_count'],
                     'injected_checks':'|'.join(map(str,case['injected_checks'])),'success':int(r3.success),'verifier_calls':r3.verifier_calls,
                     'cache_hits':r3.cache_hits,'states_seen':r3.states_seen,'edit_count':r3.edit_count,'changed_checks':len(r3.changed_checks),
                     'changed_paths':len(r3.changed_paths),'changed_check_recall':rec,'changed_check_precision':prec,'exact_hidden_check_set':exact,
                     'witness_check_recall':wrec,'witness_check_precision':wprec,'initial_c1':r3.initial_c1,'final_c1':r3.final_c1 if r3.final_c1 is not None else ''}
                fr3.append(row);all_r3.append(row)
                if bool(cfg.get('run_v2_routing_baseline',True)):
                    try:
                        r2=repair_routing_multidefect(root,st.labels,st.hubs,ctx,max_edits=rmaxedits,max_verifier_calls=rmax)
                        row2={'family':fam,'context':ci,'case':case['case'],'defect_count':case['defect_count'],'success':int(r2.success),'verifier_calls':r2.verifier_calls}
                    except Exception:
                        row2={'family':fam,'context':ci,'case':case['case'],'defect_count':case['defect_count'],'success':0,'verifier_calls':rmax}
                    fr2.append(row2);all_r2.append(row2)
                print(f'V3 routing {fam} ctx={ci} case={case["case"]} k={case["defect_count"]} success={r3.success} calls={r3.verifier_calls}',flush=True)
            for case in path_cases:
                st=case['state'];r3=repair_routing_v3(root,st,None,ctx,max_edits=rmaxedits,max_verifier_calls=rmax,
                    path_alternatives_per_route=int(cfg.get('path_alternatives_per_route',5)),check_alternatives_per_check=int(cfg.get('check_alternatives_per_check',8)),max_solutions=2)
                hidden=set(case['injected_routes']);seen=set(r3.witness_routes_seen);route_rec=len(hidden&seen)/len(hidden) if hidden else 1.0
                row={'family':fam,'context':ci,'case':case['case'],'defect_count':case['defect_count'],'success':int(r3.success),
                     'verifier_calls':r3.verifier_calls,'cache_hits':r3.cache_hits,'witness_route_recall':route_rec,
                     'changed_paths':len(r3.changed_paths),'edit_count':r3.edit_count,'initial_c1':r3.initial_c1,'final_c1':r3.final_c1 if r3.final_c1 is not None else ''}
                fp3.append(row);all_p3.append(row)
            for si in range(min(sched_cases,len(cat))):
                labels,hubs=cat.labels_hubs(si);st=RoutingState.from_parts(labels,hubs);serial=schedule_parallel(labels,hubs,ctx,'serialized')
                for method in sched_methods:
                    r3=repair_operation_schedule_portfolio(st,ctx,method,max_verifier_calls=smax,max_constraints=int(cfg.get('schedule_max_constraints',40)))
                    row={'family':fam,'context':ci,'case':si,'method':method,'success':int(r3.success),'verifier_calls':r3.verifier_calls,'cache_hits':r3.cache_hits,
                         'constraints':len(r3.constraints),'retains_parallelism':int(r3.success and r3.final_max_parallel_cx>1),
                         'speedup_vs_serial_percent':r3.speedup_vs_serial_percent if r3.success else float('nan'),'final_c1':r3.final_c1}
                    fs3.append(row);all_s3.append(row)
                    if bool(cfg.get('run_pure_operation_ablation',True)):
                        rp=repair_operation_schedule(st,ctx,method,max_verifier_calls=int(cfg.get('pure_operation_max_calls',10)),max_constraints=int(cfg.get('schedule_max_constraints',40)),minimize=False)
                        rowp={'family':fam,'context':ci,'case':si,'method':method,'success':int(rp.success),'verifier_calls':rp.verifier_calls,'constraints':len(rp.constraints),
                              'retains_parallelism':int(rp.success and rp.final_max_parallel_cx>1),'speedup_vs_serial_percent':rp.speedup_vs_serial_percent if rp.success else float('nan')}
                        fsp.append(rowp);all_sp.append(rowp)
                    if bool(cfg.get('run_v2_schedule_baseline',True)):
                        r2=repair_schedule_v2(labels,hubs,ctx,method=method,max_constraints=15,max_verifier_calls=min(smax,32))
                        speed2=(1-r2.final_duration_ns/serial.duration_ns)*100 if r2.success else float('nan')
                        row2={'family':fam,'context':ci,'case':si,'method':method,'success':int(r2.success),'verifier_calls':r2.verifier_calls,'constraints':len(r2.constraints),
                              'retains_parallelism':int(r2.success and r2.final_max_parallel_cx>1),'speedup_vs_serial_percent':speed2}
                        fs2.append(row2);all_s2.append(row2)
                    print(f'V3 schedule {fam} ctx={ci} case={si} {method} success={r3.success} constraints={len(r3.constraints)}',flush=True)
            for case in cases[:mixed_cases]:
                st=case['state']
                m=repair_staged_v3(root,st,ctx,sched_methods[0],routing_max_calls=rmax,scheduling_max_calls=smax)
                row={'family':fam,'context':ci,'case':case['case'],'defect_count':case['defect_count'],'success':int(m.success),'routing_success':int(m.routing_success),'scheduling_success':int(m.scheduling_success),
                     'total_verifier_calls':m.total_verifier_calls,'retains_parallelism':int(m.success and int(m.final_max_parallel_cx or 0)>1),'speedup_vs_serial_percent':m.speedup_vs_serial_percent if m.success else ''}
                fst.append(row);all_st.append(row)
                j=repair_cross_layer_portfolio(root,st,ctx,sched_methods[0],routing_max_calls=rmax,scheduling_calls_per_candidate=max(12,smax//2),max_routing_solutions=joint_solutions)
                rowj={'family':fam,'context':ci,'case':case['case'],'defect_count':case['defect_count'],'success':int(j.success),'routing_success':int(j.routing_success),'scheduling_success':int(j.scheduling_success),
                      'routing_candidates_found':j.routing_candidates_found,'total_verifier_calls':j.total_verifier_calls,'total_compiler_edits':j.total_compiler_edits,
                      'retains_parallelism':int(j.success and int(j.final_max_parallel_cx or 0)>1),'speedup_vs_serial_percent':j.speedup_vs_serial_percent if j.success else ''}
                fj.append(rowj);all_j.append(rowj)
        families[fam]=_family_summary(fr3,fr2,fp3,fs3,fsp,fs2,fst,fj)
    payload={'config':cfg,'generated_check_cases':[{'case':c['case'],'defect_count':c['defect_count'],'injected_checks':list(c['injected_checks']),'base_index':c['base_index']} for c in cases],
      'generated_path_cases':[{'case':c['case'],'defect_count':c['defect_count'],'injected_routes':[list(x) for x in c['injected_routes']],'base_index':c['base_index']} for c in path_cases],
      'families':families,'aggregate':{'routing_v3_success':_rate(all_r3),'routing_v2_success':_rate(all_r2),'path_v3_success':_rate(all_p3),
      'schedule_v3_success':_rate(all_s3),'schedule_pure_success':_rate(all_sp),'schedule_v2_success':_rate(all_s2),'mixed_staged_success':_rate(all_st),'mixed_cross_layer_success':_rate(all_j)},
      'elapsed_seconds':time.time()-t0}
    names=[('ft_repair_v3_routing.csv',all_r3),('ft_repair_v3_routing_v2.csv',all_r2),('ft_repair_v3_path.csv',all_p3),
           ('ft_repair_v3_schedule.csv',all_s3),('ft_repair_v3_schedule_pure.csv',all_sp),('ft_repair_v3_schedule_v2.csv',all_s2),
           ('ft_repair_v3_mixed_staged.csv',all_st),('ft_repair_v3_mixed_cross_layer.csv',all_j)]
    for n,r in names:_save_csv(out/n,r)
    (out/'ft_repair_v3_results.json').write_text(json.dumps(payload,indent=2,default=str)+'\n')
    (out/'ft_repair_v3_summary.md').write_text(_markdown(payload)+'\n')
    print('FT REPAIR V3 REPORT:',out/'ft_repair_v3_summary.md',flush=True)
    return payload
