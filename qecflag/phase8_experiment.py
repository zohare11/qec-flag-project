"""Phase 8 experiment: gate-resolved idling + repeated Steane memory rounds."""
from __future__ import annotations
from pathlib import Path
import csv, json, time
import numpy as np

from .phase5_noise import sample_hardware_contexts
from .phase7_catalog import ensure_catalog
from .phase7_routing import bridge_proxy_metrics
from .phase8_timing import (
    build_timed_bridge_plan, timed_single_fault_certificate,
    simulate_repeated_finite_p, simulate_repeated_finite_p_history,
)

CACHE_NAME='phase8_continuous_idle_catalog.json'
SCHEMA=1


def _save_csv(path, rows):
    if not rows: path.write_text(''); return
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def build_continuous_catalog(project_root: Path, progress: bool=False):
    root=Path(project_root); p7=ensure_catalog(root)
    nominal=sample_hardware_contexts(1,8101,'hw_id').context(0)
    entries=[]
    for i,e in enumerate(p7.entries):
        cert=timed_single_fault_certificate(e['labels'],e['hubs'],nominal)
        if cert.passed:
            ee=dict(e); ee['phase8_duration_ns']=cert.duration_ns; ee['phase8_idle_locations']=cert.idle_locations
            ee['phase8_fault_outcomes']=cert.fault_outcomes; entries.append(ee)
        if progress and (i+1)%10==0: print(f'P8 CERT {i+1}/{len(p7)} safe={len(entries)}')
    payload={'metadata':{
        'schema':SCHEMA,'source_phase7_catalog_size':len(p7),'catalog_size':len(entries),
        'prep_ns':100.0,'meas_ns':500.0,
        'idle_model':'explicit per serialized prep/CX/meas interval on every inactive persistent data qubit',
        'certification':'C1=0, zero single-fault conflicts/failures, zero incoming-single-error failures',
    },'entries':entries}
    path=root/'cache'/CACHE_NAME; path.parent.mkdir(exist_ok=True); path.write_text(json.dumps(payload,indent=2)+'\n')
    return payload


def ensure_continuous_catalog(project_root: Path, progress=False):
    path=Path(project_root)/'cache'/CACHE_NAME
    if path.exists():
        p=json.loads(path.read_text())
        if p.get('metadata',{}).get('schema')==SCHEMA:return p
    return build_continuous_catalog(project_root,progress)


def _labels_hubs(e): return tuple(e['labels']),tuple(int(x) for x in e['hubs'])

def _choose_proxy(entries,context,budget):
    scored=[]
    for i,e in enumerate(entries):
        labels,hubs=_labels_hubs(e); m=bridge_proxy_metrics(labels,hubs,context)
        scored.append((m.c2,m.native_cx,m.duration_ns,i))
    scored.sort(); return [entries[x[-1]] for x in scored[:min(budget,len(scored))]]


def _choose_fixed(entries,contexts):
    vals=[]
    for i,e in enumerate(entries):
        labels,hubs=_labels_hubs(e)
        vals.append((np.mean([bridge_proxy_metrics(labels,hubs,c).c2 for c in contexts]),i))
    return entries[min(vals)[1]]


def _markdown(summary):
    m=summary['catalog']['metadata']; cfg=summary['config']
    lines=['# Phase 8 summary','',
      'Scope: gate-resolved serialized timing/idle validation of Phase-7 certified bridge circuits, followed by repeated-round Steane memory diagnostics.','',
      'Idle faults are explicit during every preparation block, native CNOT interval, and measurement block for each inactive persistent data qubit.','',
      f"- Phase-7 source catalog: {m['source_phase7_catalog_size']}",
      f"- Still single-fault certified after gate-resolved idling: {m['catalog_size']}",
      f"- Repeated extraction rounds: {cfg['rounds']}",
      f"- Primary repeated-round decoder: minimum-weight fault-history decoder over full syndrome+flag history",
      f"- Baseline repeated-round decoder: temporal-majority syndrome + Steane minimum-weight correction",'',
      '## Continuous-idle certification','']
    c=summary['continuous_validation']
    lines += [f"- Rechecked circuits: {c['checked']}",f"- Passed: {c['passed']}",f"- Failed: {c['failed']}", '']
    for fam,methods in summary['repeated'].items():
        lines += [f'## {fam}','', '| Method | Mean round duration (us) | Mean native CX/round | p | Mean logical failure rate |',
                  '|---|---:|---:|---:|---:|']
        for method,rows in methods.items():
            for p in sorted({r['p'] for r in rows}):
                rr=[r for r in rows if r['p']==p]
                lines.append(f"| {method} | {np.mean([r['duration_us_per_round'] for r in rr]):.3f} | {np.mean([r['native_cx_per_round'] for r in rr]):.1f} | {p} | {np.mean([r['logical_failure_rate'] for r in rr]):.7f} |")
        lines.append('')
    lines += ['## Interpretation constraints','',
      '- The primary decoder is an exact small-code minimum-weight fault-history lookup over full syndrome+flag history; it is not MWPM/PyMatching.',
      '- Temporal-majority Steane decoding is retained as a weaker recognizable baseline.',
      '- This remains a synthetic 12-node hardware model; no named device calibration is used.',
      '- Native bridge CNOT faults are explicit and data idling is now resolved at each serialized prep/CX/meas interval.',
      '- Checks remain serialized; Phase 8 does not optimize parallel schedules or resource contention.',
      '- Repeated rounds reuse the same routed extraction circuit without ideal recovery between rounds.',
      '- The primary repeated-round decoder uses the complete noisy syndrome+flag history plus an ideal final memory-boundary syndrome; it is a small-code exact minimum-weight lookup, not MWPM/PyMatching.',
      '- The repeated-round Monte Carlo superposes Pauli fault signatures, valid for this Clifford/Pauli model.',
      '- A positive result here validates the Phase-7 physical catalog under a stronger idle/time model; it does not establish device-level fault tolerance.','']
    return '\n'.join(lines)


def run_all(project_root:Path,cfg:dict,out_dir:Path):
    t0=time.time(); root=Path(project_root); out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    cat=ensure_continuous_catalog(root,progress=True); entries=cat['entries']
    if not entries: raise RuntimeError('No Phase-7 circuit survives gate-resolved idle certification')
    seed=int(cfg.get('seed',8201)); nctx=int(cfg.get('contexts_per_family',1)); budget=int(cfg.get('search_budget',4))
    rounds=int(cfg.get('rounds',3)); ps=[float(x) for x in cfg.get('p',[2e-4])]; shots=int(cfg.get('shots',5000))
    families=list(cfg.get('families',['hw_id']))
    train=sample_hardware_contexts(int(cfg.get('fixed_train_contexts',4)),seed+1,'hw_train')
    fixed=_choose_fixed(entries,[train.context(i) for i in range(len(train))])
    rows=[]; repeated={}
    for fi,fam in enumerate(families):
        batch=sample_hardware_contexts(nctx,seed+100*fi+10,fam); repeated[fam]={}
        for ci in range(nctx):
            ctx=batch.context(ci)
            proxy=_choose_proxy(entries,ctx,budget)[0]
            rng=np.random.default_rng(seed+1000*fi+ci)
            rand=entries[int(rng.integers(len(entries)))]
            methods={'certified_fixed':fixed,'certified_proxy':proxy,'certified_random':rand}
            for method,e in methods.items():
                labels,hubs=_labels_hubs(e)
                cert=timed_single_fault_certificate(labels,hubs,ctx)
                rows.append({'family':fam,'context':ci,'method':method,'ft_pass':cert.passed,'c1':cert.c1,
                             'single_fault_failures':cert.single_fault_failures,'conflicts':cert.conflicts,
                             'incoming_failures':cert.incoming_failures,'native_cx':cert.native_cx,
                             'duration_us':cert.duration_ns/1000.0,'idle_locations':cert.idle_locations})
                plan=build_timed_bridge_plan(labels,hubs,ctx)
                repeated[fam].setdefault(method,[])
                for pi,p in enumerate(ps):
                    base_seed=seed+100000*fi+10000*ci+100*pi+sum(ord(ch) for ch in method)%97
                    r=simulate_repeated_finite_p_history(plan,ctx,rounds,p,shots,base_seed)
                    r['decoder_name']='history_mw'
                    repeated[fam][method].append(r)
                    # Keep the simpler temporal-majority decoder as a diagnostic baseline only.
                    if method=='certified_proxy':
                        rb=simulate_repeated_finite_p(plan,ctx,rounds,p,shots,base_seed+1)
                        rb['decoder_name']='temporal_majority'
                        repeated[fam].setdefault('certified_proxy_majority_baseline',[]).append(rb)
            print(f'P8 EVAL {fam} {ci+1}/{nctx}: proxy_ft={rows[-2]["ft_pass"]}')
    _save_csv(out/'phase8_continuous_validation.csv',rows)
    flat=[]
    for fam,methods in repeated.items():
        for method,rr in methods.items():
            for r in rr: flat.append({'family':fam,'method':method,**r})
    _save_csv(out/'phase8_repeated_memory.csv',flat)
    payload={'config':cfg,'catalog':cat,
             'continuous_validation':{'checked':len(rows),'passed':sum(r['ft_pass'] for r in rows),'failed':sum(not r['ft_pass'] for r in rows)},
             'repeated':repeated,'elapsed_seconds':time.time()-t0}
    # Avoid duplicating the full 74-entry catalog in the results JSON.
    payload['catalog']={'metadata':cat['metadata']}
    (out/'phase8_results.json').write_text(json.dumps(payload,indent=2)+'\n')
    (out/'phase8_summary.md').write_text(_markdown(payload)+'\n')
    print('PHASE 8 REPORT:',out/'phase8_summary.md')
    return payload
