from typing import Optional, Any
import time
import numpy as np

from slrag.core.schemas import TranscriptChunk, ControllerDecision
from slrag.core.session import ControllerState
from slrag.core.config import get_controller_config
from slrag.controller.suppression import evaluate_suppression
from slrag.controller.content_floor import evaluate_content_floor
from slrag.controller.probe import evaluate_probe
from slrag.controller.stability import evaluate_stability, _get_encoder, cosine_similarity
from slrag.controller.speculation import process_speculation

class RetrievalController:
    """
    Component 1: The Cascading Retrieval Controller.
    
    Processes TranscriptChunks and decides whether to WAIT, RETRIEVE, or NO_RETRIEVAL.
    Implements a strict 5-stage cascade (HC-3).
    """
    
    def __init__(self, session: ControllerState, index_mock: Any = None, encoder_mock: Any = None):
        self.session = session
        self.index_mock = index_mock
        self.encoder_mock = encoder_mock
        
    def process_chunk(self, chunk: TranscriptChunk) -> ControllerDecision:
        """
        Main entry point for the controller.
        Executes the cascade in order.
        """
        # Update prefix
        if self.session.current_prefix:
            self.session.current_prefix += " " + chunk.text
        else:
            self.session.current_prefix = chunk.text
            
        prefix = self.session.current_prefix
        t_s = chunk.t_s
        config = get_controller_config()
        
        # --- Stage -1: Speculation Checking ---
        # Calculate drift for speculation manager
        encoder = _get_encoder(self.encoder_mock)
        current_emb = encoder.encode(chunk.text) # Embed just the new chunk text
        drift = 0.0
        if self.session.last_embedding is not None:
             sim = cosine_similarity(current_emb, self.session.last_embedding)
             drift = 1.0 - sim
             
        process_speculation(chunk.text, drift, self.session)

        # --- Refractory Period Check ---
        current_time_ms = t_s * 1000
        refractory_ms = config.get("refractory_ms", 250.0)
        
        if (current_time_ms - self.session.last_retrieve_time) < refractory_ms:
             return ControllerDecision(
                 t_s=t_s,
                 decision="WAIT",
                 reason="refractory_period",
                 confidence=1.0
             )

        # --- Stage 0: Suppression ---
        decision = evaluate_suppression(prefix, t_s)
        if decision:
            return decision
            
        # --- Stage 1: Content Floor ---
        decision = evaluate_content_floor(prefix, t_s)
        if decision:
            return decision
            
        # --- Stage 2: Probe ---
        decision = evaluate_probe(prefix, t_s, self.index_mock)
        if decision:
            if decision.decision == "RETRIEVE":
                 self.session.last_retrieve_time = current_time_ms
                 self.session.current_prefix = "" # reset on retrieval
            return decision
            
        # --- Stage 3: Stability ---
        decision = evaluate_stability(prefix, t_s, self.session, self.encoder_mock)
        if decision:
             if decision.decision == "RETRIEVE":
                 self.session.last_retrieve_time = current_time_ms
                 self.session.current_prefix = "" # reset on retrieval
             return decision
             
        # --- Stage 4: LLM Tie-break (Stub) ---
        # If we reach here, we've fallen through.
        # Fallback to WAIT if no decision.
        return ControllerDecision(
            t_s=t_s,
            decision="WAIT",
            reason="insufficient_confidence",
            confidence=0.5
        )
