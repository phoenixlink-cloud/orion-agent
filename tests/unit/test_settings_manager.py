"""
Tests for orion.cli.settings_manager -- CLI /settings module.
"""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_console():
    console = MagicMock()
    console.print = MagicMock()
    console.status = MagicMock()
    return console


@pytest.fixture
def settings_file(tmp_path):
    """Create a temporary settings file."""
    settings_dir = tmp_path / ".orion"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "default_mode": "pro",
                "enable_streaming": False,
                "command_timeout_seconds": 60,
            }
        )
    )
    return settings_file


class TestSettingCategories:
    def test_categories_defined(self):
        from orion.cli.settings_manager import SETTING_CATEGORIES

        assert "Governance" in SETTING_CATEGORIES
        assert "Core Features" in SETTING_CATEGORIES
        assert "Command Execution" in SETTING_CATEGORIES
        assert "Models" in SETTING_CATEGORIES

    def test_each_setting_has_required_fields(self):
        from orion.cli.settings_manager import SETTING_CATEGORIES

        for _category, settings in SETTING_CATEGORIES.items():
            for key, meta in settings.items():
                assert "label" in meta, f"{key} missing label"
                assert "type" in meta, f"{key} missing type"
                assert "default" in meta, f"{key} missing default"
                assert "description" in meta, f"{key} missing description"


class TestLoadSettings:
    def test_load_defaults_when_no_file(self, tmp_path):
        with patch("orion.cli.settings_manager.SETTINGS_FILE", tmp_path / "nonexistent.json"):
            from orion.cli.settings_manager import _load_settings

            settings = _load_settings()
            assert settings["default_mode"] == "safe"
            assert settings["enable_streaming"] is True

    def test_load_merges_with_defaults(self, settings_file):
        with patch("orion.cli.settings_manager.SETTINGS_FILE", settings_file):
            from orion.cli.settings_manager import _load_settings

            settings = _load_settings()
            assert settings["default_mode"] == "pro"  # User override
            assert settings["enable_streaming"] is False  # User override
            assert settings["enable_table_of_three"] is True  # Default


class TestSaveSettings:
    def test_save_creates_file(self, tmp_path):
        settings_dir = tmp_path / ".orion"
        settings_file = settings_dir / "settings.json"
        with patch("orion.cli.settings_manager.SETTINGS_DIR", settings_dir):
            with patch("orion.cli.settings_manager.SETTINGS_FILE", settings_file):
                from orion.cli.settings_manager import _save_settings

                _save_settings({"default_mode": "project"})
                assert settings_file.exists()
                data = json.loads(settings_file.read_text())
                assert data["default_mode"] == "project"


class TestRunSettings:
    @pytest.mark.asyncio
    async def test_view_mode(self, mock_console, settings_file):
        with patch("orion.cli.settings_manager.SETTINGS_FILE", settings_file):
            from orion.cli.settings_manager import run_settings

            result = await run_settings(mock_console, "view")
            assert isinstance(result, dict)
            assert "default_mode" in result
            # Console should have been called
            assert mock_console.print.called

    @pytest.mark.asyncio
    async def test_reset_mode(self, mock_console, settings_file):
        with patch("orion.cli.settings_manager.SETTINGS_DIR", settings_file.parent):
            with patch("orion.cli.settings_manager.SETTINGS_FILE", settings_file):
                from orion.cli.settings_manager import run_settings

                result = await run_settings(mock_console, "reset")
                assert result["default_mode"] == "safe"

    @pytest.mark.asyncio
    async def test_export_mode(self, mock_console, settings_file):
        with patch("orion.cli.settings_manager.SETTINGS_DIR", settings_file.parent):
            with patch("orion.cli.settings_manager.SETTINGS_FILE", settings_file):
                from orion.cli.settings_manager import run_settings

                await run_settings(mock_console, "export")
                export_path = settings_file.parent / "settings_export.json"
                assert export_path.exists()


class TestFormatValue:
    def test_bool_formatting(self):
        from orion.cli.settings_manager import _format_value

        assert _format_value(True, {"type": "bool"}) == "enabled"
        assert _format_value(False, {"type": "bool"}) == "disabled"

    def test_int_formatting(self):
        from orion.cli.settings_manager import _format_value

        assert _format_value(30, {"type": "int", "label": "timeout"}) == "30"

    def test_large_int_formatting(self):
        from orion.cli.settings_manager import _format_value

        result = _format_value(100000, {"type": "int", "label": "Max File Size"})
        assert "KB" in result or "100" in result
