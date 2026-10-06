"""Controlled multi-defect benchmark generation for FT compiler repair v2."""
from __future__ import annotations
from pathlib import Path
from itertools import combinations

from qecflag.phase5_actions import ensure_hardware_action_table
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase7_routing import bridge_native_risk
from qecflag.phase4_physics import verification_summary


def _logical_ft(labels) -> bool:
    v = verification_summary(tuple(labels))
    return bool(v['single_fault_conflicts'] == 0 and v['single_fault_logical_failures'] == 0
                and v['single_incoming_error_failures'] == 0)


def _physical_pass(labels,hubs,context) -> bool:
    r=bridge_native_risk(labels,hubs,context,compute_c2=False)
    return bool(r.c1==0 and r.decoder.single_fault_conflicts==0 and r.decoder.single_fault_failures==0 and r.decoder.incoming_failures==0)


def single_defect_pool(project_root: Path, context, bases: int = 8, per_check: int = 4) -> list[dict]:
    """Find local compiler-choice mutations that preserve logical FT but break physical FT."""
    root=Path(project_root); cat=ensure_catalog(root,progress=False); table=ensure_hardware_action_table(root)
    pool=[]
    for bi in range(min(int(bases),len(cat))):
        labels,hubs=cat.labels_hubs(bi)
        for ci in range(6):
            found=0
            for action in range(table.n_actions):
                nl=list(labels); nh=list(hubs)
                nl[ci]=table.template_label(action); nh[ci]=table.hub(action)
                if nl[ci]==labels[ci] and int(nh[ci])==int(hubs[ci]): continue
                if not _logical_ft(nl): continue
                if _physical_pass(nl,nh,context): continue
                pool.append({'base_index':bi,'check':ci,'action':action,'label':nl[ci],'hub':int(nh[ci]),
                             'base_labels':tuple(labels),'base_hubs':tuple(hubs)})
                found += 1
                if found >= int(per_check): break
    return pool


def generate_multidefect_cases(project_root: Path, context, defect_counts=(1,2,3), cases_per_count=4,
                               bases: int = 8) -> list[dict]:
    """Create hidden 1/2/3-defect cases without exposing locations to repair.

    Defects are composed only when they share the same certified base and occur
    on distinct checks.  Combined inputs must remain logically FT and physically
    unsafe.  The ground-truth mutated checks are retained only for evaluation.
    """
    pool=single_defect_pool(project_root,context,bases=bases,per_check=1)
    bybase={}
    for x in pool: bybase.setdefault(x['base_index'],[]).append(x)
    out=[]; seen=set()
    for k in defect_counts:
        need=int(cases_per_count)
        for bi,items in sorted(bybase.items()):
            # Prefer one canonical mutation per check for combinatorial diversity.
            first={}
            for x in items: first.setdefault(x['check'],x)
            checks=sorted(first)
            for subset in combinations(checks,int(k)):
                base=first[subset[0]]
                labels=list(base['base_labels']); hubs=list(base['base_hubs']); acts=[]
                for ci in subset:
                    x=first[ci]; labels[ci]=x['label']; hubs[ci]=x['hub']; acts.append(x['action'])
                sig=(tuple(labels),tuple(hubs))
                if sig in seen or not _logical_ft(labels) or _physical_pass(labels,hubs,context):
                    continue
                seen.add(sig)
                out.append({'case':len(out),'defect_count':int(k),'base_index':int(bi),
                            'injected_checks':tuple(map(int,subset)),'injected_actions':tuple(map(int,acts)),
                            'labels':tuple(labels),'hubs':tuple(hubs),
                            'base_labels':tuple(base['base_labels']),'base_hubs':tuple(base['base_hubs'])})
                need -= 1
                if need<=0: break
            if need<=0: break
    return out
