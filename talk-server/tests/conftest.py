"""Pytest fixtures for talk-server tests."""
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(main.app)
