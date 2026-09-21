import numpy as np
from typing import Optional, Any

from slrag.core.schemas import ControllerDecision
from slrag.core.config import get_controller_config
from slrag.core.session import SessionState
from slrag.controller.content_floor import count_content_anchors

# Lazy load embedding model
_encoder = None

def _get_encoder(encoder_mock: Any = None):
    if encoder_mock is not None:
        return encoder_mock
        
    global _encoder
    if _encoder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _encoder = SentenceTransformer("BAAI/bge-small-en-v1.5")
        except ImportError:
            # Fallback for tests
            class MockEncoder:
                def encode(self, text):
                    return np.random.rand(384)
            _encoder = MockEncoder()
    return _encoder

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def evaluate_stability(prefix: str, t_s: float, session: SessionState, encoder_mock: Any = None) -> Optional[ControllerDecision]:
    """
    Stage 3 — Embedding Stability.
    
    Computes cosine drift between consecutive prefix embeddings.
    drift < ε AND content_anchors >= 2 -> RETRIEVE.
    """
    config = get_controller_config()
    epsilon = config.get("epsilon", 0.15)
    min_anchors = config.get("content_anchor_min", 2)
    
    encoder = _get_encoder(encoder_mock)
    
    # Embed current prefix
    # Real implementation would use properly batched async encoding, but for the 
    # hackathon we'll use synchronous encoding on the single string.
    current_emb = encoder.encode(prefix)
    
    # Compare with last embedding in session
    if session.last_embedding is not None:
        sim = cosine_similarity(current_emb, session.last_embedding)
        drift = 1.0 - sim
        
        anchors = count_content_anchors(prefix)
        
        if drift < epsilon and anchors >= min_anchors:
            # Update session state before returning
            session.last_embedding = current_emb
            return ControllerDecision(
                t_s=t_s,
                decision="RETRIEVE",
                reason="intent_stabilised",
                confidence=0.8
            )
            
    # Always update the session with the latest embedding
    session.last_embedding = current_emb
    
    # Fall through to Stage 4 (or NO_DECISION)
    return None
