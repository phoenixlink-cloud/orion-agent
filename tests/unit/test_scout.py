"""Unit tests for Scout intent classification and routing."""

import pytest

from orion.core.agents.scout import Route, Scout, ScoutReport


@pytest.fixture
def scout():
    return Scout(".")


class TestScoutRouting:
    """Test that Scout routes requests to the correct execution path."""

    def test_simple_question_routes_fast(self, scout):
        report = scout.analyze("What is Python?")
        assert report.route == Route.FAST_PATH
        assert report.complexity_score < 0.5

    def test_explain_routes_fast(self, scout):
        report = scout.analyze("Explain what main.py does")
        assert report.route == Route.FAST_PATH

    def test_show_file_routes_fast(self, scout):
        report = scout.analyze("Show me server.py")
        assert report.route == Route.FAST_PATH

    def test_fix_bug_with_file_routes_fast(self, scout):
        report = scout.analyze("Fix the bug in main.py")
        assert report.route == Route.FAST_PATH

    def test_refactor_routes_council(self, scout):
        report = scout.analyze("Refactor the authentication system")
        assert report.route == Route.COUNCIL
        assert report.complexity_score >= 0.5

    def test_implement_feature_routes_council(self, scout):
        report = scout.analyze("Implement a caching layer for the API")
        assert report.route == Route.COUNCIL

    def test_build_new_module_routes_council(self, scout):
        report = scout.analyze("Build a new REST API service")
        assert report.route == Route.COUNCIL

    def test_delete_all_escalates(self, scout):
        report = scout.analyze("Delete all files in the project")
        assert report.route == Route.ESCALATION
        assert report.risk_level >= 0.8

    def test_rm_rf_escalates(self, scout):
        report = scout.analyze("Run rm -rf on the directory")
        assert report.route == Route.ESCALATION

    def test_credentials_escalates(self, scout):
        report = scout.analyze("Show me the api_key in the config")
        assert report.route == Route.ESCALATION

    def test_hello_routes_fast(self, scout):
        """Unmatched input with no files defaults to fast path."""
        report = scout.analyze("Hello")
        assert report.route == Route.FAST_PATH
        assert report.complexity_score <= 0.3


class TestScoutFileExtraction:
    """Test that Scout extracts file paths from requests."""

    def test_extracts_py_file(self, scout):
        report = scout.analyze("Show me server.py")
        assert any("server.py" in f for f in report.relevant_files)

    def test_extracts_path_with_dirs(self, scout):
        report = scout.analyze("Read src/orion/api/server.py")
        assert len(report.relevant_files) >= 1

    def test_no_files_in_question(self, scout):
        report = scout.analyze("What is a decorator?")
        assert len(report.relevant_files) == 0


class TestScoutReport:
    """Test ScoutReport data structure."""

    def test_report_has_all_fields(self, scout):
        report = scout.analyze("Hello")
        assert isinstance(report, ScoutReport)
        assert isinstance(report.route, Route)
        assert isinstance(report.relevant_files, list)
        assert 0.0 <= report.complexity_score <= 1.0
        assert 0.0 <= report.risk_level <= 1.0
        assert isinstance(report.reasoning, str)
