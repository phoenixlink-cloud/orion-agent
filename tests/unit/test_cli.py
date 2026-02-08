"""Tests for orion.cli — commands and REPL."""

import os
import pytest
from unittest.mock import MagicMock, patch

from orion.cli.commands import (
    handle_command,
    _handle_workspace,
    _handle_add,
    _handle_drop,
    _handle_mode,
    _handle_diff,
    _handle_commit,
    _handle_map,
)


# =========================================================================
# FIXTURES
# =========================================================================

@pytest.fixture
def console():
    c = MagicMock()
    c.print_info = MagicMock()
    c.print_success = MagicMock()
    c.print_error = MagicMock()
    c.print_help = MagicMock()
    c.print_status = MagicMock()
    c._print = MagicMock()
    return c


# =========================================================================
# COMMAND DISPATCH
# =========================================================================

class TestHandleCommand:
    def test_quit(self, console):
        result = handle_command("/quit", console, None, "safe")
        assert result == "QUIT"

    def test_exit(self, console):
        result = handle_command("/exit", console, None, "safe")
        assert result == "QUIT"

    def test_help(self, console):
        result = handle_command("/help", console, None, "safe")
        assert result == {}
        console.print_help.assert_called_once()

    def test_status(self, console):
        result = handle_command("/status", console, "/tmp", "pro")
        assert result == {}
        console.print_status.assert_called_once_with("/tmp", "pro")

    def test_unknown_command(self, console):
        result = handle_command("/foobar", console, None, "safe")
        assert result == {}
        console.print_error.assert_called_once()


# =========================================================================
# WORKSPACE
# =========================================================================

class TestWorkspace:
    def test_no_workspace_set(self, console):
        result = _handle_workspace(["/workspace"], console, None)
        assert result == {}
        console.print_info.assert_called()

    def test_show_current_workspace(self, console):
        result = _handle_workspace(["/workspace"], console, "/some/path")
        assert result == {}
        assert "Current workspace" in str(console.print_info.call_args)

    def test_set_valid_workspace(self, console, tmp_path):
        result = _handle_workspace(["/workspace", str(tmp_path)], console, None)
        assert result.get("workspace") == str(tmp_path.resolve())

    def test_set_invalid_workspace(self, console, tmp_path):
        fake = str(tmp_path / "definitely_does_not_exist_xyz_12345")
        result = _handle_workspace(["/workspace", fake], console, None)
        assert result == {}
        console.print_error.assert_called()


# =========================================================================
# ADD / DROP
# =========================================================================

class TestAddDrop:
    def test_add_no_args_empty(self, console):
        result = _handle_add(["/add"], console, "/tmp", [])
        assert result == {}

    def test_add_no_workspace(self, console):
        result = _handle_add(["/add", "file.py"], console, None, [])
        assert result == {}
        console.print_error.assert_called()

    def test_drop_no_args(self, console):
        result = _handle_drop(["/drop"], console, [])
        assert result == {}

    def test_drop_all(self, console):
        files = ["a.py", "b.py"]
        result = _handle_drop(["/drop", "all"], console, files)
        assert len(files) == 0

    def test_drop_specific(self, console):
        files = ["a.py", "b.py"]
        result = _handle_drop(["/drop", "a.py"], console, files)
        assert "a.py" not in files

    def test_drop_not_found(self, console):
        files = ["a.py"]
        result = _handle_drop(["/drop", "z.py"], console, files)
        console.print_error.assert_called()


# =========================================================================
# MODE
# =========================================================================

class TestMode:
    def test_show_current_mode(self, console):
        result = _handle_mode(["/mode"], console, "safe")
        assert result == {}
        assert "SAFE" in str(console.print_info.call_args)

    def test_switch_to_pro(self, console):
        result = _handle_mode(["/mode", "pro"], console, "safe")
        assert result.get("mode") == "pro"

    def test_switch_to_project(self, console):
        result = _handle_mode(["/mode", "project"], console, "safe")
        assert result.get("mode") == "project"

    def test_invalid_mode(self, console):
        result = _handle_mode(["/mode", "hacker"], console, "safe")
        assert result == {}
        console.print_error.assert_called()


# =========================================================================
# CLEAR
# =========================================================================

class TestClear:
    def test_clear(self, console):
        files = ["a.py", "b.py"]
        result = handle_command("/clear", console, None, "safe", files)
        assert len(files) == 0
        assert result.get("context_files") == []
