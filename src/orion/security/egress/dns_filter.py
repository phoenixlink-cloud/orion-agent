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
"""DNS filter for container network isolation.

A lightweight DNS proxy that runs on the host side and resolves ONLY
whitelisted domains. Non-whitelisted queries receive NXDOMAIN responses.

This is the second layer of network security (after the egress proxy):
  1. Even if the container somehow bypasses HTTP_PROXY, DNS won't resolve
  2. Prevents DNS-based data exfiltration (encoding data in subdomains)
  3. Blocks DNS rebinding attacks

Architecture:
  Container DNS --UDP/53--> DNSFilter (Host) ---> Upstream DNS (filtered)

The filter shares the same whitelist as the egress proxy (EgressConfig).
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger("orion.security.egress.dns_filter")

# DNS constants
DNS_PORT = 53
DNS_HEADER_SIZE = 12
DNS_MAX_PACKET = 512
DNS_RCODE_NXDOMAIN = 3
DNS_RCODE_NOERROR = 0
DNS_RCODE_SERVFAIL = 2

# Default upstream DNS servers
DEFAULT_UPSTREAM_DNS = ["8.8.8.8", "8.8.4.4"]


@dataclass
class DNSStats:
    """Statistics for DNS filter operations."""

    total_queries: int = 0
    allowed_queries: int = 0
    blocked_queries: int = 0
    failed_queries: int = 0
    unique_domains: set = field(default_factory=set)
    blocked_domains: set = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "total_queries": self.total_queries,
            "allowed_queries": self.allowed_queries,
            "blocked_queries": self.blocked_queries,
            "failed_queries": self.failed_queries,
            "unique_domains": len(self.unique_domains),
            "blocked_domains_count": len(self.blocked_domains),
            "top_blocked": list(self.blocked_domains)[:20],
        }


def parse_dns_name(data: bytes, offset: int) -> tuple[str, int]:
    """Parse a DNS domain name from a packet, handling compression pointers.

    Returns:
        Tuple of (domain_name, new_offset).
    """
    labels: list[str] = []
    original_offset = offset
    jumped = False
    jump_offset = 0

    while offset < len(data):
        length = data[offset]

        # Compression pointer (top 2 bits set)
        if (length & 0xC0) == 0xC0:
            if not jumped:
                jump_offset = offset + 2
            pointer = struct.unpack("!H", data[offset : offset + 2])[0] & 0x3FFF
            offset = pointer
            jumped = True
            continue

        # End of name
        if length == 0:
            offset += 1
            break

        # Regular label
        offset += 1
        label = data[offset : offset + length].decode("ascii", errors="replace")
        labels.append(label)
        offset += length

    domain = ".".join(labels)
    final_offset = jump_offset if jumped else offset
    return domain, final_offset


def build_nxdomain_response(query_data: bytes) -> bytes:
    """Build an NXDOMAIN response for a DNS query.

    Takes the original query and modifies the header to indicate
    the domain does not exist. This is the response for blocked domains.
    """
    if len(query_data) < DNS_HEADER_SIZE:
        return b""

    # Copy the query ID
    transaction_id = query_data[:2]

    # Build response header:
    # QR=1 (response), Opcode=0 (standard), AA=1 (authoritative),
    # TC=0, RD=1, RA=1, Z=0, RCODE=3 (NXDOMAIN)
    flags = struct.pack("!H", 0x8583)  # 1000 0101 1000 0011

    # QDCOUNT=1, ANCOUNT=0, NSCOUNT=0, ARCOUNT=0
    counts = struct.pack("!HHH", 0, 0, 0)

    # Include the question section from the original query
    question_section = query_data[DNS_HEADER_SIZE:]

    return transaction_id + flags + query_data[4:6] + counts + question_section


def build_servfail_response(query_data: bytes) -> bytes:
    """Build a SERVFAIL response for upstream DNS failures."""
    if len(query_data) < DNS_HEADER_SIZE:
        return b""

    transaction_id = query_data[:2]
    flags = struct.pack("!H", 0x8582)  # RCODE=2 (SERVFAIL)
    counts = struct.pack("!HHH", 0, 0, 0)
    question_section = query_data[DNS_HEADER_SIZE:]

    return transaction_id + flags + query_data[4:6] + counts + question_section


class DNSFilter:
    """DNS filtering proxy for container network isolation.

    Intercepts DNS queries and only forwards those for whitelisted
    domains to the upstream DNS server. All other queries receive
    NXDOMAIN responses.

    Usage:
        from orion.security.egress.config import load_config
        config = load_config()
        dns = DNSFilter(config)
        dns.start()
        # ... container runs, DNS queries are filtered ...
        dns.stop()
    """

    def __init__(
        self,
        egress_config=None,
        listen_host: str = "0.0.0.0",
        listen_port: int = DNS_PORT,
        upstream_dns: list[str] | None = None,
    ) -> None:
        from .config import EgressConfig, load_config

        self._config = egress_config or load_config()
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._upstream_dns = upstream_dns or list(DEFAULT_UPSTREAM_DNS)

        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._stats = DNSStats()
        self._lock = threading.Lock()

    @property
    def stats(self) -> DNSStats:
        return self._stats

    @property
    def is_running(self) -> bool:
        return self._running

    def _is_domain_allowed(self, domain: str) -> bool:
        """Check if a domain is in the whitelist."""
        # Strip trailing dot (common in DNS queries)
        domain = domain.rstrip(".")
        return self._config.is_domain_allowed(domain) is not None

    def _forward_to_upstream(self, query_data: bytes) -> bytes | None:
        """Forward a DNS query to the upstream DNS server and return the response."""
        for upstream in self._upstream_dns:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(3.0)
                sock.sendto(query_data, (upstream, DNS_PORT))
                response, _ = sock.recvfrom(DNS_MAX_PACKET)
                sock.close()
                return response
            except (socket.timeout, socket.error, OSError) as exc:
                logger.debug("Upstream DNS %s failed: %s", upstream, exc)
                continue
        return None

    def _handle_query(self, query_data: bytes, client_addr: tuple) -> None:
        """Process a single DNS query."""
        if len(query_data) < DNS_HEADER_SIZE:
            return

        with self._lock:
            self._stats.total_queries += 1

        # Parse the domain name from the question section
        try:
            domain, _ = parse_dns_name(query_data, DNS_HEADER_SIZE)
        except (IndexError, UnicodeDecodeError):
            logger.debug("Failed to parse DNS query from %s", client_addr)
            with self._lock:
                self._stats.failed_queries += 1
            return

        domain_clean = domain.rstrip(".")

        with self._lock:
            self._stats.unique_domains.add(domain_clean)

        # Check whitelist
        if not self._is_domain_allowed(domain_clean):
            # BLOCKED: return NXDOMAIN
            logger.debug("DNS BLOCKED: %s (from %s)", domain_clean, client_addr[0])
            with self._lock:
                self._stats.blocked_queries += 1
                self._stats.blocked_domains.add(domain_clean)
            response = build_nxdomain_response(query_data)
            if response and self._sock:
                try:
                    self._sock.sendto(response, client_addr)
                except OSError:
                    pass
            return

        # ALLOWED: forward to upstream DNS
        logger.debug("DNS ALLOWED: %s (from %s)", domain_clean, client_addr[0])
        response = self._forward_to_upstream(query_data)

        if response is None:
            logger.warning("Upstream DNS failed for allowed domain %s", domain_clean)
            with self._lock:
                self._stats.failed_queries += 1
            response = build_servfail_response(query_data)

        with self._lock:
            self._stats.allowed_queries += 1

        if response and self._sock:
            try:
                self._sock.sendto(response, client_addr)
            except OSError:
                pass

    def start(self) -> None:
        """Start the DNS filter in a background thread."""
        if self._running:
            logger.warning("DNS filter already running")
            return

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._listen_host, self._listen_port))
        self._sock.settimeout(1.0)  # Allow periodic check of _running flag

        self._running = True
        self._thread = threading.Thread(
            target=self._serve,
            name="dns-filter",
            daemon=True,
        )
        self._thread.start()

        logger.info(
            "DNS filter started on %s:%d (upstream: %s)",
            self._listen_host,
            self._listen_port,
            ", ".join(self._upstream_dns),
        )

    def stop(self) -> None:
        """Stop the DNS filter."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("DNS filter stopped")

    def reload_config(self, config=None) -> None:
        """Reload the egress config (updates the whitelist)."""
        from .config import load_config

        self._config = config or load_config()
        logger.info("DNS filter config reloaded")

    def _serve(self) -> None:
        """Listen for DNS queries and process them."""
        while self._running:
            try:
                data, addr = self._sock.recvfrom(DNS_MAX_PACKET)
                # Handle each query in a separate thread to avoid blocking
                threading.Thread(
                    target=self._handle_query,
                    args=(data, addr),
                    daemon=True,
                ).start()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    logger.error("DNS filter socket error")
                break

    def get_status(self) -> dict:
        """Get DNS filter status for dashboard display."""
        return {
            "running": self._running,
            "listen_host": self._listen_host,
            "listen_port": self._listen_port,
            "upstream_dns": self._upstream_dns,
            "stats": self._stats.to_dict(),
        }
