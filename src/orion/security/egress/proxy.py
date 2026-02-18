# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
#    You may use, modify, and distribute this file under AGPL-3.0.
#    See LICENSE for the full text.
#
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#    For proprietary use, SaaS deployment, or enterprise licensing.
#    See LICENSE-ENTERPRISE.md or contact info@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""Egress proxy server -- The Narrow Door.

An HTTP forward proxy that runs on the HOST side and filters all
outbound traffic from Orion's Docker sandbox. The container is
configured to route HTTP/HTTPS traffic through this proxy.

Architecture:
  Docker Container (Orion) --HTTP_PROXY--> EgressProxy (Host) --> Internet

The proxy enforces:
  1. Domain whitelist (additive model, default: LLM endpoints only)
  2. Protocol filtering (HTTPS only by default)
  3. Method filtering (GET-only for research domains)
  4. Content inspection (credential leakage detection)
  5. Rate limiting (per-domain and global)
  6. Full audit logging (JSON Lines, host-side)

For HTTPS traffic, the proxy uses the HTTP CONNECT method.
It does NOT perform TLS interception (no MITM). Instead:
  - Domain filtering is based on the CONNECT hostname
  - Content inspection applies to HTTP (non-TLS) requests only
  - For HTTPS, the proxy tunnels the connection after domain check
"""

from __future__ import annotations

import http.server
import logging
import select
import socket
import socketserver
import threading
import time
from typing import Any
from urllib.parse import urlparse

from .audit import AuditEntry, AuditLogger
from .config import EgressConfig, load_config
from .inspector import ContentInspector
from .rate_limiter import RateLimiter

logger = logging.getLogger("orion.security.egress.proxy")

# HTTP methods classified by read/write semantics
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Buffer size for tunnel relay
_TUNNEL_BUFSIZE = 65536

# Timeout for upstream connections (seconds)
_UPSTREAM_TIMEOUT = 30


class EgressProxyHandler(http.server.BaseHTTPRequestHandler):
    """HTTP proxy request handler with security enforcement.

    Handles both regular HTTP requests (GET/POST) and HTTPS tunneling
    via the CONNECT method.
    """

    # These are set by the EgressProxyServer on the class before serving
    egress_config: EgressConfig
    audit_logger: AuditLogger
    content_inspector: ContentInspector
    rate_limiter: RateLimiter

    # ---------------------------------------------------------------
    # CONNECT method -- HTTPS tunneling
    # ---------------------------------------------------------------
    def do_CONNECT(self) -> None:
        """Handle HTTPS CONNECT tunneling.

        The client sends: CONNECT hostname:port HTTP/1.1
        We check the domain whitelist and either tunnel or reject.
        No TLS interception -- we cannot inspect HTTPS payloads.
        """
        hostname, port = self._parse_connect_target()
        if not hostname:
            self._send_error(400, "Bad CONNECT target")
            return

        client_ip = self.client_address[0] if self.client_address else ""

        # --- Security gate ---
        rule = self.egress_config.is_domain_allowed(hostname)
        if rule is None:
            if self.egress_config.enforce:
                self.audit_logger.log(
                    AuditEntry.blocked(
                        "CONNECT",
                        f"{hostname}:{port}",
                        hostname,
                        "Domain not whitelisted",
                        client_ip,
                    )
                )
                self._send_error(403, f"Blocked: {hostname} is not whitelisted")
                return
            else:
                logger.warning("AUDIT-ONLY: CONNECT to non-whitelisted %s:%d", hostname, port)

        # --- Protocol check ---
        if rule and not self.egress_config.is_protocol_allowed(hostname, "https"):
            self.audit_logger.log(
                AuditEntry.blocked(
                    "CONNECT",
                    f"{hostname}:{port}",
                    hostname,
                    "HTTPS not allowed for domain",
                    client_ip,
                )
            )
            self._send_error(403, f"Blocked: HTTPS not allowed for {hostname}")
            return

        # --- Rate limit check ---
        rate_limit = rule.rate_limit_rpm if rule else 60
        rl_result = self.rate_limiter.check(hostname, rate_limit)
        if not rl_result.allowed:
            self.audit_logger.log(
                AuditEntry.rate_limited("CONNECT", f"{hostname}:{port}", hostname, client_ip)
            )
            self._send_error(429, f"Rate limited: {rl_result.reason}")
            return

        # --- Establish tunnel ---
        try:
            upstream = socket.create_connection((hostname, port), timeout=_UPSTREAM_TIMEOUT)
        except (TimeoutError, OSError) as exc:
            logger.error("Failed to connect to %s:%d -- %s", hostname, port, exc)
            self._send_error(502, f"Cannot reach {hostname}:{port}")
            return

        # Tell client the tunnel is established
        self.send_response(200, "Connection Established")
        self.end_headers()

        # Log the successful tunnel
        self.audit_logger.log(
            AuditEntry.allowed(
                "CONNECT",
                f"{hostname}:{port}",
                hostname,
                rule.domain if rule else "AUDIT-ONLY",
                status_code=200,
                client_ip=client_ip,
            )
        )

        # Relay data between client and upstream
        self._tunnel(self.connection, upstream)
        upstream.close()

    # ---------------------------------------------------------------
    # Regular HTTP methods (GET, POST, PUT, DELETE, etc.)
    # ---------------------------------------------------------------
    def do_GET(self) -> None:
        self._handle_http_request("GET")

    def do_POST(self) -> None:
        self._handle_http_request("POST")

    def do_PUT(self) -> None:
        self._handle_http_request("PUT")

    def do_DELETE(self) -> None:
        self._handle_http_request("DELETE")

    def do_PATCH(self) -> None:
        self._handle_http_request("PATCH")

    def do_HEAD(self) -> None:
        self._handle_http_request("HEAD")

    def do_OPTIONS(self) -> None:
        self._handle_http_request("OPTIONS")

    def _handle_http_request(self, method: str) -> None:
        """Process an HTTP request through the security pipeline."""
        parsed = urlparse(self.path)
        hostname = parsed.hostname or ""
        client_ip = self.client_address[0] if self.client_address else ""
        url = self.path

        # --- 1. Domain whitelist check ---
        rule = self.egress_config.is_domain_allowed(hostname)
        if rule is None:
            if self.egress_config.enforce:
                self.audit_logger.log(
                    AuditEntry.blocked(method, url, hostname, "Domain not whitelisted", client_ip)
                )
                self._send_error(403, f"Blocked: {hostname} is not whitelisted")
                return
            else:
                logger.warning("AUDIT-ONLY: %s to non-whitelisted %s", method, hostname)

        # --- 2. Protocol check ---
        protocol = parsed.scheme or "http"
        if rule and not self.egress_config.is_protocol_allowed(hostname, protocol):
            self.audit_logger.log(
                AuditEntry.blocked(
                    method, url, hostname, f"Protocol {protocol} not allowed", client_ip
                )
            )
            self._send_error(403, f"Blocked: {protocol} not allowed for {hostname}")
            return

        # --- 3. Write method check (GET-only domains) ---
        if method.upper() in _WRITE_METHODS:
            if rule and not rule.allow_write:
                self.audit_logger.log(
                    AuditEntry.blocked(
                        method,
                        url,
                        hostname,
                        "Write operations not allowed (read-only domain)",
                        client_ip,
                    )
                )
                self._send_error(403, f"Blocked: {hostname} is read-only (GET only)")
                return

        # --- 4. Rate limit check ---
        rate_limit = rule.rate_limit_rpm if rule else 60
        rl_result = self.rate_limiter.check(hostname, rate_limit)
        if not rl_result.allowed:
            self.audit_logger.log(AuditEntry.rate_limited(method, url, hostname, client_ip))
            self._send_error(429, f"Rate limited: {rl_result.reason}")
            return

        # --- 5. Content inspection (for request body) ---
        body = b""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            body = self.rfile.read(content_length)

        if body and self.egress_config.content_inspection:
            inspection = self.content_inspector.inspect(body, hostname, method)
            if inspection.blocked:
                self.audit_logger.log(
                    AuditEntry.credential_leak(
                        method, url, hostname, inspection.patterns_found, client_ip
                    )
                )
                self._send_error(
                    403,
                    f"Blocked: credential pattern detected in outbound payload ({', '.join(inspection.patterns_found)})",
                )
                return

        # --- 6. Forward the request ---
        start_time = time.time()
        try:
            import httpx

            # Build headers (forward most, strip hop-by-hop)
            fwd_headers = {}
            for key, value in self.headers.items():
                key_lower = key.lower()
                if key_lower in (
                    "proxy-authorization",
                    "proxy-connection",
                    "connection",
                    "keep-alive",
                    "host",
                ):
                    continue
                fwd_headers[key] = value

            with httpx.Client(timeout=_UPSTREAM_TIMEOUT, follow_redirects=True) as client:
                resp = client.request(
                    method=method,
                    url=url,
                    headers=fwd_headers,
                    content=body if body else None,
                )

            duration_ms = (time.time() - start_time) * 1000

            # Send response back to client
            self.send_response(resp.status_code)
            for key, value in resp.headers.items():
                key_lower = key.lower()
                if key_lower in ("transfer-encoding", "connection", "keep-alive"):
                    continue
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(resp.content)

            # Audit log the successful request
            self.audit_logger.log(
                AuditEntry.allowed(
                    method,
                    url,
                    hostname,
                    rule.domain if rule else "AUDIT-ONLY",
                    status_code=resp.status_code,
                    duration_ms=duration_ms,
                    request_size=len(body),
                    response_size=len(resp.content),
                    client_ip=client_ip,
                )
            )

        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error("Upstream request failed: %s %s -- %s", method, url, exc)
            self._send_error(502, f"Upstream error: {exc}")

    # ---------------------------------------------------------------
    # Helper methods
    # ---------------------------------------------------------------
    def _parse_connect_target(self) -> tuple[str, int]:
        """Parse hostname:port from a CONNECT request."""
        try:
            if ":" in self.path:
                host, port_str = self.path.rsplit(":", 1)
                return host, int(port_str)
            return self.path, 443
        except (ValueError, AttributeError):
            return "", 0

    def _tunnel(self, client_conn: socket.socket, upstream_conn: socket.socket) -> None:
        """Relay data between client and upstream (for CONNECT tunneling)."""
        conns = [client_conn, upstream_conn]
        timeout = 60  # Tunnel idle timeout
        try:
            while True:
                readable, _, errors = select.select(conns, [], conns, timeout)
                if errors:
                    break
                if not readable:
                    break  # Timeout
                for sock in readable:
                    other = upstream_conn if sock is client_conn else client_conn
                    try:
                        data = sock.recv(_TUNNEL_BUFSIZE)
                        if not data:
                            return
                        other.sendall(data)
                    except OSError:
                        return
        except Exception:
            pass

    def _send_error(self, code: int, message: str) -> None:
        """Send an error response to the client."""
        body = f"AEGIS Egress Proxy: {message}\n".encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Aegis-Blocked", "true")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass

    def log_message(self, format: str, *args: Any) -> None:
        """Override to use our logger instead of stderr."""
        logger.debug("Proxy: %s", format % args)


class EgressProxyServer:
    """The Narrow Door -- host-side egress proxy server.

    Manages the lifecycle of the HTTP proxy that filters Docker
    container traffic. Runs in a background thread.

    Usage:
        server = EgressProxyServer()
        server.start()
        # ... Orion runs inside Docker, traffic flows through proxy ...
        server.stop()
    """

    def __init__(
        self,
        config: EgressConfig | None = None,
        config_path: str | None = None,
    ) -> None:
        self._config = config or load_config(config_path)
        self._audit = AuditLogger(self._config.audit_log_path)
        self._inspector = ContentInspector(max_body_size=self._config.max_body_size)
        self._rate_limiter = RateLimiter(self._config.global_rate_limit_rpm)

        self._httpd: socketserver.TCPServer | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def config(self) -> EgressConfig:
        return self._config

    @property
    def audit(self) -> AuditLogger:
        return self._audit

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the egress proxy server in a background thread."""
        if self._running:
            logger.warning("Egress proxy already running")
            return

        # Configure handler class with our security components
        EgressProxyHandler.egress_config = self._config
        EgressProxyHandler.audit_logger = self._audit
        EgressProxyHandler.content_inspector = self._inspector
        EgressProxyHandler.rate_limiter = self._rate_limiter

        # Create the TCP server
        socketserver.TCPServer.allow_reuse_address = True
        self._httpd = socketserver.ThreadingTCPServer(
            (self._config.proxy_host, self._config.proxy_port),
            EgressProxyHandler,
        )

        # Start serving in background thread
        self._thread = threading.Thread(
            target=self._serve,
            name="egress-proxy",
            daemon=True,
        )
        self._running = True
        self._thread.start()

        logger.info(
            "Egress proxy started on %s:%d (enforce=%s, domains=%d hardcoded + %d user)",
            self._config.proxy_host,
            self._config.proxy_port,
            self._config.enforce,
            len(self._config.get_all_allowed_domains()) - len(self._config.whitelist),
            len(self._config.whitelist),
        )

    def stop(self) -> None:
        """Stop the egress proxy server."""
        self._running = False
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self._audit.close()
        logger.info("Egress proxy stopped")

    def reload_config(self, config_path: str | None = None) -> None:
        """Reload configuration from disk without restarting."""
        new_config = load_config(config_path)
        self._config = new_config
        EgressProxyHandler.egress_config = new_config
        self._rate_limiter = RateLimiter(new_config.global_rate_limit_rpm)
        EgressProxyHandler.rate_limiter = self._rate_limiter
        logger.info("Egress proxy config reloaded")

    def _serve(self) -> None:
        """Serve requests until stopped."""
        try:
            self._httpd.serve_forever()
        except Exception as exc:
            if self._running:
                logger.error("Egress proxy crashed: %s", exc)
            self._running = False

    def get_status(self) -> dict:
        """Get proxy status for dashboard display."""
        return {
            "running": self._running,
            "host": self._config.proxy_host,
            "port": self._config.proxy_port,
            "enforce": self._config.enforce,
            "content_inspection": self._config.content_inspection,
            "dns_filtering": self._config.dns_filtering,
            "hardcoded_domains": len(self._config.get_all_allowed_domains())
            - len(self._config.whitelist),
            "user_domains": len(self._config.whitelist),
            "rate_limit_stats": self._rate_limiter.get_stats(),
            "audit_stats": self._audit.get_stats(),
            "audit_entries": self._audit.entry_count,
        }
