# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for egress content inspector (credential leakage detection)."""

import pytest

from orion.security.egress.inspector import ContentInspector, InspectionResult


class TestContentInspector:
    """Tests for outbound payload credential detection."""

    def setup_method(self):
        self.inspector = ContentInspector()

    # --- Clean payloads (should pass) ---

    def test_clean_json_payload(self):
        body = '{"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}]}'
        result = self.inspector.inspect(body, "example.com", "POST")
        assert result.clean is True

    def test_clean_text_payload(self):
        result = self.inspector.inspect("Hello world, this is a test", "example.com", "POST")
        assert result.clean is True

    def test_empty_body_is_clean(self):
        result = self.inspector.inspect("", "example.com", "POST")
        assert result.clean is True

    def test_get_requests_always_clean(self):
        body = "sk-1234567890abcdefghij"
        result = self.inspector.inspect(body, "example.com", "GET")
        assert result.clean is True

    def test_head_requests_always_clean(self):
        body = "sk-1234567890abcdefghij"
        result = self.inspector.inspect(body, "example.com", "HEAD")
        assert result.clean is True

    # --- LLM provider exemption ---

    def test_llm_provider_exempt_openai(self):
        body = '{"api_key": "sk-1234567890abcdefghijklmnop"}'
        result = self.inspector.inspect(body, "api.openai.com", "POST")
        assert result.clean is True

    def test_llm_provider_exempt_anthropic(self):
        body = '{"api_key": "sk-ant-1234567890abcdefghijklmnop"}'
        result = self.inspector.inspect(body, "api.anthropic.com", "POST")
        assert result.clean is True

    def test_llm_provider_exempt_google(self):
        body = "AIzaSyD-1234567890abcdefghijklmnopqrstuvw"
        result = self.inspector.inspect(body, "generativelanguage.googleapis.com", "POST")
        assert result.clean is True

    def test_llm_provider_exempt_localhost(self):
        body = "sk-1234567890abcdefghijklmnop"
        result = self.inspector.inspect(body, "localhost", "POST")
        assert result.clean is True

    # --- Credential patterns (should block) ---

    def test_detect_openai_api_key(self):
        body = "Here is my key: sk-1234567890abcdefghijklmnop"
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True
        assert "openai_api_key" in result.patterns_found

    def test_detect_anthropic_api_key(self):
        body = "key: sk-ant-1234567890abcdefghijklmnop"
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True
        assert "anthropic_api_key" in result.patterns_found

    def test_detect_github_token(self):
        body = "token: ghp_1234567890abcdefghijABCDEFGHIJklmnopqr"
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True
        assert "github_token" in result.patterns_found

    def test_detect_aws_access_key(self):
        body = "AKIAIOSFODNN7EXAMPLE"
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True
        assert "aws_access_key" in result.patterns_found

    def test_detect_google_api_key(self):
        body = "key=AIzaSyD-1234567890abcdefghijklmnopqrstuvw"
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True
        assert "google_api_key" in result.patterns_found

    def test_detect_slack_webhook(self):
        body = "https://hooks.slack.com/services/T1234ABCD/B1234ABCD/abcdefghij1234567890"
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True
        assert "slack_webhook" in result.patterns_found

    def test_detect_private_key(self):
        body = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAA..."
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True
        assert "private_key_header" in result.patterns_found

    def test_detect_connection_string(self):
        body = "mongodb://admin:password123@db.example.com:27017/mydb"
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True
        assert "connection_string" in result.patterns_found

    def test_detect_password_assignment(self):
        body = 'password="SuperSecret123!"'
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True
        assert "generic_password_assignment" in result.patterns_found

    # --- Multiple patterns ---

    def test_multiple_patterns_detected(self):
        body = (
            "sk-1234567890abcdefghijklmnop\n"
            "ghp_1234567890abcdefghijABCDEFGHIJklmnopqr\n"
            'password="hunter2hunter2"'
        )
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True
        assert len(result.patterns_found) >= 2

    # --- Bytes input ---

    def test_bytes_input(self):
        body = b"sk-1234567890abcdefghijklmnop"
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True

    def test_bytes_clean_input(self):
        body = b"Hello world"
        result = self.inspector.inspect(body, "example.com", "POST")
        assert result.clean is True

    # --- Details contain redacted info ---

    def test_details_are_redacted(self):
        body = "sk-1234567890abcdefghijklmnop"
        result = self.inspector.inspect(body, "evil.com", "POST")
        assert result.blocked is True
        assert len(result.details) > 0
        # Details should not contain the full key
        for detail in result.details:
            assert "1234567890abcdefghijklmnop" not in detail

    # --- InspectionResult properties ---

    def test_clean_result_not_blocked(self):
        result = InspectionResult(clean=True)
        assert result.blocked is False

    def test_blocked_result(self):
        result = InspectionResult(clean=False, patterns_found=["test"])
        assert result.blocked is True
