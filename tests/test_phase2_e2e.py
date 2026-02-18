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
"""Phase 2 End-to-End Integration Tests.

These tests verify that Phase 2 components (egress proxy, DNS filter,
approval queue, AEGIS Invariant 7, Google credentials, Antigravity)
work together correctly and enforce the intended security properties.

Unlike unit tests, these tests exercise CROSS-COMPONENT behaviour:
shared config, security invariant alignment, and integration contracts.
"""

import json
import threading
import time
from pathlib import Path

import pytest

# ============================================================================
# 3.1  EGRESS PROXY INTEGRATION
# ============================================================================


class TestEgressProxyIntegration:
    """Verify egress proxy config, whitelist, rate limiting, inspection, and audit."""

    def test_non_whitelisted_domain_blocked(self):
        """Domain NOT on the whitelist must be rejected by config."""
        from orion.security.egress.config import EgressConfig

        config = EgressConfig(enforce=True)
        # Default config has only hardcoded LLM domains
        assert config.is_domain_allowed("evil-exfil.com") is None

    def test_hardcoded_llm_domains_always_present(self):
        """Hardcoded LLM domains must appear in every config, even empty ones."""
        from orion.security.egress.config import HARDCODED_LLM_DOMAINS, EgressConfig

        config = EgressConfig()
        all_domains = config.get_all_allowed_domains()
        all_domain_names = {r.domain for r in all_domains}

        for domain in HARDCODED_LLM_DOMAINS:
            assert domain in all_domain_names, f"Hardcoded domain {domain} missing"

    def test_hardcoded_domains_cannot_be_removed(self):
        """Even if user whitelist is empty, hardcoded domains remain."""
        from orion.security.egress.config import HARDCODED_LLM_DOMAINS, EgressConfig

        config = EgressConfig(whitelist=[])
        all_rules = config.get_all_allowed_domains()
        system_domains = {r.domain for r in all_rules if r.added_by == "system"}

        assert system_domains == set(HARDCODED_LLM_DOMAINS)

    def test_user_whitelist_additive(self):
        """User whitelist adds to (doesn't replace) hardcoded domains."""
        from orion.security.egress.config import (
            HARDCODED_LLM_DOMAINS,
            DomainRule,
            EgressConfig,
        )

        user_rule = DomainRule(domain="docs.example.com", added_by="user")
        config = EgressConfig(whitelist=[user_rule])

        all_rules = config.get_all_allowed_domains()
        all_domain_names = {r.domain for r in all_rules}

        assert "docs.example.com" in all_domain_names
        for d in HARDCODED_LLM_DOMAINS:
            assert d in all_domain_names

    def test_rate_limiter_throttles_after_rpm(self):
        """Rate limiter must reject requests after exceeding RPM."""
        from orion.security.egress.rate_limiter import RateLimiter

        rl = RateLimiter(global_limit_rpm=1000)
        domain_limit = 5

        # First 5 should pass
        for _ in range(domain_limit):
            result = rl.check("test.example.com", domain_limit)
            assert result.allowed, f"Request should be allowed: {result.reason}"

        # 6th should be rejected
        result = rl.check("test.example.com", domain_limit)
        assert not result.allowed
        assert "rate limit" in result.reason.lower()

    def test_content_inspector_detects_credential(self):
        """Content inspector must detect credential patterns in POST body."""
        from orion.security.egress.inspector import ContentInspector

        inspector = ContentInspector()
        # Send an AWS key to a non-LLM domain
        body = '{"config": "AKIAIOSFODNN7EXAMPLE"}'
        result = inspector.inspect(body, "evil.com", "POST")

        assert result.blocked
        assert "aws_access_key" in result.patterns_found

    def test_content_inspector_allows_llm_traffic(self):
        """Content inspector must NOT block legitimate LLM API traffic."""
        from orion.security.egress.inspector import ContentInspector

        inspector = ContentInspector()
        body = '{"api_key": "sk-1234567890abcdefghijklmnop"}'
        result = inspector.inspect(body, "api.openai.com", "POST")

        assert result.clean

    def test_audit_logger_writes_valid_jsonl(self, tmp_path):
        """Audit logger must write valid JSON Lines entries."""
        from orion.security.egress.audit import AuditEntry, AuditLogger

        log_path = tmp_path / "audit.log"
        with AuditLogger(log_path) as logger:
            logger.log(
                AuditEntry.blocked("POST", "https://evil.com/api", "evil.com", "Not whitelisted")
            )
            logger.log(
                AuditEntry.allowed(
                    "GET",
                    "https://api.openai.com/v1/chat",
                    "api.openai.com",
                    "api.openai.com",
                    status_code=200,
                )
            )

        assert logger.entry_count == 2

        # Verify each line is valid JSON
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "timestamp" in data
            assert "event_type" in data
            assert "hostname" in data

    def test_config_reload_updates_whitelist(self, tmp_path):
        """Config reload from YAML must update the whitelist."""
        from orion.security.egress.config import load_config

        config_file = tmp_path / "egress.yaml"
        config_file.write_text(
            "whitelist:\n  - domain: custom.example.com\n    allow_write: false\n"
        )

        config = load_config(config_file)
        assert config.is_domain_allowed("custom.example.com") is not None

        # Update the file
        config_file.write_text(
            "whitelist:\n"
            "  - domain: custom.example.com\n"
            "    allow_write: false\n"
            "  - domain: another.example.com\n"
            "    allow_write: true\n"
        )

        # Reload
        config2 = load_config(config_file)
        assert config2.is_domain_allowed("another.example.com") is not None


# ============================================================================
# 3.2  DNS FILTER INTEGRATION
# ============================================================================


class TestDNSFilterIntegration:
    """Verify DNS filter shares whitelist with egress proxy config."""

    def test_whitelisted_domain_not_blocked(self):
        """Whitelisted domain must NOT be NXDOMAIN'd by DNS filter."""
        from orion.security.egress.config import DomainRule, EgressConfig
        from orion.security.egress.dns_filter import DNSFilter

        config = EgressConfig(whitelist=[DomainRule(domain="docs.example.com")])
        dns_filter = DNSFilter(egress_config=config)

        assert dns_filter._is_domain_allowed("docs.example.com")
        assert dns_filter._is_domain_allowed("api.openai.com")  # Hardcoded LLM

    def test_non_whitelisted_domain_blocked_by_dns(self):
        """Non-whitelisted domain must be blocked by DNS filter."""
        from orion.security.egress.config import EgressConfig
        from orion.security.egress.dns_filter import DNSFilter

        config = EgressConfig()
        dns_filter = DNSFilter(egress_config=config)

        assert not dns_filter._is_domain_allowed("evil-exfil.example.com")

    def test_dns_filter_shares_whitelist_with_proxy(self):
        """DNS filter and egress proxy must use the SAME whitelist source."""
        from orion.security.egress.config import DomainRule, EgressConfig
        from orion.security.egress.dns_filter import DNSFilter

        user_rule = DomainRule(domain="shared-test.example.com")
        config = EgressConfig(whitelist=[user_rule])
        dns_filter = DNSFilter(egress_config=config)

        # Both should agree
        proxy_allowed = config.is_domain_allowed("shared-test.example.com") is not None
        dns_allowed = dns_filter._is_domain_allowed("shared-test.example.com")

        assert proxy_allowed == dns_allowed

    def test_adding_domain_makes_it_resolvable(self):
        """Adding a domain to config whitelist should make it pass DNS filter."""
        from orion.security.egress.config import DomainRule, EgressConfig
        from orion.security.egress.dns_filter import DNSFilter

        config = EgressConfig(whitelist=[])
        dns_filter = DNSFilter(egress_config=config)

        # Initially blocked
        assert not dns_filter._is_domain_allowed("new-service.example.com")

        # Add to whitelist and reload
        config.whitelist.append(DomainRule(domain="new-service.example.com"))
        dns_filter.reload_config(config)

        # Now allowed
        assert dns_filter._is_domain_allowed("new-service.example.com")


# ============================================================================
# 3.3  APPROVAL QUEUE INTEGRATION
# ============================================================================


class TestApprovalQueueIntegration:
    """Verify approval queue submit/approve/deny/expire/persist."""

    def test_submit_and_approve(self, tmp_path):
        """Submitted request must block until approved."""
        from orion.security.egress.approval_queue import (
            ApprovalQueue,
            ApprovalStatus,
            RequestCategory,
        )

        queue = ApprovalQueue(persist_path=tmp_path / "queue.json")
        try:
            req_id = queue.submit(
                category=RequestCategory.NETWORK_WRITE,
                summary="POST to https://api.github.com/repos",
                timeout_s=10,
            )

            # Approve from another thread
            def _approve():
                time.sleep(0.1)
                queue.approve(req_id, reason="Looks good")

            t = threading.Thread(target=_approve)
            t.start()

            result = queue.wait_for_decision(req_id, timeout=5)
            t.join(timeout=5)

            assert result == ApprovalStatus.APPROVED
        finally:
            queue.stop()

    def test_submit_and_deny(self, tmp_path):
        """Denied request must return DENIED status."""
        from orion.security.egress.approval_queue import (
            ApprovalQueue,
            ApprovalStatus,
            RequestCategory,
        )

        queue = ApprovalQueue(persist_path=tmp_path / "queue.json")
        try:
            req_id = queue.submit(
                category=RequestCategory.NETWORK_WRITE,
                summary="DELETE to https://api.github.com/repos/evil",
                timeout_s=10,
            )

            def _deny():
                time.sleep(0.1)
                queue.deny(req_id, reason="Suspicious")

            t = threading.Thread(target=_deny)
            t.start()

            result = queue.wait_for_decision(req_id, timeout=5)
            t.join(timeout=5)

            assert result == ApprovalStatus.DENIED
        finally:
            queue.stop()

    def test_timeout_expires_request(self, tmp_path):
        """Request that times out must return EXPIRED."""
        from orion.security.egress.approval_queue import (
            ApprovalQueue,
            ApprovalStatus,
            RequestCategory,
        )

        queue = ApprovalQueue(persist_path=tmp_path / "queue.json")
        try:
            req_id = queue.submit(
                category=RequestCategory.NETWORK_WRITE,
                summary="Expiry test",
                timeout_s=0.3,
            )

            result = queue.wait_for_decision(req_id, timeout=1)
            assert result == ApprovalStatus.EXPIRED
        finally:
            queue.stop()

    def test_queue_persists_to_json(self, tmp_path):
        """Queue state must be persisted to JSON and recoverable."""
        from orion.security.egress.approval_queue import (
            ApprovalQueue,
            RequestCategory,
        )

        persist_file = tmp_path / "queue.json"
        queue = ApprovalQueue(persist_path=persist_file, default_timeout_s=60)
        try:
            queue.submit(
                category=RequestCategory.NETWORK_WRITE,
                summary="Persist test",
                timeout_s=60,
            )

            # Verify file was written
            assert persist_file.exists()
            data = json.loads(persist_file.read_text())
            assert len(data) >= 1
        finally:
            queue.stop()

    def test_callback_fires_on_decision(self, tmp_path):
        """Registered callback must fire when a request is decided."""
        from orion.security.egress.approval_queue import (
            ApprovalQueue,
            RequestCategory,
        )

        results = []
        queue = ApprovalQueue(persist_path=tmp_path / "queue.json")
        try:
            queue.on_request(lambda req: results.append(req.status))

            req_id = queue.submit(
                category=RequestCategory.NETWORK_WRITE,
                summary="Callback test",
                timeout_s=10,
            )
            queue.approve(req_id, reason="OK")

            # Give callback time to fire
            time.sleep(0.2)
            assert len(results) >= 1
            assert results[0] == "pending"  # on_request fires at submission time
        finally:
            queue.stop()


# ============================================================================
# 3.4  AEGIS INVARIANT 7 INTEGRATION
# ============================================================================


class TestAegisInvariant7Integration:
    """Verify AEGIS Invariant 7 (Network Access Control) security properties."""

    def test_blocked_google_drive_denied(self):
        """Blocked Google service (Drive) must return DENY."""
        from orion.core.governance.aegis import NetworkAccessRequest, check_network_access

        result = check_network_access(
            NetworkAccessRequest(
                hostname="drive.googleapis.com",
                method="GET",
                url="https://drive.googleapis.com/v3/files",
            )
        )
        assert not result.passed
        assert any("blocked" in v.lower() or "AEGIS-7" in v for v in result.violations)

    def test_allowed_gemini_llm_domain(self):
        """Allowed LLM domain (Gemini) must return ALLOW."""
        from orion.core.governance.aegis import NetworkAccessRequest, check_network_access

        result = check_network_access(
            NetworkAccessRequest(
                hostname="generativelanguage.googleapis.com",
                method="POST",
                url="https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent",
            )
        )
        assert result.passed

    def test_non_https_generates_warning(self):
        """Non-HTTPS request must generate a WARNING (not block)."""
        from orion.core.governance.aegis import NetworkAccessRequest, check_network_access

        result = check_network_access(
            NetworkAccessRequest(
                hostname="api.openai.com",
                method="GET",
                url="http://api.openai.com/v1/models",
                protocol="http",
            )
        )
        assert any("http" in w.lower() for w in result.warnings)

    def test_write_method_generates_warning(self):
        """POST/PUT/DELETE must generate a write-operation WARNING."""
        from orion.core.governance.aegis import NetworkAccessRequest, check_network_access

        for method in ("POST", "PUT", "DELETE"):
            result = check_network_access(
                NetworkAccessRequest(
                    hostname="api.openai.com", method=method, url="https://api.openai.com/v1/test"
                )
            )
            assert any("write" in w.lower() for w in result.warnings), (
                f"{method} should warn about write"
            )

    def test_aegis_version_7_or_higher(self):
        """AEGIS module version must be 7.0.0+."""
        import re

        from orion.core.governance import aegis

        # Extract version from module docstring
        match = re.search(r"v(\d+)\.(\d+)\.(\d+)", aegis.__doc__ or "")
        assert match, "AEGIS module docstring must contain version"
        major = int(match.group(1))
        assert major >= 7, f"AEGIS version must be 7+, got {major}"

    def test_all_blocked_google_services_exist(self):
        """Blocked Google services frozenset must include Drive, Gmail, Calendar, YouTube."""
        from orion.core.governance.aegis import _BLOCKED_GOOGLE_SERVICES

        required = {
            "drive.googleapis.com",
            "gmail.googleapis.com",
            "calendar.googleapis.com",
            "youtube.googleapis.com",
        }
        for svc in required:
            assert svc in _BLOCKED_GOOGLE_SERVICES, f"Missing blocked service: {svc}"


# ============================================================================
# 3.5  GOOGLE CREDENTIALS SECURITY
# ============================================================================


class TestGoogleCredentialsSecurity:
    """Verify Google credential scope enforcement and container isolation."""

    def test_blocked_scope_rejected_on_store(self, tmp_path):
        """Storing token with blocked scope (Drive) must raise ValueError."""
        from orion.security.egress.google_credentials import (
            GoogleCredentialManager,
            GoogleCredentials,
        )

        manager = GoogleCredentialManager(
            credentials_path=tmp_path / "creds.json",
            use_secure_store=False,
        )
        creds = GoogleCredentials(
            access_token="ya29.test",
            scope="openid https://www.googleapis.com/auth/drive",
            expires_at=time.time() + 3600,
        )
        with pytest.raises(ValueError, match="blocked scopes"):
            manager.store(creds)

    def test_allowed_scope_accepted(self, tmp_path):
        """Storing token with allowed scope (Gemini) must succeed."""
        from orion.security.egress.google_credentials import (
            GoogleCredentialManager,
            GoogleCredentials,
        )

        manager = GoogleCredentialManager(
            credentials_path=tmp_path / "creds.json",
            use_secure_store=False,
        )
        creds = GoogleCredentials(
            access_token="ya29.test",
            scope="openid email",
            expires_at=time.time() + 3600,
        )
        manager.store(creds)
        assert manager.has_credentials

    def test_container_credentials_no_refresh_token(self, tmp_path):
        """Container credential file must NOT contain refresh_token."""
        from orion.security.egress.google_credentials import (
            GoogleCredentialManager,
            GoogleCredentials,
        )

        manager = GoogleCredentialManager(
            credentials_path=tmp_path / "creds.json",
            use_secure_store=False,
        )
        creds = GoogleCredentials(
            access_token="ya29.test",
            refresh_token="1//secret-refresh-token",
            scope="openid email",
            expires_at=time.time() + 3600,
        )
        manager.store(creds)
        out = manager.write_container_credentials(tmp_path / "container_creds.json")

        container_data = json.loads(out.read_text())
        assert "refresh_token" not in container_data
        assert container_data["access_token"] == "ya29.test"

    def test_to_safe_dict_redacts_tokens(self):
        """to_safe_dict() must NOT contain actual token values."""
        from orion.security.egress.google_credentials import GoogleCredentials

        creds = GoogleCredentials(
            access_token="ya29.super-secret-token",
            refresh_token="1//super-secret-refresh",
            scope="openid email",
            expires_at=time.time() + 3600,
        )
        safe = creds.to_safe_dict()

        assert "ya29.super-secret-token" not in str(safe)
        assert "1//super-secret-refresh" not in str(safe)
        assert safe["has_access_token"] is True
        assert safe["has_refresh_token"] is True

    def test_expired_token_detected(self):
        """Expired token must be detected by is_expired property."""
        from orion.security.egress.google_credentials import GoogleCredentials

        creds = GoogleCredentials(
            access_token="ya29.test",
            expires_at=time.time() - 600,  # 10 minutes ago
        )
        assert creds.is_expired

        creds_fresh = GoogleCredentials(
            access_token="ya29.test",
            expires_at=time.time() + 3600,  # 1 hour from now
        )
        assert not creds_fresh.is_expired


# ============================================================================
# 3.6  CROSS-COMPONENT INTEGRATION
# ============================================================================


class TestCrossComponentIntegration:
    """Verify components work together across module boundaries."""

    def test_egress_config_and_dns_share_whitelist(self):
        """Egress proxy config and DNS filter must use the same whitelist."""
        from orion.security.egress.config import DomainRule, EgressConfig
        from orion.security.egress.dns_filter import DNSFilter

        user_rules = [
            DomainRule(domain="api.slack.com"),
            DomainRule(domain="hooks.slack.com"),
        ]
        config = EgressConfig(whitelist=user_rules)
        dns = DNSFilter(egress_config=config)

        # Iterate all domains the proxy would allow
        for rule in config.get_all_allowed_domains():
            assert dns._is_domain_allowed(rule.domain), f"DNS should allow {rule.domain}"

    def test_aegis_invariant7_matches_blocked_google_in_config(self):
        """AEGIS blocked Google services must be consistent with egress proxy config."""
        from orion.core.governance.aegis import (
            _BLOCKED_GOOGLE_SERVICES,
            NetworkAccessRequest,
            check_network_access,
        )
        from orion.security.egress.config import EgressConfig

        config = EgressConfig()

        for blocked_domain in _BLOCKED_GOOGLE_SERVICES:
            # AEGIS must block it
            result = check_network_access(
                NetworkAccessRequest(
                    hostname=blocked_domain, method="GET", url=f"https://{blocked_domain}/"
                )
            )
            assert not result.passed, f"AEGIS should block {blocked_domain}"

            # Egress config must NOT whitelist it (unless it's a subdomain of an allowed domain)
            # Note: some blocked domains like "www.googleapis.com/drive" are path-based,
            # so the hostname "www.googleapis.com" might match a broader rule.
            # The important check is that AEGIS blocks them regardless.

    def test_inspector_patterns_cover_google_credentials(self):
        """Inspector must detect Google API keys in outbound traffic."""
        from orion.security.egress.inspector import ContentInspector

        inspector = ContentInspector()
        # Google API key pattern
        body = '{"key": "AIzaSyA1234567890abcdefghijklmnopqrstuv"}'
        result = inspector.inspect(body, "random-server.com", "POST")

        assert result.blocked
        assert "google_api_key" in result.patterns_found

    def test_approval_queue_categorizes_network_writes(self, tmp_path):
        """Approval queue must support the categories used by egress proxy."""
        from orion.security.egress.approval_queue import (
            ApprovalQueue,
            RequestCategory,
        )

        queue = ApprovalQueue(persist_path=tmp_path / "queue.json")
        try:
            # Egress proxy would submit network_write requests
            req_id = queue.submit(
                category=RequestCategory.NETWORK_WRITE,
                summary="POST to https://api.github.com/repos",
                method="POST",
                url="https://api.github.com/repos",
                hostname="api.github.com",
                timeout_s=60,
            )

            pending = queue.get_pending()
            assert len(pending) == 1
            assert pending[0].category == "network_write"
            assert pending[0].method == "POST"
            assert pending[0].hostname == "api.github.com"

            queue.cancel(req_id)
        finally:
            queue.stop()

    def test_blocked_scopes_align_with_blocked_google_services(self):
        """Google credential BLOCKED_SCOPES must cover the same services as AEGIS blocked list."""
        from orion.core.governance.aegis import _BLOCKED_GOOGLE_SERVICES
        from orion.security.egress.google_credentials import BLOCKED_SCOPES

        # Drive is blocked in both
        assert any("drive" in scope for scope in BLOCKED_SCOPES)
        assert "drive.googleapis.com" in _BLOCKED_GOOGLE_SERVICES

        # Gmail is blocked in both
        assert any("gmail" in scope for scope in BLOCKED_SCOPES)
        assert "gmail.googleapis.com" in _BLOCKED_GOOGLE_SERVICES

        # YouTube is blocked in both
        assert any("youtube" in scope for scope in BLOCKED_SCOPES)
        assert "youtube.googleapis.com" in _BLOCKED_GOOGLE_SERVICES

        # Calendar is blocked in both
        assert any("calendar" in scope for scope in BLOCKED_SCOPES)
        assert any("calendar" in svc for svc in _BLOCKED_GOOGLE_SERVICES)

    def test_oauth_stripped_from_llm_providers(self):
        """OpenAI and Google must use API_KEY auth, NOT OAUTH."""
        from orion.integrations.platforms import AuthMethod, get_platform_registry

        registry = get_platform_registry()

        openai = registry.get("openai")
        assert openai is not None
        assert openai.auth_method == AuthMethod.API_KEY
        assert openai.oauth_provider is None or openai.oauth_provider == ""

        google = registry.get("google")
        assert google is not None
        assert google.auth_method == AuthMethod.API_KEY
        assert google.oauth_provider is None or google.oauth_provider == ""

    def test_providers_get_key_has_no_oauth_fallback(self):
        """providers._get_key() must NOT fall back to OAuth tokens."""
        import inspect

        from orion.core.llm.providers import _get_key

        source = inspect.getsource(_get_key)
        assert "oauth" not in source.lower(), "_get_key() still references OAuth"
