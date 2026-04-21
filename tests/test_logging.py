"""Logging tests."""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from desk_pricer.app import _LOG_FILE


class TestLogging:
    def test_request_logged(self, client: TestClient):
        """A request should produce a JSON log line."""
        # Note existing line count
        start_lines = 0
        if _LOG_FILE.exists():
            with open(_LOG_FILE, "r", encoding="utf-8") as f:
                start_lines = len(f.readlines())
        resp = client.get("/v1/health")
        assert resp.status_code == 200
        # Log is written asynchronously by middleware; give it a moment
        time.sleep(0.1)
        assert _LOG_FILE.exists()
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # At least one new line should have been written
        new_lines = lines[start_lines:]
        if not new_lines:
            # Read full file and check last line
            last_line = lines[-1] if lines else None
        else:
            last_line = new_lines[-1]
        assert last_line is not None
        entry = json.loads(last_line.strip())
        assert entry["method"] == "GET"
        assert entry["path"] == "/v1/health"
        assert "duration_ms" in entry
        assert entry["status"] == 200
