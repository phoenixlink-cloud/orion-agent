# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for egress DNS filter."""

import socket
import struct
import threading
import time

import pytest

from orion.security.egress.config import DomainRule, EgressConfig
from orion.security.egress.dns_filter import (
    DNSFilter,
    DNSStats,
    build_nxdomain_response,
    build_servfail_response,
    parse_dns_name,
)


def _build_dns_query(domain: str, qtype: int = 1) -> bytes:
    """Build a minimal DNS query packet for testing.

    Args:
        domain: The domain to query (e.g. "api.openai.com").
        qtype: Query type (1=A, 28=AAAA).

    Returns:
        Raw DNS query bytes.
    """
    # Transaction ID
    txid = struct.pack("!H", 0x1234)
    # Flags: standard query, recursion desired
    flags = struct.pack("!H", 0x0100)
    # QDCOUNT=1, ANCOUNT=0, NSCOUNT=0, ARCOUNT=0
    counts = struct.pack("!HHHH", 1, 0, 0, 0)

    # Question section: encode domain name
    question = b""
    for label in domain.split("."):
        question += struct.pack("B", len(label)) + label.encode("ascii")
    question += b"\x00"  # Root label

    # QTYPE and QCLASS (IN)
    question += struct.pack("!HH", qtype, 1)

    return txid + flags + counts + question


def _find_free_port() -> int:
    """Find an available UDP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestParseDNSName:
    """Tests for DNS name parsing."""

    def test_simple_domain(self):
        query = _build_dns_query("example.com")
        name, offset = parse_dns_name(query, 12)  # Skip header
        assert name == "example.com"

    def test_subdomain(self):
        query = _build_dns_query("api.openai.com")
        name, offset = parse_dns_name(query, 12)
        assert name == "api.openai.com"

    def test_deep_subdomain(self):
        query = _build_dns_query("a.b.c.d.example.com")
        name, offset = parse_dns_name(query, 12)
        assert name == "a.b.c.d.example.com"

    def test_single_label(self):
        query = _build_dns_query("localhost")
        name, offset = parse_dns_name(query, 12)
        assert name == "localhost"


class TestBuildResponses:
    """Tests for DNS response builders."""

    def test_nxdomain_response_valid(self):
        query = _build_dns_query("evil.com")
        response = build_nxdomain_response(query)
        assert len(response) > 0
        # Check transaction ID matches
        assert response[:2] == query[:2]
        # Check QR bit is set (response)
        flags = struct.unpack("!H", response[2:4])[0]
        assert flags & 0x8000  # QR=1
        # Check RCODE=3 (NXDOMAIN)
        assert (flags & 0x000F) == 3

    def test_servfail_response_valid(self):
        query = _build_dns_query("test.com")
        response = build_servfail_response(query)
        assert len(response) > 0
        assert response[:2] == query[:2]
        flags = struct.unpack("!H", response[2:4])[0]
        assert (flags & 0x000F) == 2  # RCODE=2 (SERVFAIL)

    def test_nxdomain_short_query(self):
        response = build_nxdomain_response(b"short")
        assert response == b""

    def test_servfail_short_query(self):
        response = build_servfail_response(b"short")
        assert response == b""


class TestDNSStats:
    """Tests for DNS statistics tracking."""

    def test_initial_stats(self):
        stats = DNSStats()
        assert stats.total_queries == 0
        assert stats.allowed_queries == 0
        assert stats.blocked_queries == 0

    def test_to_dict(self):
        stats = DNSStats()
        stats.total_queries = 10
        stats.allowed_queries = 7
        stats.blocked_queries = 3
        stats.unique_domains.add("test.com")
        d = stats.to_dict()
        assert d["total_queries"] == 10
        assert d["allowed_queries"] == 7
        assert d["blocked_queries"] == 3
        assert d["unique_domains"] == 1


class TestDNSFilter:
    """Tests for the DNS filter server."""

    def _make_config(self) -> EgressConfig:
        """Create a test config with some whitelisted domains."""
        return EgressConfig(
            whitelist=[
                DomainRule(domain="github.com"),
                DomainRule(domain="pypi.org"),
            ],
        )

    def test_is_domain_allowed_hardcoded(self):
        config = self._make_config()
        dns = DNSFilter(egress_config=config, listen_port=0)
        assert dns._is_domain_allowed("api.openai.com") is True
        assert dns._is_domain_allowed("api.anthropic.com") is True
        assert dns._is_domain_allowed("localhost") is True

    def test_is_domain_allowed_user_whitelist(self):
        config = self._make_config()
        dns = DNSFilter(egress_config=config, listen_port=0)
        assert dns._is_domain_allowed("github.com") is True
        assert dns._is_domain_allowed("api.github.com") is True  # subdomain
        assert dns._is_domain_allowed("pypi.org") is True

    def test_is_domain_blocked(self):
        config = self._make_config()
        dns = DNSFilter(egress_config=config, listen_port=0)
        assert dns._is_domain_allowed("evil.com") is False
        assert dns._is_domain_allowed("malware.xyz") is False

    def test_trailing_dot_stripped(self):
        config = self._make_config()
        dns = DNSFilter(egress_config=config, listen_port=0)
        assert dns._is_domain_allowed("api.openai.com.") is True
        assert dns._is_domain_allowed("evil.com.") is False

    def test_start_and_stop(self):
        port = _find_free_port()
        config = self._make_config()
        dns = DNSFilter(egress_config=config, listen_port=port)

        assert dns.is_running is False
        dns.start()
        assert dns.is_running is True
        time.sleep(0.2)
        dns.stop()
        assert dns.is_running is False

    def test_blocked_domain_gets_nxdomain(self):
        port = _find_free_port()
        config = self._make_config()
        dns = DNSFilter(egress_config=config, listen_port=port)
        dns.start()
        time.sleep(0.2)

        try:
            # Send a query for a blocked domain
            query = _build_dns_query("evil.com")
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2.0)
            sock.sendto(query, ("127.0.0.1", port))
            response, _ = sock.recvfrom(512)
            sock.close()

            # Verify NXDOMAIN response
            assert len(response) > 0
            assert response[:2] == query[:2]  # Transaction ID matches
            flags = struct.unpack("!H", response[2:4])[0]
            assert (flags & 0x000F) == 3  # RCODE=3 (NXDOMAIN)

            # Stats should reflect the blocked query
            assert dns.stats.blocked_queries >= 1
        finally:
            dns.stop()

    def test_allowed_domain_gets_forwarded(self):
        port = _find_free_port()
        config = self._make_config()
        dns = DNSFilter(egress_config=config, listen_port=port)
        dns.start()
        time.sleep(0.2)

        try:
            # Send a query for an allowed domain (api.openai.com)
            query = _build_dns_query("api.openai.com")
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5.0)
            sock.sendto(query, ("127.0.0.1", port))

            try:
                response, _ = sock.recvfrom(512)
                # Should get a response (either real answer or SERVFAIL if no internet)
                assert len(response) > 0
                assert response[:2] == query[:2]  # Transaction ID matches
                flags = struct.unpack("!H", response[2:4])[0]
                rcode = flags & 0x000F
                # Should NOT be NXDOMAIN (3) -- either NOERROR (0) or SERVFAIL (2)
                assert rcode != 3, "Allowed domain should not get NXDOMAIN"
            except socket.timeout:
                # If there's no internet, the upstream DNS will time out
                # This is acceptable -- the key test is that it wasn't blocked
                pass
            finally:
                sock.close()

            # Stats should show at least one allowed or failed query (not blocked)
            assert dns.stats.blocked_queries == 0
        finally:
            dns.stop()

    def test_get_status(self):
        port = _find_free_port()
        config = self._make_config()
        dns = DNSFilter(egress_config=config, listen_port=port)
        dns.start()
        time.sleep(0.1)

        status = dns.get_status()
        assert status["running"] is True
        assert status["listen_port"] == port
        assert isinstance(status["stats"], dict)
        assert "total_queries" in status["stats"]

        dns.stop()

    def test_reload_config(self):
        port = _find_free_port()
        config = self._make_config()
        dns = DNSFilter(egress_config=config, listen_port=port)

        # Initially evil.com is blocked
        assert dns._is_domain_allowed("evil.com") is False

        # Reload with new config that includes evil.com
        new_config = EgressConfig(
            whitelist=[DomainRule(domain="evil.com")],
        )
        dns.reload_config(new_config)

        # Now evil.com should be allowed
        assert dns._is_domain_allowed("evil.com") is True

    def test_multiple_blocked_queries_tracked(self):
        port = _find_free_port()
        config = self._make_config()
        dns = DNSFilter(egress_config=config, listen_port=port)
        dns.start()
        time.sleep(0.2)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2.0)

            # Send queries for multiple blocked domains
            for domain in ["evil.com", "malware.xyz", "phishing.net"]:
                query = _build_dns_query(domain)
                sock.sendto(query, ("127.0.0.1", port))
                try:
                    sock.recvfrom(512)
                except socket.timeout:
                    pass

            sock.close()
            time.sleep(0.3)

            assert dns.stats.blocked_queries >= 3
            assert dns.stats.total_queries >= 3
        finally:
            dns.stop()
