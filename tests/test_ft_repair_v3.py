from pathlib import Path

from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase6_native import simulate_native
from ftrepair_v3.hittingset_bb import hybrid_hitting_set
from ftrepair_v3.model import RoutingState, physical_path_candidates, build_plan
from ftrepair_v3.mutations import generate_check_choice_cases, generate_path_defect_cases
from ftrepair_v3.routing_cegis import repair_routing_v3
from ftrepair_v3.op_scheduler import repair_operation_schedule_portfolio

ROOT=Path(__file__).resolve().parents[1]


def test_hybrid_hitting_set_covers_larger_universe():
    clauses=[{('a',i),('shared',0)} for i in range(40)]
    sol=hybrid_hitting_set(clauses,weights={('shared',0):0.5},max_size=4)
    assert sol==(('shared',0),)


def test_custom_path_plan_preserves_ideal_endpoint_semantics():
    ctx=sample_hardware_contexts(1,33102,'hw_id').context(0)
    labels,hubs=ensure_catalog(ROOT).labels_hubs(0)
    base=RoutingState.from_parts(labels,hubs)
    paths=physical_path_candidates(base,0,0,ctx,max_paths=4,include_data_interiors=True)
    assert len(paths)>=1
    for p in paths[:2]:
        st=base.with_path(0,0,p)
        plan=build_plan(st,ctx)
        data,obs=simulate_native(plan)
        assert data==0 and obs==0


def test_v3_repairs_reference_single_hidden_check():
    ctx=sample_hardware_contexts(1,11101,'hw_id').context(0)
    cases=generate_check_choice_cases(ROOT,ctx,defect_counts=(1,),cases_per_count=1,bases=1)
    assert cases
    c=cases[0]
    r=repair_routing_v3(ROOT,c['state'],None,ctx,max_edits=4,max_verifier_calls=20,
                        max_solutions=1,path_alternatives_per_route=2,check_alternatives_per_check=5)
    assert r.success and r.final_c1==0.0
    assert set(c['injected_checks']).issubset(set(r.witness_checks_seen))


def test_v3_repairs_physical_path_defect_when_available():
    ctx=sample_hardware_contexts(1,33102,'hw_id').context(0)
    cases=generate_path_defect_cases(ROOT,ctx,defect_counts=(1,),cases_per_count=1,bases=1,max_paths_per_route=5)
    assert cases
    c=cases[0]
    r=repair_routing_v3(ROOT,c['state'],None,ctx,max_edits=4,max_verifier_calls=36,
                        max_solutions=1,path_alternatives_per_route=5,check_alternatives_per_check=5)
    assert r.success and r.final_c1==0.0
    assert set(c['injected_routes']).intersection(set(r.witness_routes_seen))


def test_operation_level_portfolio_restores_ft_and_keeps_cx_concurrency():
    ctx=sample_hardware_contexts(1,11101,'hw_id').context(0)
    labels,hubs=ensure_catalog(ROOT).labels_hubs(0)
    st=RoutingState.from_parts(labels,hubs)
    r=repair_operation_schedule_portfolio(st,ctx,'shortest_greedy',max_verifier_calls=24,max_constraints=40)
    assert r.success and r.final_c1==0.0
    assert r.final_max_parallel_cx>=2
    assert r.speedup_vs_serial_percent is not None and r.speedup_vs_serial_percent>0


def test_cross_layer_portfolio_returns_exactly_safe_combination():
    from ftrepair_v3.cross_layer import repair_cross_layer_portfolio
    ctx=sample_hardware_contexts(1,11101,'hw_id').context(0)
    c=generate_check_choice_cases(ROOT,ctx,defect_counts=(1,),cases_per_count=1,bases=1)[0]
    r=repair_cross_layer_portfolio(ROOT,c['state'],ctx,'shortest_greedy',routing_max_calls=20,
                                   scheduling_calls_per_candidate=12,max_routing_solutions=1)
    assert r.success and r.routing_success and r.scheduling_success
    assert r.final_max_parallel_cx is not None and r.final_max_parallel_cx>=2
