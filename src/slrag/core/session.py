from typing import Dict, Any, List


class EvidencePool:
    """Session-scoped, chunk-ID-keyed store for retrieved evidence."""
    
    def __init__(self):
        # chunk_id -> dict of chunk data
        self._chunks: Dict[str, Dict[str, Any]] = {}
        
    def add_chunk(self, chunk_id: str, data: Dict[str, Any]) -> None:
        if chunk_id not in self._chunks:
            self._chunks[chunk_id] = data
            
    def get_chunk(self, chunk_id: str) -> Dict[str, Any]:
        return self._chunks.get(chunk_id)
        
    def demote_to_pool(self, chunk_id: str, data: Dict[str, Any]) -> None:
        """Add a chunk from a cancelled speculative branch."""
        data['speculative'] = True
        self.add_chunk(chunk_id, data)


class SessionState:
    """In-process, ephemeral session state."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.evidence_pool = EvidencePool()
        
        # Speculative branches: dict of branch_id -> branch_data
        self.active_speculations: Dict[str, Dict[str, Any]] = {}
        
        # Prefix tracking for the controller
        self.current_prefix: str = ""
        self.last_embedding = None
        self.last_retrieve_time: float = -1000.0  # Allow immediate first retrieval
        
    def clear(self):
        """Destroy session state (HC-4)."""
        self.evidence_pool = EvidencePool()
        self.active_speculations = {}
        self.current_prefix = ""
        self.last_embedding = None
        self.last_retrieve_time = -1000.0
