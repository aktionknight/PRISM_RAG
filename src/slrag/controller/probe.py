import numpy as np
from typing import Optional, Any

from slrag.core.schemas import ControllerDecision
from slrag.core.config import get_controller_config


def evaluate_probe(prefix: str, t_s: float, index_mock: Any = None) -> Optional[ControllerDecision]:
    """
    Stage 2 — Corpus Discriminativeness Probe.
    
    Queries BM25 index. If results are peaked (discriminative) -> RETRIEVE.
    If results are flat (ambiguous) -> WAIT.
    If in between, pass to Stage 3.
    """
    if not prefix.strip():
         return ControllerDecision(
            t_s=t_s,
            decision="WAIT",
            reason="corpus_ambiguous",
            confidence=0.9
        )
        
    config = get_controller_config()
    tau_hi = config.get("tau_hi", 0.35)
    tau_lo = config.get("tau_lo", 0.10)
    h_lo_thresh = config.get("h_lo", 0.65)
    top_k = config.get("top_k_probe", 10)
    margin_n = config.get("margin_top_n", 5)
    
    # In a real system, we'd query the actual bm25s index here.
    # For this stub/test, we rely on the injected mock.
    if index_mock is None:
        return None # Pass to stage 3 if no index available
        
    scores = index_mock.query(prefix, k=top_k)
    
    if len(scores) == 0 or scores[0] == 0:
        # No matches at all -> flat
        return ControllerDecision(
            t_s=t_s,
            decision="WAIT",
            reason="corpus_ambiguous",
            confidence=0.8
        )
        
    # Calculate margin: (s1 - mean(s2..s5)) / s1
    s1 = scores[0]
    s_rest = scores[1:margin_n] if len(scores) > 1 else []
    mean_rest = np.mean(s_rest) if len(s_rest) > 0 else 0
    margin = (s1 - mean_rest) / s1 if s1 > 0 else 0
    
    # Calculate normalised entropy of top-10
    # H = -sum(p * log(p)) / log(k)
    # p_i = s_i / sum(scores)
    total_score = np.sum(scores)
    if total_score > 0:
        p = scores / total_score
        # filter zeros
        p = p[p > 0]
        h_raw = -np.sum(p * np.log(p))
        h_norm = h_raw / np.log(len(scores)) if len(scores) > 1 else 0.0
    else:
        h_norm = 1.0 # Max entropy if all zero
        
    if margin > tau_hi and h_norm < h_lo_thresh:
        return ControllerDecision(
            t_s=t_s,
            decision="RETRIEVE",
            reason="corpus_discriminative",
            confidence=min(0.7 + margin, 1.0)
        )
    elif margin < tau_lo:
        return ControllerDecision(
            t_s=t_s,
            decision="WAIT",
            reason="corpus_ambiguous",
            confidence=0.6
        )
        
    # Fall through to Stage 3
    return None
