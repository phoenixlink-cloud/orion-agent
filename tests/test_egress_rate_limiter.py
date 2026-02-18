# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for egress rate limiter."""

import time

import pytest

from orion.security.egress.rate_limiter import RateLimiter, SlidingWindowCounter


class TestSlidingWindowCounter:
    """Tests for the sliding window counter."""

    def test_empty_counter(self):
        counter = SlidingWindowCounter()
        assert counter.count() == 0

    def test_add_increments(self):
        counter = SlidingWindowCounter()
        assert counter.add() == 1
        assert counter.add() == 2
        assert counter.add() == 3

    def test_count_matches_adds(self):
        counter = SlidingWindowCounter()
        counter.add()
        counter.add()
        counter.add()
        assert counter.count() == 3

    def test_reset_clears(self):
        counter = SlidingWindowCounter()
        counter.add()
        counter.add()
        counter.reset()
        assert counter.count() == 0


class TestRateLimiter:
    """Tests for the per-domain and global rate limiter."""

    def test_first_request_allowed(self):
        limiter = RateLimiter(global_limit_rpm=100)
        result = limiter.check("api.openai.com", domain_limit_rpm=60)
        assert result.allowed is True

    def test_within_domain_limit(self):
        limiter = RateLimiter(global_limit_rpm=100)
        for _ in range(5):
            result = limiter.check("api.openai.com", domain_limit_rpm=10)
        assert result.allowed is True

    def test_domain_limit_exceeded(self):
        limiter = RateLimiter(global_limit_rpm=1000)
        # Fill up domain limit
        for _ in range(10):
            limiter.check("api.openai.com", domain_limit_rpm=10)
        # Next request should be blocked
        result = limiter.check("api.openai.com", domain_limit_rpm=10)
        assert result.allowed is False
        assert "api.openai.com" in result.reason

    def test_global_limit_exceeded(self):
        limiter = RateLimiter(global_limit_rpm=5)
        # Fill up global limit across different domains
        for i in range(5):
            limiter.check(f"domain{i}.com", domain_limit_rpm=100)
        # Next request to any domain should be blocked
        result = limiter.check("another.com", domain_limit_rpm=100)
        assert result.allowed is False
        assert "Global" in result.reason

    def test_different_domains_independent(self):
        limiter = RateLimiter(global_limit_rpm=1000)
        # Fill up domain A
        for _ in range(10):
            limiter.check("a.com", domain_limit_rpm=10)
        # Domain B should still work
        result = limiter.check("b.com", domain_limit_rpm=10)
        assert result.allowed is True

    def test_result_contains_stats(self):
        limiter = RateLimiter(global_limit_rpm=100)
        result = limiter.check("test.com", domain_limit_rpm=60)
        assert result.domain_rpm == 1
        assert result.global_rpm == 1
        assert result.domain_limit == 60
        assert result.global_limit == 100

    def test_get_stats(self):
        limiter = RateLimiter(global_limit_rpm=100)
        limiter.check("a.com", 60)
        limiter.check("a.com", 60)
        limiter.check("b.com", 60)
        stats = limiter.get_stats()
        assert stats["a.com"] == 2
        assert stats["b.com"] == 1
        assert stats["_global"] == 3

    def test_reset_all(self):
        limiter = RateLimiter(global_limit_rpm=100)
        limiter.check("a.com", 60)
        limiter.check("b.com", 60)
        limiter.reset()
        stats = limiter.get_stats()
        assert stats["_global"] == 0

    def test_reset_single_domain(self):
        limiter = RateLimiter(global_limit_rpm=100)
        limiter.check("a.com", 60)
        limiter.check("b.com", 60)
        limiter.reset("a.com")
        stats = limiter.get_stats()
        assert stats.get("a.com", 0) == 0
        assert stats["b.com"] == 1

    def test_hostname_case_insensitive(self):
        limiter = RateLimiter(global_limit_rpm=100)
        limiter.check("API.OpenAI.COM", domain_limit_rpm=10)
        limiter.check("api.openai.com", domain_limit_rpm=10)
        stats = limiter.get_stats()
        assert stats["api.openai.com"] == 2
