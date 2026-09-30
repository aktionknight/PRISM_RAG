import re
from typing import Optional

from slrag.core.schemas import ControllerDecision
from slrag.core.config import get_controller_config
from slrag.controller.content_floor import count_content_anchors, _get_nlp


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
    
    is_question = '?' in prefix_lower
    
    # Simple rule: if we have presentation verbs or anaphora, we suppress,
    # BUT only if there are NO new content anchors in the prefix.
    
    anchor_text = prefix
    if has_presentation:
        # Formatting instructions are not new corpus content. Use the existing
        # presentation controls, and spaCy's generic numeric recognition for an
        # immediately preceding format count (e.g. "two bullets"). Leave other
        # nouns and numbers intact so substantive requests still retrieve.
        doc = _get_nlp()(prefix)
        spans = []
        for phrase in config.get("presentation_verbs", []):
            for match in re.finditer(r'\b' + re.escape(phrase) + r'\b', prefix, re.IGNORECASE):
                start = match.start()
                previous = next((token for token in reversed(doc) if token.idx < start), None)
                if previous is not None and previous.like_num and not prefix[previous.idx + len(previous.text):start].strip():
                    start = previous.idx
                spans.append((start, match.end()))
        for start, end in sorted(spans, reverse=True):
            anchor_text = anchor_text[:start] + " " * (end - start) + anchor_text[end:]
    anchors = count_content_anchors(anchor_text)
    
    if (has_presentation or (has_anaphora and not is_question)) and anchors == 0:
        return ControllerDecision(
            t_s=t_s,
            decision="NO_RETRIEVAL",
            reason="presentation_restructure",
            confidence=0.9,
            stage=0,
            stage_name="Stage 0: Suppression",
            threshold=0.0,
        )
        
    return None
