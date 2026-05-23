"""Pytest fixtures."""

import os

# Run pricing in-process during tests so logging hooks and monkeypatches work.
os.environ.setdefault("DESKPRICER_INLINE", "1")

import pytest
from fastapi.testclient import TestClient

from deskpricer.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
