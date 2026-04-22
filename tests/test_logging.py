"""Logging tests."""

from fastapi.testclient import TestClient


class TestLogging:
    def test_request_logged(self, client: TestClient, caplog):
        """A request should produce a structured JSON log record."""
        with caplog.at_level("INFO", logger="deskpricer"):
            resp = client.get("/v1/health")
            assert resp.status_code == 200

        # Find log records with request path info
        request_records = [r for r in caplog.records if getattr(r, "path", None) == "/v1/health"]
        assert len(request_records) >= 1
        record = request_records[-1]
        assert record.method == "GET"
        assert record.status == 200
        assert hasattr(record, "duration_ms")
        assert record.duration_ms >= 0

    def test_log_file_path_is_configurable(self, monkeypatch):
        """DESKPRICER_LOG_DIR env var should override the default path."""
        custom_dir = "/tmp/test_deskpricer_logs"
        monkeypatch.setenv("DESKPRICER_LOG_DIR", custom_dir)
        # Re-import to pick up the new env var
        from pathlib import Path

        from deskpricer.logging_config import _default_log_dir

        assert _default_log_dir() == Path(custom_dir)

    def test_safe_rotating_file_handler_swallows_rollover_failure(self, tmp_path, monkeypatch):
        """_SafeRotatingFileHandler must survive an OSError during rollover (e.g. Windows lock)."""
        import logging
        import logging.handlers
        from deskpricer.logging_config import _SafeRotatingFileHandler

        log_file = tmp_path / "test.log"
        handler = _SafeRotatingFileHandler(log_file, maxBytes=1, backupCount=1, encoding="utf-8")

        monkeypatch.setattr(
            logging.handlers.RotatingFileHandler, "shouldRollover", lambda self, record: True
        )

        def _failing_rollover(self):
            raise OSError("simulated Windows file lock")

        monkeypatch.setattr(logging.handlers.RotatingFileHandler, "doRollover", _failing_rollover)

        record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", (), None)
        handler.emit(record)  # must not raise
        handler.close()

        assert log_file.exists()
