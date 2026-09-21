import re
from typing import Optional

from slrag.core.schemas import ControllerDecision
from slrag.core.config import get_controller_config


def evaluate_suppression(prefix: str, t_s: float) -> Optional[ControllerDecision]:
    """
    Stage 0 — Suppression Gate.
    
    Detects presentation verbs or anaphora that indicate a restructuring
    of the previous answer rather than a new query.
    
    Returns:
        ControllerDecision(NO_RETRIEVAL) if suppressed, otherwise None (pass to next stage).
    """
    config = get_controller_config()
    prefix_lower = prefix.lower()
    
    # 1. Check for presentation verbs
    has_presentation = any(
        re.search(r'\b' + re.escape(verb) + r'\b', prefix_lower) 
        for verb in config.get("presentation_verbs", [])
    )
    
    # 2. Check for anaphora to prior answer
    has_anaphora = any(
        re.search(r'\b' + re.escape(pattern) + r'\b', prefix_lower) 
        for pattern in config.get("anaphora_patterns", [])
    )
    
    # Simple rule: if we have presentation verbs or anaphora, we suppress.
    # In a real system, we'd also run NER to ensure ZERO new content entities,
    # but we'll do a simple regex check here for the stub.
    
    if has_presentation or has_anaphora:
        return ControllerDecision(
            t_s=t_s,
            decision="NO_RETRIEVAL",
            reason="presentation_restructure",
            confidence=0.9
        )
        
    return None
