import spacy
from typing import Optional

from slrag.core.schemas import ControllerDecision
from slrag.core.config import get_controller_config

# Lazy load spaCy model
_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            # Fallback for tests if model not installed
            _nlp = spacy.blank("en")
    return _nlp


def evaluate_content_floor(prefix: str, t_s: float) -> Optional[ControllerDecision]:
    """
    Stage 1 — Content Floor.
    
    Returns WAIT if < 1 content anchor OR dangling preposition.
    Otherwise returns None (pass to next stage).
    """
    nlp = _get_nlp()
    doc = nlp(prefix)
    
    # 1. Check for dangling prepositions/determiners at the very end
    is_dangling = False
    if len(doc) > 0:
        if not doc.has_annotation("ENT_IOB"):
            # Fallback
            words = prefix.split()
            if words and words[-1].lower() in ["at", "to", "in", "for", "with", "on", "the", "a", "an"]:
                is_dangling = True
        elif doc[-1].pos_ in ["ADP", "DET"]:
            is_dangling = True
            
    if is_dangling:
        return ControllerDecision(
            t_s=t_s,
            decision="WAIT",
            reason="intent_unstable",
            confidence=0.8,
            stage=1,
            stage_name="Stage 1: Content Floor",
            margin=0.0,
            threshold=1.0,
        )
        
    # 2. Count content anchors (GPE, ORG, PRODUCT, CARDINAL, NOUN)
    content_anchors = 0
    if not doc.has_annotation("ENT_IOB"):
        # Fallback for tests if blank model is used
        words = prefix.split()
        content_anchors = sum(1 for w in words if len(w) > 4 or (len(w) > 3 and w[0].isupper()))
    else:
        for ent in doc.ents:
            if ent.label_ in ["GPE", "ORG", "PRODUCT", "CARDINAL"]:
                content_anchors += 1
                
        for token in doc:
            if token.pos_ == "NOUN" and not token.ent_type_:
                content_anchors += 1
            
    # Need at least 1 content anchor to proceed
    if content_anchors < 1:
        return ControllerDecision(
            t_s=t_s,
            decision="WAIT",
            reason="intent_unstable",
            confidence=0.9,
            stage=1,
            stage_name="Stage 1: Content Floor",
            margin=float(content_anchors),
            threshold=1.0,
        )
        
    return None


def evaluate_sentence_boundary(prefix: str, t_s: float) -> Optional[ControllerDecision]:
    """
    Boundary Rule: A completed sentence with at least one content anchor
    triggers RETRIEVE regardless of the probe. Also triggers on clause-level conjunctions.
    """
    clean_prefix = prefix.strip()
    if not clean_prefix:
        return None

    nlp = _get_nlp()
    doc = nlp(clean_prefix)
    
    split_indices = []
    for token in doc:
        if token.pos_ == "PUNCT" and token.text in {".", "?", "!"}:
            split_indices.append(token.i + 1)
        elif token.lemma_.lower() in {"and", "but", "or", "also", "plus"} and token.dep_ == "cc" and token.head.pos_ in {"VERB", "AUX"}:
            split_indices.append(token.i)
            
    if not split_indices:
        return None

    for idx in split_indices:
        sentence_text = doc[:idx].text.strip()
        anchors = count_content_anchors(sentence_text)
        if anchors >= 1:
            return ControllerDecision(
                t_s=t_s,
                decision="RETRIEVE",
                reason="sentence_boundary",
                confidence=0.95,
                stage=1,
                stage_name="Stage 1: Sentence Boundary",
                margin=float(anchors),
                threshold=1.0,
            )

    return None

def count_content_anchors(prefix: str) -> int:
    """Helper for Stage 3 to count anchors."""
    nlp = _get_nlp()
    doc = nlp(prefix)
    
    content_anchors = 0
    if not doc.has_annotation("ENT_IOB"):
        words = prefix.split()
        content_anchors = sum(1 for w in words if len(w) > 4 or (len(w) > 3 and w[0].isupper()))
    else:
        for ent in doc.ents:
            if ent.label_ in ["GPE", "ORG", "PRODUCT", "CARDINAL"]:
                content_anchors += 1
                
        for token in doc:
            if token.pos_ == "NOUN" and not token.ent_type_:
                content_anchors += 1
            
    return content_anchors
