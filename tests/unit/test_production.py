"""Tests for orion.core.production -- logging, health, shutdown, metrics."""

import json

from orion.core.production.health import HealthProbe, HealthStatus
from orion.core.production.logging import StructuredLogger
from orion.core.production.metrics import MetricsCollector

# =========================================================================
# STRUCTURED LOGGING
# =========================================================================


class TestStructuredLogger:
    def test_logger_creation(self):
        logger = StructuredLogger("test")
        assert logger.name == "test"

    def test_log_info(self):
        logger = StructuredLogger("test_info", level="DEBUG")
        output = logger._format("INFO", "test message", key="value")
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "test message"
        assert parsed["key"] == "value"
        assert "timestamp" in parsed

    def test_correlation_id(self):
        logger = StructuredLogger("test_corr", level="DEBUG")
        logger.set_correlation_id("req-123")
        output = logger._format("INFO", "traced message")
        parsed = json.loads(output)
        assert parsed["correlation_id"] == "req-123"

    def test_error_log(self):
        logger = StructuredLogger("test_err", level="DEBUG")
        output = logger._format("ERROR", "something broke", error_code=500)
        parsed = json.loads(output)
        assert parsed["level"] == "ERROR"
        assert parsed["error_code"] == 500


# =========================================================================
# HEALTH PROBE
# =========================================================================


class TestHealthProbe:
    def test_default_healthy(self):
        probe = HealthProbe()
        status = probe.health()
        assert isinstance(status, HealthStatus)

    def test_readiness(self):
        probe = HealthProbe()
        probe.mark_ready()
        assert probe.ready() is True

    def test_liveness(self):
        probe = HealthProbe()
        assert probe.live() is True


# =========================================================================
# METRICS COLLECTOR
# =========================================================================


class TestMetricsCollector:
    def test_track_request(self):
        collector = MetricsCollector()
        with collector.track("test_endpoint"):
            pass  # simulate work
        metrics = collector.get_metrics()
        assert metrics.total_requests >= 1

    def test_track_multiple(self):
        collector = MetricsCollector()
        with collector.track("ep1"):
            pass
        with collector.track("ep2"):
            pass
        try:
            with collector.track("ep3"):
                raise ValueError("fail")
        except ValueError:
            pass
        metrics = collector.get_metrics()
        assert metrics.total_requests == 3
        assert metrics.failed_requests == 1

    def test_prometheus_export(self):
        collector = MetricsCollector()
        with collector.track("test"):
            pass
        export = collector.to_prometheus()
        assert isinstance(export, str)
        assert "total" in export.lower() or "request" in export.lower()
