"""Pytest fixtures."""

import pytest
from fastapi.testclient import TestClient

from deskpricer.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
