"""
Tests for orion.cli.doctor — /doctor diagnostic module.

Tests individual health checks and the full doctor report.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.fixture
def mock_console():
    """Create a mock console for capturing output."""
    console = MagicMock()
    console.print = MagicMock()
    console.status = MagicMock()
    return console


class TestCheckPythonEnvironment:
    def test_returns_pass_on_valid_python(self):
        from orion.cli.doctor import check_python_environment
        result = check_python_environment()
        assert result.status in ("pass", "warn")
        assert "Python" in result.message

    def test_result_has_details(self):
        from orion.cli.doctor import check_python_environment
        result = check_python_environment()
        assert len(result.details) >= 1


class TestCheckSecureStore:
    def test_returns_check_result(self):
        from orion.cli.doctor import check_secure_store
        result = check_secure_store()
        assert result.name == "Secure Store"
        assert result.status in ("pass", "warn", "fail")


class TestCheckSettings:
    def test_returns_check_result(self):
        from orion.cli.doctor import check_settings
        result = check_settings()
        assert result.name == "Settings"
        assert result.status in ("pass", "warn", "fail")


class TestCheckApiKeys:
    def test_returns_check_result(self):
        from orion.cli.doctor import check_api_keys
        result = check_api_keys()
        assert result.name == "API Keys"
        assert result.status in ("pass", "warn")


class TestCheckOllama:
    @pytest.mark.asyncio
    async def test_returns_check_result(self):
        from orion.cli.doctor import check_ollama
        result = await check_ollama()
        assert result.name == "Ollama (Local LLM)"
        assert result.status in ("pass", "warn", "fail")


class TestCheckApiServer:
    @pytest.mark.asyncio
    async def test_returns_check_result(self):
        from orion.cli.doctor import check_api_server
        result = await check_api_server()
        assert result.name == "API Server"
        assert result.status in ("pass", "warn")


class TestCheckWorkspace:
    def test_valid_workspace(self, tmp_path):
        from orion.cli.doctor import check_workspace
        result = check_workspace(str(tmp_path))
        assert result.status == "pass"

    def test_invalid_workspace(self):
        from orion.cli.doctor import check_workspace
        result = check_workspace("/nonexistent/path/xyz123")
        assert result.status == "fail"


class TestCheckCoreModules:
    def test_returns_check_result(self):
        from orion.cli.doctor import check_core_modules
        result = check_core_modules()
        assert result.name == "Core Modules"
        assert result.status in ("pass", "warn")


class TestDoctorReport:
    def test_report_properties(self):
        from orion.cli.doctor import DoctorReport, CheckResult
        report = DoctorReport(checks=[
            CheckResult("A", "pass", "OK"),
            CheckResult("B", "warn", "Warning"),
            CheckResult("C", "fail", "Error"),
        ])
        assert report.passed == 1
        assert report.warnings == 1
        assert report.failures == 1
        assert report.total == 3
        assert report.healthy is False

    def test_healthy_report(self):
        from orion.cli.doctor import DoctorReport, CheckResult
        report = DoctorReport(checks=[
            CheckResult("A", "pass", "OK"),
            CheckResult("B", "pass", "OK"),
        ])
        assert report.healthy is True


class TestRunDoctor:
    @pytest.mark.asyncio
    async def test_run_doctor_returns_report(self, mock_console, tmp_path):
        from orion.cli.doctor import run_doctor
        report = await run_doctor(console=mock_console, workspace=str(tmp_path))
        assert report.total >= 6  # At least 6 checks
        assert all(c.name for c in report.checks)

    @pytest.mark.asyncio
    async def test_run_doctor_without_console(self, tmp_path):
        from orion.cli.doctor import run_doctor
        report = await run_doctor(console=None, workspace=str(tmp_path))
        assert report.total >= 6


class TestCheckResultFormatting:
    def test_icon_mapping(self):
        from orion.cli.doctor import CheckResult
        assert CheckResult("", "pass", "").icon == "✓"
        assert CheckResult("", "warn", "").icon == "⚠"
        assert CheckResult("", "fail", "").icon == "✗"

    def test_color_mapping(self):
        from orion.cli.doctor import CheckResult
        assert CheckResult("", "pass", "").color == "green"
        assert CheckResult("", "warn", "").color == "yellow"
        assert CheckResult("", "fail", "").color == "red"
