#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,platform,sys,subprocess
from pathlib import Path
import numpy as np
from ftrepair_v2.experiment import run_all
from ftrepair_v2.mutations import generate_multidefect_cases
from ftrepair_v2.routing_cegis import repair_routing_multidefect
from ftrepair_v2.schedule_cegis import repair_parallel_schedule_portfolio, repair_parallel_schedule_cegis
from ftrepair_v2.mixed_repair import repair_mixed
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase7_catalog import ensure_catalog
ROOT=Path(__file__).resolve().parent

def load(p):
    q=Path(p);q=q if q.is_absolute() else ROOT/q;return json.loads(q.read_text())

def doctor():
    import pytest
    print(json.dumps({'branch':'ft-compiler-repair-v2','python':sys.version.split()[0],'executable':sys.executable,
      'platform':platform.platform(),'inside_virtual_environment':sys.prefix!=getattr(sys,'base_prefix',sys.prefix),
      'numpy':np.__version__,'pytest':pytest.__version__,'project_root':str(ROOT)},indent=2))

def inspect_multidefect():
    ctx=sample_hardware_contexts(1,22101,'hw_id').context(0)
    cases=generate_multidefect_cases(ROOT,ctx,defect_counts=(2,),cases_per_count=1,bases=2)
    if not cases: raise SystemExit('No two-defect case found')
    c=cases[0];r=repair_routing_multidefect(ROOT,c['labels'],c['hubs'],ctx,max_edits=4,max_verifier_calls=48,alternatives_per_check=4)
    print(json.dumps({'hidden_injected_checks':c['injected_checks'],'result':r.to_dict()},indent=2))

def inspect_schedule():
    ctx=sample_hardware_contexts(1,11101,'hw_id').context(0);labels,hubs=ensure_catalog(ROOT).labels_hubs(0)
    r=repair_parallel_schedule_portfolio(labels,hubs,ctx,'shortest_greedy',max_constraints=15,max_verifier_calls=32)
    print(json.dumps(r.to_dict(),indent=2))

def inspect_mixed():
    ctx=sample_hardware_contexts(1,11101,'hw_id').context(0)
    c=generate_multidefect_cases(ROOT,ctx,defect_counts=(1,),cases_per_count=1,bases=2)[0]
    r=repair_mixed(ROOT,c['labels'],c['hubs'],ctx,'shortest_greedy',routing_max_edits=3,routing_max_calls=32,schedule_max_calls=24)
    print(json.dumps({'hidden_injected_checks':c['injected_checks'],'result':r.to_dict()},indent=2))

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    for x in ['doctor','inspect-multidefect','inspect-schedule','inspect-mixed']:sub.add_parser(x)
    a=sub.add_parser('all');a.add_argument('--config',required=True);a.add_argument('--out',required=True)
    sp=sub.add_parser('split');sp.add_argument('--config',required=True);sp.add_argument('--out',required=True)
    args=ap.parse_args()
    if args.cmd=='doctor':return doctor()
    if args.cmd=='inspect-multidefect':return inspect_multidefect()
    if args.cmd=='inspect-schedule':return inspect_schedule()
    if args.cmd=='inspect-mixed':return inspect_mixed()
    cfg=load(args.config);out=Path(args.out);out=out if out.is_absolute() else ROOT/out
    if out.exists() and any(out.iterdir()):raise SystemExit(f'Output directory already exists and is nonempty: {out}')
    if args.cmd=='all':
        p=run_all(ROOT,cfg,out);print(f'DONE repair v2: {out} ({p["elapsed_seconds"]:.2f}s)');return
    # Family-isolated split to bound memory and make long runs restartable.
    out.mkdir(parents=True,exist_ok=True);family_dirs=[];payloads=[]
    for fam in cfg.get('families',[]):
        fd=out/f'_family_{fam}';family_dirs.append(fd);subcfg=dict(cfg);subcfg['families']=[fam]
        cp=out/f'_config_{fam}.json';cp.write_text(json.dumps(subcfg,indent=2)+'\n')
        print('FT REPAIR V2 SPLIT',fam,flush=True)
        subprocess.run([sys.executable,str(ROOT/'run_ft_repair_v2.py'),'all','--config',str(cp),'--out',str(fd)],check=True,cwd=ROOT)
        payloads.append(json.loads((fd/'ft_repair_v2_results.json').read_text()))
    # Merge rows and recompute by reusing a lightweight merge here.
    import csv
    def rows(name):
        z=[]
        for d in family_dirs:
            p=d/name
            if p.exists() and p.stat().st_size:
                with p.open() as f:z.extend(list(csv.DictReader(f)))
        return z
    r2=rows('ft_repair_v2_routing.csv');r1=rows('ft_repair_v2_routing_v1.csv');s2=rows('ft_repair_v2_scheduling.csv');sp=rows('ft_repair_v2_scheduling_pure.csv');s1=rows('ft_repair_v2_scheduling_v1.csv');m=rows('ft_repair_v2_mixed.csv')
    from ftrepair_v2.experiment import _save_csv,_markdown,_rate
    families={}
    for p in payloads:families.update(p['families'])
    merged={'config':cfg,'generated_cases':payloads[0].get('generated_cases',[]) if payloads else [],'families':families,
            'aggregate':{'routing_v2_success':_rate(r2),'routing_v1_success':_rate(r1),'schedule_v2_success':_rate(s2),'schedule_pure_success':_rate(sp),'schedule_v1_success':_rate(s1),'mixed_v2_success':_rate(m)},
            'elapsed_seconds':sum(float(p.get('elapsed_seconds',0)) for p in payloads)}
    _save_csv(out/'ft_repair_v2_routing.csv',r2);_save_csv(out/'ft_repair_v2_routing_v1.csv',r1);_save_csv(out/'ft_repair_v2_scheduling.csv',s2);_save_csv(out/'ft_repair_v2_scheduling_pure.csv',sp);_save_csv(out/'ft_repair_v2_scheduling_v1.csv',s1);_save_csv(out/'ft_repair_v2_mixed.csv',m)
    (out/'ft_repair_v2_results.json').write_text(json.dumps(merged,indent=2)+'\n');(out/'ft_repair_v2_summary.md').write_text(_markdown(merged)+'\n')
    for p in out.glob('_config_*.json'):p.unlink()
    print(f'DONE repair v2 split: {out}')
if __name__=='__main__':main()
