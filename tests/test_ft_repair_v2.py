from pathlib import Path
from ftrepair_v2.hittingset import minimum_weight_hitting_set
from ftrepair_v2.mutations import generate_multidefect_cases
from ftrepair_v2.routing_cegis import repair_routing_multidefect
from ftrepair_v2.schedule_cegis import repair_parallel_schedule_portfolio
from ftrepair_v2.mixed_repair import repair_mixed
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase7_catalog import ensure_catalog
ROOT=Path(__file__).resolve().parents[1]

def test_exact_hitting_set_minimizes_cardinality_then_weight():
    clauses=[{(0,1),(0,2)},{(0,2),(1,2)}]
    sol=minimum_weight_hitting_set(clauses,weights={(0,1):0.1,(0,2):0.9,(1,2):0.1})
    assert sol==((0,2),)

def _two_defect_case():
    ctx=sample_hardware_contexts(1,11101,'hw_id').context(0)
    cases=generate_multidefect_cases(ROOT,ctx,defect_counts=(2,),cases_per_count=1,bases=2)
    assert cases
    return ctx,cases[0]

def test_multidefect_generator_hides_two_distinct_bad_checks():
    _ctx,c=_two_defect_case()
    assert c['defect_count']==2 and len(set(c['injected_checks']))==2

def test_multidefect_cegis_can_repair_reference_case():
    ctx,c=_two_defect_case()
    r=repair_routing_multidefect(ROOT,c['labels'],c['hubs'],ctx,max_edits=5,max_verifier_calls=80)
    assert r.success and r.final_c1==0.0
    assert set(c['injected_checks']).issubset(set(r.witness_checks_seen))

def test_global_schedule_cegis_repairs_reference_and_keeps_parallelism():
    ctx=sample_hardware_contexts(1,11101,'hw_id').context(0)
    labels,hubs=ensure_catalog(ROOT).labels_hubs(0)
    r=repair_parallel_schedule_portfolio(labels,hubs,ctx,'shortest_greedy',max_constraints=15,max_verifier_calls=24)
    assert r.success and r.final_c1==0.0
    assert r.final_max_parallel_cx>=2

def test_mixed_repair_pipeline_can_restore_lowering_and_schedule():
    ctx=sample_hardware_contexts(1,11101,'hw_id').context(0)
    cases=generate_multidefect_cases(ROOT,ctx,defect_counts=(1,),cases_per_count=1,bases=2)
    assert cases
    c=cases[0]
    r=repair_mixed(ROOT,c['labels'],c['hubs'],ctx,'shortest_greedy',routing_max_edits=3,routing_max_calls=32,schedule_max_calls=24)
    assert r.routing_success
    assert r.success
    assert r.final_max_parallel_cx is not None and r.final_max_parallel_cx>=2
