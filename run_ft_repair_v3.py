#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,platform,sys,subprocess,csv
from pathlib import Path
import numpy as np

from ftrepair_v3.experiment import run_all,_save_csv,_family_summary,_rate,_markdown
from ftrepair_v3.mutations import generate_check_choice_cases,generate_path_defect_cases
from ftrepair_v3.routing_cegis import repair_routing_v3
from ftrepair_v3.op_scheduler import repair_operation_schedule_portfolio
from ftrepair_v3.cross_layer import repair_staged_v3,repair_cross_layer_portfolio
from ftrepair_v3.model import RoutingState
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase7_catalog import ensure_catalog

ROOT=Path(__file__).resolve().parent

def load(p):
    q=Path(p);q=q if q.is_absolute() else ROOT/q
    return json.loads(q.read_text())

def doctor():
    import pytest
    print(json.dumps({'branch':'ft-compiler-repair-v3','python':sys.version.split()[0],'executable':sys.executable,
      'platform':platform.platform(),'inside_virtual_environment':sys.prefix!=getattr(sys,'base_prefix',sys.prefix),
      'numpy':np.__version__,'pytest':pytest.__version__,'project_root':str(ROOT)},indent=2))

def inspect_routing():
    ctx=sample_hardware_contexts(1,33101,'hw_id').context(0)
    cases=generate_check_choice_cases(ROOT,ctx,defect_counts=(2,),cases_per_count=1,bases=2)
    if not cases:raise SystemExit('No two-defect case found')
    c=cases[0]
    r=repair_routing_v3(ROOT,c['state'],None,ctx,max_edits=5,max_verifier_calls=48,max_solutions=3,
                        path_alternatives_per_route=4,check_alternatives_per_check=8)
    print(json.dumps({'hidden_injected_checks':list(c['injected_checks']),'result':r.to_dict()},indent=2,default=str))

def inspect_path():
    ctx=sample_hardware_contexts(1,33102,'hw_id').context(0)
    cases=generate_path_defect_cases(ROOT,ctx,defect_counts=(1,),cases_per_count=1,bases=2,max_paths_per_route=5)
    if not cases:
        print(json.dumps({'path_defect_found':False,'note':'No unsafe alternate <=3-hop bridge path found in inspected bases.'},indent=2));return
    c=cases[0]
    r=repair_routing_v3(ROOT,c['state'],None,ctx,max_edits=4,max_verifier_calls=40,max_solutions=3,
                        path_alternatives_per_route=5,check_alternatives_per_check=6)
    print(json.dumps({'path_defect_found':True,'hidden_routes':[list(x) for x in c['injected_routes']],
                      'initial_c1':c['initial_c1'],'result':r.to_dict()},indent=2,default=str))

def inspect_schedule():
    ctx=sample_hardware_contexts(1,11101,'hw_id').context(0)
    labels,hubs=ensure_catalog(ROOT).labels_hubs(0);st=RoutingState.from_parts(labels,hubs)
    r=repair_operation_schedule_portfolio(st,ctx,'shortest_greedy',max_verifier_calls=32,max_constraints=40)
    print(json.dumps(r.to_dict(),indent=2,default=str))

def inspect_cross_layer():
    ctx=sample_hardware_contexts(1,33103,'hw_id').context(0)
    cases=generate_check_choice_cases(ROOT,ctx,defect_counts=(1,),cases_per_count=1,bases=2)
    if not cases:raise SystemExit('No mixed input case found')
    c=cases[0]
    staged=repair_staged_v3(ROOT,c['state'],ctx,'shortest_greedy',routing_max_calls=32,scheduling_max_calls=24)
    joint=repair_cross_layer_portfolio(ROOT,c['state'],ctx,'shortest_greedy',routing_max_calls=44,
                                       scheduling_calls_per_candidate=20,max_routing_solutions=3)
    print(json.dumps({'hidden_injected_checks':list(c['injected_checks']),'staged':staged.to_dict(),
                      'cross_layer':joint.to_dict()},indent=2,default=str))

def _rows(family_dirs,name):
    z=[]
    for d in family_dirs:
        p=d/name
        if p.exists() and p.stat().st_size:
            with p.open() as f:z.extend(list(csv.DictReader(f)))
    return z

def split_run(cfg,out):
    out.mkdir(parents=True,exist_ok=True);family_dirs=[];payloads=[]
    for slot,fam in enumerate(cfg.get('families',[])):
        fd=out/f'_family_{fam}';family_dirs.append(fd);subcfg=dict(cfg);subcfg['families']=[fam];subcfg['family_seed_slots']={fam:slot}
        cp=out/f'_config_{fam}.json';cp.write_text(json.dumps(subcfg,indent=2)+'\n')
        print('FT REPAIR V3 SPLIT',fam,flush=True)
        subprocess.run([sys.executable,str(ROOT/'run_ft_repair_v3.py'),'all','--config',str(cp),'--out',str(fd)],check=True,cwd=ROOT)
        payloads.append(json.loads((fd/'ft_repair_v3_results.json').read_text()))
    names=['ft_repair_v3_routing.csv','ft_repair_v3_routing_v2.csv','ft_repair_v3_path.csv','ft_repair_v3_schedule.csv',
           'ft_repair_v3_schedule_pure.csv','ft_repair_v3_schedule_v2.csv','ft_repair_v3_mixed_staged.csv','ft_repair_v3_mixed_cross_layer.csv']
    rows={n:_rows(family_dirs,n) for n in names}
    families={}
    for p in payloads:families.update(p['families'])
    merged={'config':cfg,
      'generated_check_cases':payloads[0].get('generated_check_cases',[]) if payloads else [],
      'generated_path_cases':payloads[0].get('generated_path_cases',[]) if payloads else [],'families':families,
      'aggregate':{
        'routing_v3_success':_rate(rows['ft_repair_v3_routing.csv']),'routing_v2_success':_rate(rows['ft_repair_v3_routing_v2.csv']),
        'path_v3_success':_rate(rows['ft_repair_v3_path.csv']),'schedule_v3_success':_rate(rows['ft_repair_v3_schedule.csv']),
        'schedule_pure_success':_rate(rows['ft_repair_v3_schedule_pure.csv']),'schedule_v2_success':_rate(rows['ft_repair_v3_schedule_v2.csv']),
        'mixed_staged_success':_rate(rows['ft_repair_v3_mixed_staged.csv']),'mixed_cross_layer_success':_rate(rows['ft_repair_v3_mixed_cross_layer.csv'])},
      'elapsed_seconds':sum(float(p.get('elapsed_seconds',0)) for p in payloads)}
    for n,z in rows.items():_save_csv(out/n,z)
    (out/'ft_repair_v3_results.json').write_text(json.dumps(merged,indent=2,default=str)+'\n')
    (out/'ft_repair_v3_summary.md').write_text(_markdown(merged)+'\n')
    for p in out.glob('_config_*.json'):p.unlink()
    print(f'DONE repair v3 split: {out}')

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    for x in ['doctor','inspect-routing','inspect-path','inspect-schedule','inspect-cross-layer']:sub.add_parser(x)
    a=sub.add_parser('all');a.add_argument('--config',required=True);a.add_argument('--out',required=True)
    s=sub.add_parser('split');s.add_argument('--config',required=True);s.add_argument('--out',required=True)
    args=ap.parse_args()
    if args.cmd=='doctor':return doctor()
    if args.cmd=='inspect-routing':return inspect_routing()
    if args.cmd=='inspect-path':return inspect_path()
    if args.cmd=='inspect-schedule':return inspect_schedule()
    if args.cmd=='inspect-cross-layer':return inspect_cross_layer()
    cfg=load(args.config);out=Path(args.out);out=out if out.is_absolute() else ROOT/out
    if out.exists() and any(out.iterdir()):raise SystemExit(f'Output directory already exists and is nonempty: {out}')
    if args.cmd=='all':
        p=run_all(ROOT,cfg,out);print(f'DONE repair v3: {out} ({p["elapsed_seconds"]:.2f}s)');return
    return split_run(cfg,out)

if __name__=='__main__':main()
