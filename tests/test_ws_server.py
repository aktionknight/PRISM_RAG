"""
tests/test_ws_server.py — Unit tests for ws_server FastAPI endpoint.

Component 5 & Demo Surface (Matangi).
"""

import pytest

from slrag.api import ws_server


def test_ws_server_import_or_app():
    if ws_server.FASTAPI_AVAILABLE:
        app = ws_server.create_app()
        assert app is not None
    else:
        with pytest.raises(ImportError) as exc_info:
            ws_server.create_app()
        assert "fastapi" in str(exc_info.value).lower()
