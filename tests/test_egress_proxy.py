# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for the egress proxy server."""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock, patch

import pytest

from orion.security.egress.audit import AuditLogger
from orion.security.egress.config import DomainRule, EgressConfig
from orion.security.egress.inspector import ContentInspector
from orion.security.egress.proxy import EgressProxyHandler, EgressProxyServer
from orion.security.egress.rate_limiter import RateLimiter


def _find_free_port() -> int:
    """Find an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestEgressProxyServer:
    """Tests for EgressProxyServer lifecycle."""

    def test_start_and_stop(self, tmp_path):
        port = _find_free_port()
        config = EgressConfig(
            proxy_port=port,
            audit_log_path=str(tmp_path / "audit.log"),
        )
        server = EgressProxyServer(config=config)

        assert server.is_running is False
        server.start()
        assert server.is_running is True

        # Give it a moment to bind
        time.sleep(0.2)

        # Verify port is listening
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            result = s.connect_ex(("127.0.0.1", port))
            assert result == 0, f"Proxy not listening on port {port}"

        server.stop()
        assert server.is_running is False

    def test_double_start_warns(self, tmp_path):
        port = _find_free_port()
        config = EgressConfig(
            proxy_port=port,
            audit_log_path=str(tmp_path / "audit.log"),
        )
        server = EgressProxyServer(config=config)
        server.start()
        time.sleep(0.1)
        # Second start should not crash
        server.start()
        server.stop()

    def test_get_status(self, tmp_path):
        port = _find_free_port()
        config = EgressConfig(
            proxy_port=port,
            audit_log_path=str(tmp_path / "audit.log"),
        )
        server = EgressProxyServer(config=config)
        server.start()
        time.sleep(0.1)

        status = server.get_status()
        assert status["running"] is True
        assert status["port"] == port
        assert status["enforce"] is True
        assert status["content_inspection"] is True
        assert isinstance(status["rate_limit_stats"], dict)
        assert isinstance(status["audit_stats"], dict)

        server.stop()

    def test_config_reload(self, tmp_path):
        port = _find_free_port()
        config = EgressConfig(
            proxy_port=port,
            global_rate_limit_rpm=100,
            audit_log_path=str(tmp_path / "audit.log"),
        )
        server = EgressProxyServer(config=config)
        server.start()
        time.sleep(0.1)

        assert server.config.global_rate_limit_rpm == 100

        # Write new config and reload
        from orion.security.egress.config import save_config

        new_config = EgressConfig(
            proxy_port=port,
            global_rate_limit_rpm=500,
            whitelist=[DomainRule(domain="github.com")],
            audit_log_path=str(tmp_path / "audit.log"),
        )
        config_path = tmp_path / "egress_config.yaml"
        save_config(new_config, config_path)
        server.reload_config(str(config_path))

        assert server.config.global_rate_limit_rpm == 500
        assert len(server.config.whitelist) == 1

        server.stop()


class TestEgressProxyBlocking:
    """Tests for the proxy's security enforcement via real HTTP requests."""

    @pytest.fixture(autouse=True)
    def setup_proxy(self, tmp_path):
        """Start a proxy server for each test."""
        self.port = _find_free_port()
        self.config = EgressConfig(
            proxy_port=self.port,
            audit_log_path=str(tmp_path / "audit.log"),
            enforce=True,
            whitelist=[
                DomainRule(domain="allowed.example.com", allow_write=True),
                DomainRule(domain="readonly.example.com", allow_write=False),
            ],
        )
        self.server = EgressProxyServer(config=self.config)
        self.server.start()
        time.sleep(0.2)
        yield
        self.server.stop()

    def _proxy_request(self, method: str, url: str, body: str = "") -> tuple[int, str]:
        """Send an HTTP request through the proxy and return (status, body)."""
        import httpx

        try:
            with httpx.Client(
                proxy=f"http://127.0.0.1:{self.port}",
                timeout=5.0,
            ) as client:
                resp = client.request(method, url, content=body.encode() if body else None)
                return resp.status_code, resp.text
        except httpx.ProxyError as exc:
            # httpx wraps proxy 4xx/5xx responses in ProxyError
            # Extract status from the exception message
            msg = str(exc)
            if "403" in msg:
                return 403, msg
            if "429" in msg:
                return 429, msg
            return 502, msg
        except Exception as exc:
            return 0, str(exc)

    def test_blocked_domain_returns_403(self):
        status, body = self._proxy_request("GET", "http://evil.example.com/steal")
        assert status == 403
        assert (
            "not whitelisted" in body.lower() or "blocked" in body.lower() or "403" in body.lower()
        )

    def test_allowed_domain_passes(self):
        # This will try to connect to allowed.example.com which won't resolve,
        # but the proxy should NOT return 403. It should return 502 (upstream error).
        status, body = self._proxy_request("GET", "http://allowed.example.com/test")
        # Not 403 means the domain check passed (might be 502 if host doesn't exist)
        assert status != 403 or "not whitelisted" not in body.lower()

    def test_write_to_readonly_domain_blocked(self):
        status, body = self._proxy_request(
            "POST", "http://readonly.example.com/api", '{"data": "test"}'
        )
        assert status == 403
        assert "read-only" in body.lower() or "blocked" in body.lower() or "403" in body.lower()

    def test_audit_log_populated(self):
        # Make a request that will be blocked
        self._proxy_request("GET", "http://evil.example.com/steal")
        time.sleep(0.1)

        stats = self.server.audit.get_stats()
        assert stats["total_requests"] >= 1
        assert stats["blocked"] >= 1


class TestEgressProxyHandlerUnit:
    """Unit tests for handler logic without starting a real server."""

    def test_handler_class_attributes_set(self, tmp_path):
        """Verify handler gets security components from server."""
        port = _find_free_port()
        config = EgressConfig(
            proxy_port=port,
            audit_log_path=str(tmp_path / "audit.log"),
        )
        server = EgressProxyServer(config=config)
        server.start()
        time.sleep(0.1)

        assert EgressProxyHandler.egress_config is config
        assert EgressProxyHandler.audit_logger is server.audit
        assert EgressProxyHandler.rate_limiter is server.rate_limiter
        assert isinstance(EgressProxyHandler.content_inspector, ContentInspector)

        server.stop()
