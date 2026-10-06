import numpy as np
from pathlib import Path
from qecflag.phase5_noise import sample_hardware_contexts
from qecflag.phase7_catalog import ensure_catalog
from qecflag.phase8_timing import (
    build_timed_bridge_plan, simulate_timed_round, timed_single_fault_certificate,
    temporal_majority_syndrome, standard_steane_history_correction,
    repeated_fault_records, build_repeated_history_decoder,
)

ROOT=Path(__file__).resolve().parents[1]

def _fixture():
    e=ensure_catalog(ROOT).entries[0]; c=sample_hardware_contexts(1,8401,'hw_id').context(0)
    return e,c

def test_timed_plan_has_more_duration_than_cx_only():
    e,c=_fixture(); p=build_timed_bridge_plan(e['labels'],e['hubs'],c)
    assert p.duration_ns > p.native.duration_ns
    assert len(p.events) == p.native.native_cx + 12
    assert all(x>0 for x in p.data_idle_ns)

def test_timed_ideal_map_preserves_no_error():
    e,c=_fixture(); p=build_timed_bridge_plan(e['labels'],e['hubs'],c)
    d,o=simulate_timed_round(p)
    assert d==0 and o==0

def test_phase7_seed_survives_timed_single_fault_model():
    e,c=_fixture(); cert=timed_single_fault_certificate(e['labels'],e['hubs'],c)
    assert cert.passed
    assert cert.c1==0
    assert cert.single_fault_failures==0

def test_majority_history():
    h = 5 | (2<<6) | (5<<12)
    assert temporal_majority_syndrome(h,3)==5
    assert isinstance(standard_steane_history_correction(h,3),int)

def test_history_decoder_corrects_all_single_faults_for_certified_seed():
    e,c=_fixture(); p=build_timed_bridge_plan(e['labels'],e['hubs'],c)
    rec=repeated_fault_records(p,c,3)
    dec=build_repeated_history_decoder(p,c,3,rec)
    assert dec.single_fault_conflicts==0
    assert dec.single_fault_failures==0
    assert dec.incoming_failures==0
