#!/usr/bin/env python3
from pathlib import Path
import argparse, json, subprocess, sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from qecflag.phase8_experiment import ensure_continuous_catalog,_choose_proxy,_labels_hubs
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase10_scheduler import (
    schedule_parallel,local_priority_search,beam_priority_search,
    certify_parallel_schedule,summarize_schedule,validate_resource_schedule,
)
from qecflag.phase10_experiment import run_all,merge_family_results


def _split(config_path:Path,out:Path):
    cfg=json.loads(config_path.read_text()); families=list(cfg.get('families',['hw_id']))
    out.mkdir(parents=True,exist_ok=True); parts=out/'parts'; parts.mkdir(exist_ok=True)
    dirs=[]
    for fam in families:
        sub=dict(cfg); sub['families']=[fam]
        c=parts/f'{fam}_config.json'; c.write_text(json.dumps(sub,indent=2)+'\n')
        d=parts/fam
        print('P10 SPLIT:',fam)
        subprocess.run([sys.executable,str(ROOT/'run_phase10.py'),'all','--config',str(c),'--out',str(d)],check=True)
        dirs.append(d)
    merge_family_results(out,dirs,cfg)
    print('PHASE 10 MERGED REPORT:',out/'phase10_summary.md')


def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('doctor'); sub.add_parser('inspect-schedule'); sub.add_parser('inspect-certification')
    a=sub.add_parser('all'); a.add_argument('--config',required=True); a.add_argument('--out',required=True)
    s=sub.add_parser('split'); s.add_argument('--config',required=True); s.add_argument('--out',required=True)
    args=p.parse_args()
    if args.cmd=='doctor':
        print(json.dumps({'python':sys.executable,'project_root':str(ROOT),
                          'inside_virtual_environment':sys.prefix!=getattr(sys,'base_prefix',sys.prefix)},indent=2)); return
    if args.cmd=='split': _split(Path(args.config),Path(args.out)); return
    cat=ensure_continuous_catalog(ROOT); ctx=sample_hardware_contexts(1,10301,'hw_id').context(0)
    e=_choose_proxy(cat['entries'],ctx,4)[0]; labels,hubs=_labels_hubs(e)
    if args.cmd=='inspect-schedule':
        methods={m:schedule_parallel(labels,hubs,ctx,m) for m in ['serialized','ancilla_overlap','asap','noise_greedy','css_block']}
        methods['local_search']=local_priority_search(labels,hubs,ctx)
        methods['beam_search']=beam_priority_search(labels,hubs,ctx,8)[0]
        print(json.dumps({m:{**summarize_schedule(s,ctx),'resource_valid':validate_resource_schedule(s)} for m,s in methods.items()},indent=2)); return
    if args.cmd=='inspect-certification':
        out={}
        for m in ['serialized','ancilla_overlap','asap','noise_greedy','css_block']:
            s=schedule_parallel(labels,hubs,ctx,m); c=certify_parallel_schedule(s,ctx)
            out[m]={**summarize_schedule(s,ctx),**c.__dict__}
        print(json.dumps(out,indent=2)); return
    cfg=json.loads(Path(args.config).read_text()); run_all(ROOT,cfg,Path(args.out))

if __name__=='__main__': main()
