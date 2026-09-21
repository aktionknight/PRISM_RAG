from slrag.controller.speculation import process_speculation

def test_speculation_contradiction(session):
    # Setup active branch
    session.active_speculations["branch_1"] = {
        "status": "pending",
        "retrieved_chunks": [{"chunk_id": "c1", "data": "test"}]
    }
    
    # "no wait" is a self-correction marker
    process_speculation("no wait", 0.1, session)
    
    # Branch should be deleted
    assert "branch_1" not in session.active_speculations
    # Chunk should be demoted to pool
    assert session.evidence_pool.get_chunk("c1")["speculative"] is True

def test_speculation_high_drift(session):
    session.active_speculations["branch_1"] = {"status": "pending"}
    
    # Drift 0.5 > 0.30 max
    process_speculation("hello", 0.5, session)
    
    assert "branch_1" not in session.active_speculations

def test_speculation_confirm(session):
    session.active_speculations["branch_1"] = {"status": "pending"}
    
    # Low drift, no markers
    process_speculation("and", 0.1, session)
    
    assert "branch_1" in session.active_speculations
    assert session.active_speculations["branch_1"]["status"] == "confirmed"
