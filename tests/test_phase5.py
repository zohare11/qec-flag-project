from pathlib import Path
import numpy as np

from qecflag.phase4_agent import RoundActorCritic
from qecflag.phase4_env import RoundSynthState
from qecflag.phase5_actions import ensure_hardware_action_table, actions_to_round
from qecflag.phase5_agent import rollout_batch, beam_candidates
from qecflag.phase5_env import HardwareFeatureEncoder
from qecflag.phase5_experiment import HardwareProxyEvaluator, _routing_heuristic
from qecflag.phase5_hardware import (
    EDGES, N_EDGES, N_PHYSICAL, DATA_NODES, HUB_NODES, FLAG_NODES,
    candidate_paths, route_stats, hardware_effective_context, hardware_round_metrics,
    local_hardware_effective_context,
)
from qecflag.phase5_noise import sample_hardware_contexts, FAMILIES
from qecflag.phase4_simulation import simulate

ROOT=Path(__file__).resolve().parents[1]

def _table(): return ensure_hardware_action_table(ROOT)

def test_topology_is_connected_and_mapping_unique():
    seen={0}; frontier=[0]
    adj={i:set() for i in range(N_PHYSICAL)}
    for u,v in EDGES: adj[u].add(v); adj[v].add(u)
    for u in frontier:
        for v in adj[u]:
            if v not in seen: seen.add(v); frontier.append(v)
    assert len(seen)==N_PHYSICAL
    assert len(EDGES)==N_EDGES==17
    occupied=list(DATA_NODES)+list(HUB_NODES)+list(FLAG_NODES.values())
    assert len(occupied)==len(set(occupied))

def test_hardware_action_table_has_template_x_hub_product():
    t=_table()
    assert t.n_actions==96
    assert t.index('H0|0A12A3') is not None
    assert t.index('H1|0A12A3') is not None
    assert t.n_actions**6 > 700_000_000_000
    assert np.count_nonzero(t.hubs==0)==48 and np.count_nonzero(t.hubs==1)==48

def test_candidate_paths_and_direct_route_count():
    batch=sample_hardware_contexts(1,1,'hw_id'); c=batch.context(0)
    assert candidate_paths(5,4)[0] == (5,4)
    s=route_stats(5,4,c)
    assert s.path[0]==5 and s.path[-1]==4
    assert s.native_cx>=1
    if len(s.path)==2: assert s.native_cx==1

def test_hardware_families_shapes_and_nonnegative():
    for i,f in enumerate(FAMILIES):
        b=sample_hardware_contexts(3,10+i,f)
        assert b.logical.shape==(3,6,96)
        assert b.edge_error.shape==(3,17)
        assert b.edge_duration.shape==(3,17)
        assert b.idle_rate.shape==(3,12)
        for j in range(3): b.context(j).validate()

def test_hub_bad_families_shift_simple_routing_heuristic():
    t=_table()
    a=sample_hardware_contexts(12,99,'ood_hub0_bad')
    b=sample_hardware_contexts(12,100,'ood_hub1_bad')
    hub0_use_a=[]; hub0_use_b=[]
    for batch,out in [(a,hub0_use_a),(b,hub0_use_b)]:
        for i in range(len(batch)):
            row=_routing_heuristic(batch.context(i),t)
            out.append(np.mean([t.hub(x)==0 for x in row]))
    assert np.mean(hub0_use_a) < 0.35
    assert np.mean(hub0_use_b) > 0.65

def test_local_effective_context_and_full_effective_context_valid():
    t=_table(); c=sample_hardware_contexts(1,101,'hw_id').context(0)
    eff,d=local_hardware_effective_context(0,t.template_label(0),t.hub(0),c)
    assert eff.shape==(96,) and np.isfinite(eff).all() and np.all(eff>=0)
    assert d['native_cx']>0 and d['duration_ns']>0
    row=(0,)*6; labels,hubs=actions_to_round(row,t)
    full,detail=hardware_effective_context(labels,hubs,c)
    assert full.shape==(6,96) and np.isfinite(full).all() and np.all(full>=0)
    assert detail['native_cx']>0 and detail['duration_ns']>0 and detail['total_data_idle_ns']>0

def test_positive_idle_exposure_does_not_reduce_same_schedule_c2():
    t=_table(); batch=sample_hardware_contexts(1,102,'hw_id'); c=batch.context(0)
    row=(t.index('H0|0A12A3'),)*6; labels,hubs=actions_to_round(row,t)
    low=type(c)(c.logical,c.edge_error,c.edge_duration,c.prep_scale,c.meas_scale,np.zeros_like(c.idle_rate))
    high=type(c)(c.logical,c.edge_error,c.edge_duration,c.prep_scale,c.meas_scale,c.idle_rate*5)
    assert hardware_round_metrics(labels,hubs,high).c2 >= hardware_round_metrics(labels,hubs,low).c2

def test_hardware_encoder_rollout_and_beam_shapes():
    t=_table(); b=sample_hardware_contexts(5,103,'hw_train')
    e=HardwareFeatureEncoder(t); e.fit(b)
    m=RoundActorCritic(e.n_features,t.n_actions,hidden=24,seed=1)
    r=rollout_batch(m,e,b,np.random.default_rng(2))
    assert r.choices.shape==(5,6) and r.features.shape[0]==30
    rows=beam_candidates(m,e,b.context(0),4)
    assert len(rows)==4 and len(set(rows))==4 and all(len(x)==6 for x in rows)

def test_hardware_proxy_shapes_and_finite():
    t=_table(); p=HardwareProxyEvaluator.build(ROOT,t); b=sample_hardware_contexts(2,104,'hw_train')
    costs=p.all_costs(b)
    assert costs.shape==(2,6,96) and np.isfinite(costs).all() and np.all(costs>=0)
    choices=costs.argmin(axis=2)
    rewards=p.rewards_from_costs(costs,choices)
    assert rewards.shape==(2,) and np.isfinite(rewards).all()

def test_hardware_metrics_are_finite_and_include_physical_counts():
    t=_table(); c=sample_hardware_contexts(1,105,'hw_id').context(0)
    row=tuple([t.index('H0|0A12A3')]*6); labels,hubs=actions_to_round(row,t)
    m=hardware_round_metrics(labels,hubs,c)
    assert m.c2>0 and np.isfinite(m.c2)
    assert m.native_cx>=36 and m.duration_ns>0
    assert 0<=m.hub0_fraction<=1

def test_reduced_finite_p_zero_has_no_failures():
    t=_table(); c=sample_hardware_contexts(1,106,'hw_id').context(0)
    row=tuple([t.index('H0|0A12A3')]*6); labels,hubs=actions_to_round(row,t)
    eff,_=hardware_effective_context(labels,hubs,c)
    r=simulate(labels,eff,0.0,200,1)
    assert r['failures']==0
