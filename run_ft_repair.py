#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, platform, sys, subprocess, shutil
from pathlib import Path
import numpy as np

from ftrepair.experiment import run_all, merge_family_results
from ftrepair.routing_repair import repair_routing
from ftrepair.schedule_repair import repair_parallel_schedule
from qecflag.phase5_actions import ensure_hardware_action_table
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase7_routing import bridge_native_risk

ROOT = Path(__file__).resolve().parent


def doctor():
    import pytest
    print(json.dumps({
        'python': sys.version.split()[0], 'executable': sys.executable,
        'platform': platform.platform(),
        'inside_virtual_environment': sys.prefix != getattr(sys, 'base_prefix', sys.prefix),
        'numpy': np.__version__, 'pytest': pytest.__version__,
        'project_root': str(ROOT), 'branch': 'ft-compiler-repair-v1',
    }, indent=2))


def load_config(path):
    p=Path(path); p=p if p.is_absolute() else ROOT/p
    return json.loads(p.read_text())


def inspect_routing():
    cat=ensure_catalog(ROOT); table=ensure_hardware_action_table(ROOT)
    ctx=sample_hardware_contexts(1,11101,'hw_id').context(0)
    labels,hubs=cat.labels_hubs(0)
    for action in range(table.n_actions):
        nl=list(labels); nh=list(hubs); nl[0]=table.template_label(action); nh[0]=table.hub(action)
        risk=bridge_native_risk(nl,nh,ctx,compute_c2=False)
        passed=(risk.c1==0.0 and risk.decoder.single_fault_conflicts==0 and risk.decoder.single_fault_failures==0 and risk.decoder.incoming_failures==0)
        if not passed:
            r=repair_routing(ROOT,nl,nh,ctx,max_edits=2,max_verifier_calls=24,witness_check_limit=2)
            print(json.dumps(r.to_dict(), indent=2)); return
    raise SystemExit('No injected unsafe routing case found')


def inspect_schedule():
    cat=ensure_catalog(ROOT); ctx=sample_hardware_contexts(1,11101,'hw_id').context(0)
    labels,hubs=cat.labels_hubs(0)
    r=repair_parallel_schedule(labels,hubs,ctx,'shortest_greedy',max_constraints=15)
    print(json.dumps(r.to_dict(), indent=2))


def main():
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor'); sub.add_parser('inspect-routing'); sub.add_parser('inspect-schedule')
    a=sub.add_parser('all'); a.add_argument('--config',required=True); a.add_argument('--out',required=True)
    sp=sub.add_parser('split'); sp.add_argument('--config',required=True); sp.add_argument('--out',required=True)
    args=ap.parse_args()
    if args.command=='doctor': doctor(); return
    if args.command=='inspect-routing': inspect_routing(); return
    if args.command=='inspect-schedule': inspect_schedule(); return
    cfg=load_config(args.config)
    out=Path(args.out); out=out if out.is_absolute() else ROOT/out
    if args.command=='split':
        if out.exists() and any(out.iterdir()):
            raise SystemExit(f'Output directory already exists and is nonempty: {out}')
        out.mkdir(parents=True, exist_ok=True)
        dirs=[]
        for fam in cfg.get('families',[]):
            famdir=out/f'_family_{fam}'; dirs.append(famdir)
            subcfg=dict(cfg); subcfg['families']=[fam]
            cfgpath=out/f'_config_{fam}.json'; cfgpath.write_text(json.dumps(subcfg,indent=2)+'\n')
            cmd=[sys.executable,str(ROOT/'run_ft_repair.py'),'all','--config',str(cfgpath),'--out',str(famdir)]
            print('FT REPAIR SPLIT',fam,flush=True)
            subprocess.run(cmd,check=True,cwd=str(ROOT))
        payload=merge_family_results(out,dirs,cfg)
        for pth in out.glob('_config_*.json'): pth.unlink()
        print(f'DONE FT repair split: {out} ({payload["elapsed_seconds"]:.2f} family-seconds)')
        return
    if out.exists() and any(out.iterdir()): raise SystemExit(f'Output directory already exists and is nonempty: {out}')
    if out.exists(): out.rmdir()
    p=run_all(ROOT,cfg,out)
    print(f'DONE FT repair fork: {out} ({p["elapsed_seconds"]:.2f} seconds)')

if __name__=='__main__': main()
