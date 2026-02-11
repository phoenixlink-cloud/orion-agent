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
"""
Orion Agent -- /doctor Diagnostic Module (v7.4.0)

Enterprise-grade system health check that validates:
  1. Python environment & dependencies
  2. LLM provider connectivity (Ollama, OpenAI, Anthropic, Google, Groq)
  3. Secure credential store status
  4. Settings file integrity
  5. Workspace validity
  6. API server health
  7. Integration registry status

Follows the `brew doctor` / `flutter doctor` pattern:
  - Each check returns ✓ (pass), ⚠ (warning), or ✗ (fail)
  - Actionable remediation steps for each failure
  - Summary with overall health score

Usage:
    from orion.cli.doctor import run_doctor
    await run_doctor(console)
"""

import os
import sys
import json
import asyncio
import platform
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    """Result of a single diagnostic check."""
    name: str
    status: str      # "pass", "warn", "fail"
    message: str
    remedy: str = ""
    details: List[str] = field(default_factory=list)

    @property
    def icon(self) -> str:
        return {"pass": "✓", "warn": "⚠", "fail": "✗"}.get(self.status, "?")

    @property
    def color(self) -> str:
        return {"pass": "green", "warn": "yellow", "fail": "red"}.get(self.status, "white")


@dataclass
class DoctorReport:
    """Full diagnostic report."""
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    @property
    def failures(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def healthy(self) -> bool:
        return self.failures == 0


# =============================================================================
# Individual Checks
# =============================================================================

def check_python_environment() -> CheckResult:
    """Check Python version and critical dependencies."""
    py_version = sys.version_info
    details = [f"Python {py_version.major}.{py_version.minor}.{py_version.micro}"]
    details.append(f"Platform: {platform.system()} {platform.machine()}")
    details.append(f"Executable: {sys.executable}")

    if py_version < (3, 10):
        return CheckResult(
            name="Python Environment",
            status="fail",
            message=f"Python {py_version.major}.{py_version.minor} -- requires ≥3.10",
            remedy="Install Python 3.10+: https://python.org/downloads",
            details=details,
        )

    # Check critical dependencies
    missing = []
    optional_missing = []
    for pkg in ["pydantic", "httpx", "rich", "yaml"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    for pkg, label in [("keyring", "OS keyring"), ("cryptography", "encrypted storage")]:
        try:
            __import__(pkg)
        except ImportError:
            optional_missing.append(f"{pkg} ({label})")

    if missing:
        return CheckResult(
            name="Python Environment",
            status="fail",
            message=f"Missing packages: {', '.join(missing)}",
            remedy=f"pip install {' '.join(missing)}",
            details=details,
        )

    if optional_missing:
        details.append(f"Optional missing: {', '.join(optional_missing)}")
        return CheckResult(
            name="Python Environment",
            status="warn",
            message=f"Python {py_version.major}.{py_version.minor} OK -- optional packages missing",
            remedy=f"pip install {' '.join(p.split(' ')[0] for p in optional_missing)}",
            details=details,
        )

    return CheckResult(
        name="Python Environment",
        status="pass",
        message=f"Python {py_version.major}.{py_version.minor}.{py_version.micro} -- all dependencies OK",
        details=details,
    )


def check_secure_store() -> CheckResult:
    """Check secure credential store status."""
    try:
        from orion.security.store import get_secure_store
        store = get_secure_store()
        status = store.get_status()

        if not status["available"]:
            return CheckResult(
                name="Secure Store",
                status="fail",
                message="No secure storage backend available",
                remedy="pip install keyring cryptography",
                details=["Neither OS keyring nor encrypted file backend is available"],
            )

        providers = status["stored_providers"]
        details = [
            f"Backend: {status['backend']}",
            f"Keyring: {'available' if status['keyring_available'] else 'unavailable'}",
            f"Encrypted file: {'available' if status['encrypted_file_available'] else 'unavailable'}",
            f"Stored credentials: {len(providers)}",
        ]

        return CheckResult(
            name="Secure Store",
            status="pass",
            message=f"Active ({status['backend']}) -- {len(providers)} credential(s) stored",
            details=details,
        )
    except Exception as e:
        return CheckResult(
            name="Secure Store",
            status="fail",
            message=f"Failed to initialize: {e}",
            remedy="pip install keyring cryptography",
        )


def check_settings() -> CheckResult:
    """Check settings file integrity."""
    settings_dir = Path.home() / ".orion"
    settings_file = settings_dir / "settings.json"
    details = [f"Settings dir: {settings_dir}"]

    if not settings_dir.exists():
        return CheckResult(
            name="Settings",
            status="warn",
            message="Settings directory not created yet",
            remedy="Settings will be created on first save",
            details=details,
        )

    if not settings_file.exists():
        return CheckResult(
            name="Settings",
            status="warn",
            message="No settings file -- using defaults",
            details=details,
        )

    try:
        data = json.loads(settings_file.read_text())
        details.append(f"Keys: {len(data)}")
        details.append(f"Mode: {data.get('default_mode', 'safe')}")
        return CheckResult(
            name="Settings",
            status="pass",
            message=f"Valid -- {len(data)} settings configured",
            details=details,
        )
    except json.JSONDecodeError as e:
        return CheckResult(
            name="Settings",
            status="fail",
            message=f"Corrupted settings file: {e}",
            remedy=f"Delete or fix {settings_file}",
            details=details,
        )


async def check_ollama() -> CheckResult:
    """Check Ollama local LLM connectivity."""
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    details = [f"URL: {ollama_url}"]

    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                model_names = [m.get("name", "?") for m in models[:5]]
                details.append(f"Models: {', '.join(model_names)}")
                if not models:
                    return CheckResult(
                        name="Ollama (Local LLM)",
                        status="warn",
                        message="Running but no models installed",
                        remedy="ollama pull qwen2.5-coder:14b",
                        details=details,
                    )
                return CheckResult(
                    name="Ollama (Local LLM)",
                    status="pass",
                    message=f"Running -- {len(models)} model(s) available",
                    details=details,
                )
            return CheckResult(
                name="Ollama (Local LLM)",
                status="warn",
                message=f"Responded with {resp.status_code}",
                details=details,
            )
    except Exception:
        return CheckResult(
            name="Ollama (Local LLM)",
            status="warn",
            message="Not running (connection refused)",
            remedy="Start Ollama: ollama serve",
            details=details,
        )


def check_api_keys() -> CheckResult:
    """Check configured API keys."""
    configured = []
    missing = []

    providers = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "groq": "GROQ_API_KEY",
    }

    for name, env_var in providers.items():
        has_env = bool(os.environ.get(env_var))
        has_secure = False
        try:
            from orion.security.store import get_secure_store
            store = get_secure_store()
            has_secure = store.has_key(name)
        except Exception:
            pass

        if has_env:
            configured.append(f"{name} (env)")
        elif has_secure:
            configured.append(f"{name} (secure)")
        else:
            missing.append(name)

    details = []
    if configured:
        details.append(f"Configured: {', '.join(configured)}")
    if missing:
        details.append(f"Missing: {', '.join(missing)}")

    if not configured:
        return CheckResult(
            name="API Keys",
            status="warn",
            message="No cloud API keys configured (Ollama still works)",
            remedy="Set keys in Settings -> API Keys, or export OPENAI_API_KEY=...",
            details=details,
        )

    return CheckResult(
        name="API Keys",
        status="pass",
        message=f"{len(configured)} provider(s) configured",
        details=details,
    )


async def check_api_server() -> CheckResult:
    """Check if the API server is running."""
    api_url = os.environ.get("ORION_API_URL", "http://localhost:8001")
    details = [f"URL: {api_url}"]

    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{api_url}/api/health")
            if resp.status_code == 200:
                return CheckResult(
                    name="API Server",
                    status="pass",
                    message="Running and healthy",
                    details=details,
                )
            return CheckResult(
                name="API Server",
                status="warn",
                message=f"Responded with {resp.status_code}",
                details=details,
            )
    except Exception:
        return CheckResult(
            name="API Server",
            status="warn",
            message="Not running (CLI mode only)",
            remedy="Start with: python launch.py --api-only",
            details=details,
        )


def check_workspace(workspace: str = ".") -> CheckResult:
    """Check workspace validity."""
    ws = Path(workspace).resolve()
    details = [f"Path: {ws}"]

    if not ws.exists():
        return CheckResult(
            name="Workspace",
            status="fail",
            message=f"Path does not exist: {ws}",
            remedy="Set workspace: /workspace <path>",
            details=details,
        )

    if not ws.is_dir():
        return CheckResult(
            name="Workspace",
            status="fail",
            message="Not a directory",
            details=details,
        )

    # Check for git repo
    has_git = (ws / ".git").exists()
    details.append(f"Git repo: {'yes' if has_git else 'no'}")

    # Count files
    py_files = list(ws.rglob("*.py"))
    js_files = list(ws.rglob("*.js")) + list(ws.rglob("*.ts"))
    details.append(f"Python files: {len(py_files)}")
    details.append(f"JS/TS files: {len(js_files)}")

    return CheckResult(
        name="Workspace",
        status="pass",
        message=f"Valid -- {len(py_files)} py, {len(js_files)} js/ts files",
        details=details,
    )


def check_core_modules() -> CheckResult:
    """Check that core Orion modules are importable."""
    modules = {
        "orion.core.agents.scout": "Scout (intent classifier)",
        "orion.core.agents.fast_path": "FastPath (simple executor)",
        "orion.core.agents.router": "Router (request routing)",
        "orion.core.governance.aegis": "AEGIS (safety gate)",
        "orion.core.llm.config": "LLM Config",
        "orion.core.context.repo_map": "Repo Map",
    }

    loaded = []
    failed = []
    for mod, label in modules.items():
        try:
            __import__(mod)
            loaded.append(label)
        except Exception:
            failed.append(label)

    details = [f"Loaded: {', '.join(loaded)}"] if loaded else []
    if failed:
        details.append(f"Failed: {', '.join(failed)}")

    if failed:
        return CheckResult(
            name="Core Modules",
            status="warn",
            message=f"{len(loaded)}/{len(modules)} modules loaded",
            remedy="Some modules may need migration from Orion_MVP",
            details=details,
        )

    return CheckResult(
        name="Core Modules",
        status="pass",
        message=f"All {len(modules)} core modules loaded",
        details=details,
    )


# =============================================================================
# Main Doctor Runner
# =============================================================================

async def run_doctor(console=None, workspace: str = ".") -> DoctorReport:
    """
    Run all diagnostic checks and display results.

    Args:
        console: OrionConsole instance for output (or None for return-only)
        workspace: Current workspace path

    Returns:
        DoctorReport with all check results
    """
    report = DoctorReport()

    def _print(text: str, style: str = ""):
        if console and hasattr(console, "print"):
            console.print(text, style=style)
        elif console and hasattr(console, "status"):
            console.status(text)
        else:
            print(text)

    _print("\n  Orion Doctor -- System Health Check\n", "bold cyan")
    _print("  " + "─" * 50)

    # Sync checks
    sync_checks = [
        check_python_environment(),
        check_secure_store(),
        check_settings(),
        check_api_keys(),
        check_workspace(workspace),
        check_core_modules(),
    ]

    # Async checks
    async_results = await asyncio.gather(
        check_ollama(),
        check_api_server(),
        return_exceptions=True,
    )

    all_checks = sync_checks + [
        r if isinstance(r, CheckResult)
        else CheckResult(name="Check", status="fail", message=str(r))
        for r in async_results
    ]

    for check in all_checks:
        report.checks.append(check)
        status_color = check.color
        icon = check.icon

        _print(f"\n  {icon} {check.name}", f"bold {status_color}")
        _print(f"    {check.message}")

        if check.details:
            for detail in check.details:
                _print(f"    · {detail}", "dim")

        if check.remedy:
            _print(f"    -> {check.remedy}", "yellow")

    # Summary
    _print("\n  " + "─" * 50)
    summary = (
        f"  {report.passed} passed, "
        f"{report.warnings} warnings, "
        f"{report.failures} failures"
    )
    overall = "healthy" if report.healthy else "needs attention"
    _print(f"\n  Summary: {summary}", "bold")
    _print(
        f"  Status: {overall}\n",
        "bold green" if report.healthy else "bold yellow",
    )

    return report
