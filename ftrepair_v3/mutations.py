"""Harder compiler-mutation benchmarks for FT repair v3."""
from __future__ import annotations
from itertools import combinations
from pathlib import Path

from qecflag.phase7_catalog import ensure_catalog
from ftrepair_v2.mutations import generate_multidefect_cases as generate_v2_cases

from .model import RoutingState, physical_path_candidates, passed_native_risk
from .cache import RoutingVerifierCache


def generate_check_choice_cases(project_root:Path,context,defect_counts=(1,2,3),cases_per_count=2,bases=6):
    """V2-style hidden local template/hub mutations, normalized to v3 states."""
    raw=generate_v2_cases(project_root,context,defect_counts=defect_counts,
                          cases_per_count=cases_per_count,bases=bases)
    out=[]
    for x in raw:
        y=dict(x);y['defect_type']='check_choice';y['state']=RoutingState.from_parts(x['labels'],x['hubs'])
        y['base_state']=RoutingState.from_parts(x['base_labels'],x['base_hubs'])
        out.append(y)
    return out


def single_path_defect_pool(project_root:Path,context,bases:int=4,max_paths_per_route:int=5,
                            max_pool:int=24,cache:RoutingVerifierCache|None=None):
    """Find semantics-preserving physical path choices that destroy first-order FT."""
    root=Path(project_root);cat=ensure_catalog(root,progress=False);cache=RoutingVerifierCache() if cache is None else cache
    pool=[]
    for bi in range(min(int(bases),len(cat))):
        labels,hubs=cat.labels_hubs(bi);base=RoutingState.from_parts(labels,hubs)
        # Catalog entries are known safe, but cache the fact if needed later.
        for c in range(6):
            # Six logical interactions per one-flag template, seven/eight for two-flag;
            # infer count through route candidate access until IndexError.
            r=0
            while True:
                try:paths=physical_path_candidates(base,c,r,context,max_paths=max_paths_per_route,include_data_interiors=True)
                except IndexError:break
                except ValueError:break
                current=paths[0]
                for p in paths[1:]:
                    cand=base.with_path(c,r,p)
                    risk=cache.evaluate(cand,context,compute_c2=False)
                    if not passed_native_risk(risk):
                        pool.append({'base_index':bi,'check':c,'route':r,'path':tuple(p),
                                     'base_state':base,'state':cand,'initial_c1':float(risk.c1)})
                        break
                if len(pool)>=int(max_pool):return pool
                r+=1
    return pool


def generate_path_defect_cases(project_root:Path,context,defect_counts=(1,2),cases_per_count=2,
                               bases:int=4,max_paths_per_route:int=5,cache:RoutingVerifierCache|None=None):
    cache=RoutingVerifierCache() if cache is None else cache
    pool=single_path_defect_pool(project_root,context,bases,max_paths_per_route,cache=cache)
    bybase={}
    for x in pool:bybase.setdefault(x['base_index'],[]).append(x)
    out=[];seen=set()
    for k in defect_counts:
        need=int(cases_per_count)
        for bi,items in sorted(bybase.items()):
            # One canonical unsafe path mutation per distinct physical route.
            first={}
            for x in items:first.setdefault((x['check'],x['route']),x)
            keys=sorted(first)
            for subset in combinations(keys,int(k)):
                base=first[subset[0]]['base_state'];m=base.override_map
                for key in subset:m[key]=first[key]['path']
                st=RoutingState.from_parts(base.labels,base.hubs,m)
                if st.signature() in seen:continue
                risk=cache.evaluate(st,context,compute_c2=False)
                if passed_native_risk(risk):continue
                seen.add(st.signature())
                out.append({'case':len(out),'defect_type':'path','defect_count':int(k),'base_index':int(bi),
                            'injected_routes':tuple(subset),'injected_checks':tuple(sorted(set(c for c,_ in subset))),
                            'state':st,'base_state':base,'initial_c1':float(risk.c1)})
                need-=1
                if need<=0:break
            if need<=0:break
    return out


def generate_mixed_lowering_cases(project_root:Path,context,cases:int=2,bases:int=4,
                                  cache:RoutingVerifierCache|None=None):
    """Combine one hidden check-choice mutation with one hidden path mutation."""
    cache=RoutingVerifierCache() if cache is None else cache
    cc=generate_check_choice_cases(project_root,context,defect_counts=(1,),cases_per_count=max(2,cases),bases=bases)
    pp=single_path_defect_pool(project_root,context,bases=bases,max_pool=24,cache=cache)
    out=[]
    for a in cc:
        for b in pp:
            if a['base_index']!=b['base_index']:continue
            base=a['base_state'];st=RoutingState.from_parts(a['state'].labels,a['state'].hubs,{(b['check'],b['route']):b['path']})
            risk=cache.evaluate(st,context,compute_c2=False)
            if passed_native_risk(risk):continue
            out.append({'case':len(out),'defect_type':'mixed_lowering','defect_count':2,'base_index':a['base_index'],
                        'injected_checks':tuple(sorted(set(a['injected_checks'])|{b['check']})),
                        'injected_routes':((b['check'],b['route']),),'state':st,'base_state':base,
                        'initial_c1':float(risk.c1)})
            if len(out)>=int(cases):return out
    return out
