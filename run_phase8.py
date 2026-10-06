#!/usr/bin/env python3
from pathlib import Path
import argparse, json, sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from qecflag.phase8_experiment import build_continuous_catalog, run_all
from qecflag.phase8_timing import build_timed_bridge_plan, timed_single_fault_certificate
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase5_noise import sample_hardware_contexts


def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('doctor'); sub.add_parser('build-cache'); sub.add_parser('inspect-timing')
    a=sub.add_parser('all'); a.add_argument('--config',required=True); a.add_argument('--out',required=True)
    args=p.parse_args()
    if args.cmd=='doctor':
        print(json.dumps({'python':sys.executable,'project_root':str(ROOT),'inside_virtual_environment':sys.prefix!=getattr(sys,'base_prefix',sys.prefix)},indent=2)); return
    if args.cmd=='build-cache':
        x=build_continuous_catalog(ROOT,progress=True); print(json.dumps(x['metadata'],indent=2)); return
    if args.cmd=='inspect-timing':
        cat=ensure_catalog(ROOT); e=cat.entries[0]; ctx=sample_hardware_contexts(1,8301,'hw_id').context(0)
        plan=build_timed_bridge_plan(e['labels'],e['hubs'],ctx); cert=timed_single_fault_certificate(e['labels'],e['hubs'],ctx)
        print(json.dumps({'labels':e['labels'],'hubs':e['hubs'],'native_cx':plan.native.native_cx,'duration_us':plan.duration_ns/1000,
                          'data_idle_us':[x/1000 for x in plan.data_idle_ns],'events':len(plan.events),
                          'certificate':cert.__dict__},indent=2)); return
    cfg=json.loads(Path(args.config).read_text()); run_all(ROOT,cfg,Path(args.out))
if __name__=='__main__': main()
