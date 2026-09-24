import pytest
import numpy as np
from slrag.core.session import SessionState

@pytest.fixture
def session():
    return SessionState(session_id="test-session")

class MockBM25Index:
    def __init__(self, discriminative=True):
        self.discriminative = discriminative
        
    def query(self, text, k=10):
        if not self.discriminative:
            # Flat scores (ambiguous)
            return np.array([0.1] * k)
            
        if "apple" in text.lower():
            # Peaked scores (discriminative)
            scores = np.zeros(k)
            scores[0] = 1.5
            scores[1] = 0.2
            return scores
            
        return np.zeros(k)

@pytest.fixture
def mock_index_discriminative():
    return MockBM25Index(discriminative=True)
    
@pytest.fixture
def mock_index_ambiguous():
    return MockBM25Index(discriminative=False)

class MockEncoder:
    def __init__(self, static=False):
        self.static = static
        
    def encode(self, text):
        if self.static:
            return np.ones(384) / np.sqrt(384) # normalized ones vector
        # Returns a stable vector for the same text
        np.random.seed(hash(text) % (2**32))
        v = np.random.rand(384)
        return v / np.linalg.norm(v)

@pytest.fixture
def mock_encoder():
    return MockEncoder()
    
@pytest.fixture
def mock_encoder_static():
    return MockEncoder(static=True)
