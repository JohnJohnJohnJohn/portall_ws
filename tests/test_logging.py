"""Logging tests."""

from fastapi.testclient import TestClient


class TestLogging:
    def test_request_logged(self, client: TestClient, caplog):
        """A request should produce a structured JSON log record."""
        with caplog.at_level("INFO", logger="desk_pricer"):
            resp = client.get("/v1/health")
            assert resp.status_code == 200

        # Find log records with request path info
        request_records = [
            r for r in caplog.records
            if getattr(r, "path", None) == "/v1/health"
        ]
        assert len(request_records) >= 1
        record = request_records[-1]
        assert record.method == "GET"
        assert record.status == 200
        assert hasattr(record, "duration_ms")
        assert record.duration_ms >= 0

    def test_log_file_path_is_configurable(self, monkeypatch):
        """DESK_PRICER_LOG_DIR env var should override the default path."""
        custom_dir = "/tmp/test_deskpricer_logs"
        monkeypatch.setenv("DESK_PRICER_LOG_DIR", custom_dir)
        # Re-import to pick up the new env var
        from pathlib import Path

        from desk_pricer.logging_config import _default_log_dir
        assert _default_log_dir() == Path(custom_dir)
