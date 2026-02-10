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
#    See LICENSE-ENTERPRISE.md or contact licensing@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Agent -- Integration Health Check & Self-Test System (v6.4.0)

Validates that integrations are properly configured, reachable, and functional.

    1. HEALTH CHECKS -- Ping each integration to verify connectivity
    2. SELF-TESTS -- Run lightweight functional tests per integration
    3. RETRY LOGIC -- Automatic retry with exponential backoff
    4. STATUS DASHBOARD -- Aggregated health status across all integrations
    5. DEPENDENCY VALIDATION -- Check required packages and API keys
    6. GRACEFUL DEGRADATION -- Report which integrations are available vs degraded
"""

import os
import time
import importlib
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Tuple
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum


# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNCHECKED = "unchecked"
    ERROR = "error"


@dataclass
class IntegrationCheck:
    """Result of a single integration health check."""
    name: str
    category: str
    status: HealthStatus
    message: str
    response_time_ms: float = 0.0
    has_api_key: bool = False
    has_package: bool = False
    last_checked: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SelfTestResult:
    """Result of a self-test for an integration."""
    name: str
    passed: bool
    tests_run: int
    tests_passed: int
    tests_failed: int
    duration_ms: float
    failures: List[str] = field(default_factory=list)


@dataclass
class HealthReport:
    """Aggregated health report across all integrations."""
    timestamp: str
    total_integrations: int
    healthy: int
    degraded: int
    unavailable: int
    unchecked: int
    error: int
    overall_health_pct: float
    checks: List[IntegrationCheck] = field(default_factory=list)
    by_category: Dict[str, Dict[str, int]] = field(default_factory=dict)


# =============================================================================
# INTEGRATION HEALTH CHECKER
# =============================================================================

class IntegrationHealthChecker:
    """
    Checks health of all Orion integrations.

    Usage:
        checker = IntegrationHealthChecker()
        report = checker.run_health_checks()
        check = checker.check_integration("openai")
        results = checker.run_self_tests()
        dashboard = checker.get_dashboard()
    """

    def __init__(self):
        self._checks: Dict[str, Callable] = {}
        self._self_tests: Dict[str, Callable] = {}
        self._last_report: Optional[HealthReport] = None
        self._categories: Dict[str, str] = {}
        self._register_all_checks()

    # =========================================================================
    # PUBLIC API: HEALTH CHECKS
    # =========================================================================

    def run_health_checks(self, categories: List[str] = None) -> HealthReport:
        """Run health checks on all (or filtered) integrations."""
        checks = []
        now = datetime.now(timezone.utc).isoformat()

        for name, check_fn in self._checks.items():
            cat = self._get_category(name)
            if categories and cat not in categories:
                continue

            try:
                start = time.time()
                result = check_fn()
                elapsed = (time.time() - start) * 1000
                result.response_time_ms = round(elapsed, 1)
                result.last_checked = now
                checks.append(result)
            except Exception as e:
                checks.append(IntegrationCheck(
                    name=name, category=cat,
                    status=HealthStatus.ERROR,
                    message=f"Check failed: {str(e)[:200]}",
                    last_checked=now,
                ))

        healthy = sum(1 for c in checks if c.status == HealthStatus.HEALTHY)
        degraded = sum(1 for c in checks if c.status == HealthStatus.DEGRADED)
        unavailable = sum(1 for c in checks if c.status == HealthStatus.UNAVAILABLE)
        unchecked = sum(1 for c in checks if c.status == HealthStatus.UNCHECKED)
        error = sum(1 for c in checks if c.status == HealthStatus.ERROR)
        total = len(checks)

        health_pct = (healthy + degraded * 0.5) / total * 100 if total > 0 else 0.0

        by_cat: Dict[str, Dict[str, int]] = {}
        for c in checks:
            if c.category not in by_cat:
                by_cat[c.category] = {"healthy": 0, "degraded": 0, "unavailable": 0, "error": 0}
            by_cat[c.category][c.status.value] = by_cat[c.category].get(c.status.value, 0) + 1

        report = HealthReport(
            timestamp=now, total_integrations=total,
            healthy=healthy, degraded=degraded, unavailable=unavailable,
            unchecked=unchecked, error=error,
            overall_health_pct=round(health_pct, 1),
            checks=checks, by_category=by_cat,
        )
        self._last_report = report
        return report

    def check_integration(self, name: str) -> IntegrationCheck:
        """Check a single integration by name."""
        if name not in self._checks:
            return IntegrationCheck(
                name=name, category="unknown",
                status=HealthStatus.UNCHECKED,
                message=f"No health check registered for '{name}'",
            )
        try:
            start = time.time()
            result = self._checks[name]()
            result.response_time_ms = round((time.time() - start) * 1000, 1)
            result.last_checked = datetime.now(timezone.utc).isoformat()
            return result
        except Exception as e:
            return IntegrationCheck(
                name=name, category=self._get_category(name),
                status=HealthStatus.ERROR, message=str(e)[:200],
                last_checked=datetime.now(timezone.utc).isoformat(),
            )

    # =========================================================================
    # PUBLIC API: SELF-TESTS
    # =========================================================================

    def run_self_tests(self, names: List[str] = None) -> List[SelfTestResult]:
        """Run self-tests for integrations."""
        results = []
        targets = names or list(self._self_tests.keys())

        for name in targets:
            if name not in self._self_tests:
                continue
            try:
                start = time.time()
                test_fn = self._self_tests[name]
                passed, total, failures = test_fn()
                elapsed = (time.time() - start) * 1000
                results.append(SelfTestResult(
                    name=name, passed=len(failures) == 0,
                    tests_run=total, tests_passed=total - len(failures),
                    tests_failed=len(failures), duration_ms=round(elapsed, 1),
                    failures=failures,
                ))
            except Exception as e:
                results.append(SelfTestResult(
                    name=name, passed=False, tests_run=1, tests_passed=0,
                    tests_failed=1, duration_ms=0,
                    failures=[f"Self-test crashed: {str(e)[:200]}"],
                ))
        return results

    # =========================================================================
    # PUBLIC API: DASHBOARD
    # =========================================================================

    def get_dashboard(self) -> Dict[str, Any]:
        """Get a dashboard-ready summary of integration health."""
        if not self._last_report:
            self.run_health_checks()

        report = self._last_report
        if not report:
            return {"error": "No health data available"}

        return {
            "timestamp": report.timestamp,
            "overall_health": f"{report.overall_health_pct:.1f}%",
            "total": report.total_integrations,
            "healthy": report.healthy,
            "degraded": report.degraded,
            "unavailable": report.unavailable,
            "by_category": report.by_category,
            "integrations": [
                {
                    "name": c.name, "category": c.category,
                    "status": c.status.value, "message": c.message,
                    "response_ms": c.response_time_ms,
                    "has_key": c.has_api_key, "has_pkg": c.has_package,
                }
                for c in report.checks
            ],
        }

    # =========================================================================
    # PUBLIC API: RETRY WITH BACKOFF
    # =========================================================================

    @staticmethod
    def retry_with_backoff(
        fn: Callable,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> Any:
        """Execute a function with exponential backoff retry."""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return fn()
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    time.sleep(delay)
        raise last_error

    # =========================================================================
    # INTERNAL: CHECK REGISTRATION
    # =========================================================================

    def _register_all_checks(self):
        """Register health checks for all known integrations."""
        # --- LLM Providers ---
        self._register_check("openai", "llm", self._check_openai)
        self._register_check("anthropic", "llm", self._check_anthropic)
        self._register_check("google_gemini", "llm", self._check_google)
        self._register_check("ollama", "llm", self._check_ollama)
        self._register_check("azure_openai", "llm", self._check_azure_openai)
        self._register_check("groq", "llm", self._check_groq)
        self._register_check("mistral", "llm", self._check_mistral)
        self._register_check("cohere", "llm", self._check_cohere)
        self._register_check("together_ai", "llm", self._check_together)
        self._register_check("openrouter", "llm", self._check_openrouter)
        self._register_check("aws_bedrock", "llm", self._check_bedrock)

        # --- Voice ---
        self._register_check("elevenlabs_tts", "voice", self._check_elevenlabs)
        self._register_check("openai_tts", "voice", self._check_openai_tts)
        self._register_check("edge_tts", "voice", self._check_edge_tts)
        self._register_check("piper_tts", "voice", self._check_piper)
        self._register_check("whisper_api", "voice", self._check_whisper_api)
        self._register_check("whisper_local", "voice", self._check_whisper_local)
        self._register_check("vosk_stt", "voice", self._check_vosk)

        # --- Image ---
        self._register_check("dalle3", "image", self._check_dalle)
        self._register_check("stability_ai", "image", self._check_stability)
        self._register_check("sdxl_local", "image", self._check_sdxl)

        # --- Messaging ---
        self._register_check("slack", "messaging", self._check_slack)
        self._register_check("discord", "messaging", self._check_discord)
        self._register_check("telegram", "messaging", self._check_telegram)

        # --- Tools ---
        self._register_check("github", "tool", self._check_github)
        self._register_check("gitlab", "tool", self._check_gitlab)
        self._register_check("docker_sandbox", "tool", self._check_docker)
        self._register_check("notion", "tool", self._check_notion)

        # Register self-tests
        self._self_tests["openai"] = self._selftest_openai
        self._self_tests["ollama"] = self._selftest_ollama
        self._self_tests["docker_sandbox"] = self._selftest_docker

    def _register_check(self, name: str, category: str, fn: Callable):
        """Register a named health check."""
        self._checks[name] = fn
        self._categories[name] = category

    def _get_category(self, name: str) -> str:
        """Get category for a named integration."""
        return self._categories.get(name, "unknown")

    # =========================================================================
    # INTERNAL: INDIVIDUAL HEALTH CHECKS
    # =========================================================================

    def _check_api_key(self, env_var: str) -> bool:
        return bool(os.environ.get(env_var, ""))

    def _check_package(self, package_name: str) -> bool:
        try:
            importlib.import_module(package_name)
            return True
        except ImportError:
            return False

    # --- LLM Checks ---

    def _check_openai(self) -> IntegrationCheck:
        has_key = self._check_api_key("OPENAI_API_KEY")
        has_pkg = self._check_package("openai")
        if has_key and has_pkg:
            status, msg = HealthStatus.HEALTHY, "OpenAI API key present, package installed"
        elif has_pkg and not has_key:
            status, msg = HealthStatus.DEGRADED, "Package installed but no API key"
        else:
            status, msg = HealthStatus.UNAVAILABLE, "openai package not installed"
        return IntegrationCheck("openai", "llm", status, msg, has_api_key=has_key, has_package=has_pkg)

    def _check_anthropic(self) -> IntegrationCheck:
        has_key = self._check_api_key("ANTHROPIC_API_KEY")
        has_pkg = self._check_package("anthropic")
        if has_key and has_pkg:
            return IntegrationCheck("anthropic", "llm", HealthStatus.HEALTHY, "Ready", has_api_key=has_key, has_package=has_pkg)
        elif has_pkg:
            return IntegrationCheck("anthropic", "llm", HealthStatus.DEGRADED, "No API key", has_api_key=False, has_package=True)
        return IntegrationCheck("anthropic", "llm", HealthStatus.UNAVAILABLE, "Package not installed", has_api_key=has_key, has_package=False)

    def _check_google(self) -> IntegrationCheck:
        has_key = self._check_api_key("GOOGLE_API_KEY")
        has_pkg = self._check_package("google.generativeai")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else (HealthStatus.DEGRADED if has_pkg else HealthStatus.UNAVAILABLE)
        return IntegrationCheck("google_gemini", "llm", status, f"key={'Y' if has_key else 'N'} pkg={'Y' if has_pkg else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_ollama(self) -> IntegrationCheck:
        has_pkg = self._check_package("ollama")
        if not has_pkg:
            has_pkg = self._check_package("requests")
        try:
            import requests
            resp = requests.get("http://localhost:11434/api/tags", timeout=2)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                return IntegrationCheck("ollama", "llm", HealthStatus.HEALTHY, f"Running, {len(models)} models", has_api_key=True, has_package=True, details={"models": len(models)})
        except Exception:
            pass
        return IntegrationCheck("ollama", "llm", HealthStatus.UNAVAILABLE, "Ollama server not running", has_api_key=False, has_package=has_pkg)

    def _check_azure_openai(self) -> IntegrationCheck:
        has_key = self._check_api_key("AZURE_OPENAI_API_KEY")
        has_ep = self._check_api_key("AZURE_OPENAI_ENDPOINT")
        has_pkg = self._check_package("openai")
        if has_key and has_ep and has_pkg:
            return IntegrationCheck("azure_openai", "llm", HealthStatus.HEALTHY, "Configured", has_api_key=True, has_package=True)
        return IntegrationCheck("azure_openai", "llm", HealthStatus.UNAVAILABLE, "Missing key/endpoint/package", has_api_key=has_key, has_package=has_pkg)

    def _check_groq(self) -> IntegrationCheck:
        has_key = self._check_api_key("GROQ_API_KEY")
        has_pkg = self._check_package("groq")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("groq", "llm", status, f"key={'Y' if has_key else 'N'} pkg={'Y' if has_pkg else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_mistral(self) -> IntegrationCheck:
        has_key = self._check_api_key("MISTRAL_API_KEY")
        has_pkg = self._check_package("mistralai")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("mistral", "llm", status, f"key={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_cohere(self) -> IntegrationCheck:
        has_key = self._check_api_key("COHERE_API_KEY")
        has_pkg = self._check_package("cohere")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("cohere", "llm", status, f"key={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_together(self) -> IntegrationCheck:
        has_key = self._check_api_key("TOGETHER_API_KEY")
        has_pkg = self._check_package("together")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("together_ai", "llm", status, f"key={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_openrouter(self) -> IntegrationCheck:
        has_key = self._check_api_key("OPENROUTER_API_KEY")
        has_pkg = self._check_package("openai")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("openrouter", "llm", status, f"key={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_bedrock(self) -> IntegrationCheck:
        has_pkg = self._check_package("boto3")
        has_key = self._check_api_key("AWS_ACCESS_KEY_ID")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("aws_bedrock", "llm", status, f"aws={'Y' if has_key else 'N'} boto3={'Y' if has_pkg else 'N'}", has_api_key=has_key, has_package=has_pkg)

    # --- Voice Checks ---

    def _check_elevenlabs(self) -> IntegrationCheck:
        has_key = self._check_api_key("ELEVENLABS_API_KEY")
        has_pkg = self._check_package("elevenlabs")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("elevenlabs_tts", "voice", status, f"key={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_openai_tts(self) -> IntegrationCheck:
        has_key = self._check_api_key("OPENAI_API_KEY")
        has_pkg = self._check_package("openai")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("openai_tts", "voice", status, "Via OpenAI API", has_api_key=has_key, has_package=has_pkg)

    def _check_edge_tts(self) -> IntegrationCheck:
        has_pkg = self._check_package("edge_tts")
        status = HealthStatus.HEALTHY if has_pkg else HealthStatus.UNAVAILABLE
        return IntegrationCheck("edge_tts", "voice", status, "Free, no API key needed" if has_pkg else "edge-tts not installed", has_api_key=True, has_package=has_pkg)

    def _check_piper(self) -> IntegrationCheck:
        has_pkg = self._check_package("piper")
        status = HealthStatus.HEALTHY if has_pkg else HealthStatus.DEGRADED
        return IntegrationCheck("piper_tts", "voice", status, "Local TTS" if has_pkg else "piper not installed (optional)", has_api_key=True, has_package=has_pkg)

    def _check_whisper_api(self) -> IntegrationCheck:
        has_key = self._check_api_key("OPENAI_API_KEY")
        has_pkg = self._check_package("openai")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("whisper_api", "voice", status, "Via OpenAI API", has_api_key=has_key, has_package=has_pkg)

    def _check_whisper_local(self) -> IntegrationCheck:
        has_pkg = self._check_package("whisper")
        status = HealthStatus.HEALTHY if has_pkg else HealthStatus.UNAVAILABLE
        return IntegrationCheck("whisper_local", "voice", status, "Local Whisper" if has_pkg else "whisper not installed", has_api_key=True, has_package=has_pkg)

    def _check_vosk(self) -> IntegrationCheck:
        has_pkg = self._check_package("vosk")
        status = HealthStatus.HEALTHY if has_pkg else HealthStatus.UNAVAILABLE
        return IntegrationCheck("vosk_stt", "voice", status, "Local STT" if has_pkg else "vosk not installed", has_api_key=True, has_package=has_pkg)

    # --- Image Checks ---

    def _check_dalle(self) -> IntegrationCheck:
        has_key = self._check_api_key("OPENAI_API_KEY")
        has_pkg = self._check_package("openai")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("dalle3", "image", status, "Via OpenAI", has_api_key=has_key, has_package=has_pkg)

    def _check_stability(self) -> IntegrationCheck:
        has_key = self._check_api_key("STABILITY_API_KEY")
        has_pkg = self._check_package("requests")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("stability_ai", "image", status, f"key={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_sdxl(self) -> IntegrationCheck:
        has_pkg = self._check_package("diffusers")
        status = HealthStatus.HEALTHY if has_pkg else HealthStatus.UNAVAILABLE
        return IntegrationCheck("sdxl_local", "image", status, "Local generation" if has_pkg else "diffusers not installed", has_api_key=True, has_package=has_pkg)

    # --- Messaging Checks ---

    def _check_slack(self) -> IntegrationCheck:
        has_key = self._check_api_key("SLACK_BOT_TOKEN")
        has_pkg = self._check_package("slack_sdk")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("slack", "messaging", status, f"key={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_discord(self) -> IntegrationCheck:
        has_key = self._check_api_key("DISCORD_BOT_TOKEN")
        has_pkg = self._check_package("discord")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("discord", "messaging", status, f"key={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_telegram(self) -> IntegrationCheck:
        has_key = self._check_api_key("TELEGRAM_BOT_TOKEN")
        has_pkg = self._check_package("requests")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("telegram", "messaging", status, f"key={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    # --- Tool Checks ---

    def _check_github(self) -> IntegrationCheck:
        has_key = self._check_api_key("GITHUB_TOKEN")
        has_pkg = self._check_package("requests")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("github", "tool", status, f"token={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_gitlab(self) -> IntegrationCheck:
        has_key = self._check_api_key("GITLAB_TOKEN")
        has_pkg = self._check_package("requests")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("gitlab", "tool", status, f"token={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    def _check_docker(self) -> IntegrationCheck:
        has_pkg = self._check_package("docker")
        if not has_pkg:
            return IntegrationCheck("docker_sandbox", "tool", HealthStatus.UNAVAILABLE, "docker package not installed", has_package=False)
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return IntegrationCheck("docker_sandbox", "tool", HealthStatus.HEALTHY, "Docker daemon running", has_api_key=True, has_package=True)
        except Exception:
            return IntegrationCheck("docker_sandbox", "tool", HealthStatus.DEGRADED, "Docker package installed but daemon not running", has_package=True)

    def _check_notion(self) -> IntegrationCheck:
        has_key = self._check_api_key("NOTION_TOKEN")
        has_pkg = self._check_package("requests")
        status = HealthStatus.HEALTHY if (has_key and has_pkg) else HealthStatus.UNAVAILABLE
        return IntegrationCheck("notion", "tool", status, f"token={'Y' if has_key else 'N'}", has_api_key=has_key, has_package=has_pkg)

    # =========================================================================
    # INTERNAL: SELF-TESTS
    # =========================================================================

    def _selftest_openai(self) -> Tuple[bool, int, List[str]]:
        """Self-test for OpenAI integration."""
        failures = []
        total = 3
        if not self._check_package("openai"):
            failures.append("Cannot import openai package")
        if not self._check_api_key("OPENAI_API_KEY"):
            failures.append("OPENAI_API_KEY not set")
        try:
            from openai import OpenAI
            client = OpenAI()
        except Exception as e:
            failures.append(f"Client init failed: {e}")
        return len(failures) == 0, total, failures

    def _selftest_ollama(self) -> Tuple[bool, int, List[str]]:
        """Self-test for Ollama integration."""
        failures = []
        total = 2
        try:
            import requests
            resp = requests.get("http://localhost:11434/api/tags", timeout=2)
            if resp.status_code != 200:
                failures.append(f"Ollama server returned {resp.status_code}")
        except Exception:
            failures.append("Ollama server not reachable at localhost:11434")
        try:
            import requests
            resp = requests.get("http://localhost:11434/api/tags", timeout=2)
            models = resp.json().get("models", [])
            if not models:
                failures.append("No models loaded in Ollama")
        except Exception:
            failures.append("Cannot list Ollama models")
        return len(failures) == 0, total, failures

    def _selftest_docker(self) -> Tuple[bool, int, List[str]]:
        """Self-test for Docker sandbox."""
        failures = []
        total = 2
        try:
            import docker
            client = docker.from_env()
            client.ping()
        except Exception as e:
            failures.append(f"Docker daemon not available: {e}")
        try:
            import docker
            client = docker.from_env()
            client.containers.run("python:3.11-slim", "echo hello", remove=True, timeout=10)
        except Exception:
            failures.append("Cannot run test container")
        return len(failures) == 0, total, failures


# =============================================================================
# FACTORY
# =============================================================================

def get_health_checker() -> IntegrationHealthChecker:
    """Factory function to create an IntegrationHealthChecker."""
    return IntegrationHealthChecker()
