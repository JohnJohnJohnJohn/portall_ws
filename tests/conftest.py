"""Pytest fixtures."""

import pytest
from fastapi.testclient import TestClient

from desk_pricer.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
