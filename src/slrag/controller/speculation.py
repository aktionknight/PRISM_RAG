from typing import Dict, Any, Optional

from slrag.core.config import get_controller_config
from slrag.core.session import ControllerState

def detect_contradiction(new_chunk_text: str, current_drift: float) -> bool:
    """
    Check if the new chunk contradicts the speculative branch.
    Returns True if a self-correction marker is found or drift is too high.
    """
    config = get_controller_config()
    markers = config.get("self_correction_markers", [])
    max_drift = config.get("speculation_drift_delta", 0.30)
    
    text_lower = new_chunk_text.lower()
    
    if current_drift > max_drift:
        return True
        
    for marker in markers:
        if marker in text_lower:
            return True
            
    return False

def process_speculation(chunk_text: str, current_drift: float, session: ControllerState) -> None:
    """
    Manage the lifecycle of speculative branches.
    If contradiction detected -> CANCEL and demote to pool.
    If consistent -> CONFIRM (leave active).
    """
    # Create a list of keys to safely iterate and delete
    active_branches = list(session.active_speculations.keys())
    
    for branch_id in active_branches:
        branch = session.active_speculations[branch_id]
        
        if detect_contradiction(chunk_text, current_drift):
            # CANCEL
            # Demote retrieved chunks to EvidencePool
            for chunk_data in branch.get("retrieved_chunks", []):
                if hasattr(session, 'session') and session.session is not None:
                    from slrag.core.schemas import EvidencePoolEntry
                    entry = EvidencePoolEntry(**chunk_data)
                    entry.speculative = True
                    session.session.add_evidence(entry)
                else:
                    session.evidence_pool.demote_to_pool(
                        chunk_data["chunk_id"], 
                        chunk_data
                    )
            # Remove branch
            del session.active_speculations[branch_id]
        else:
            # CONFIRM - promote to confirmed state
            branch["status"] = "confirmed"
