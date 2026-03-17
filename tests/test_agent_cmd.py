"""Tests for the 'faultray agent' CLI command group."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from faultray.cli import app

runner = CliRunner()

EXAMPLE_YAML = Path(__file__).resolve().parent.parent / "examples" / "ai-agent-workflow.yaml"


# ---------------------------------------------------------------------------
# 1. The agent command group exists
# ---------------------------------------------------------------------------

def test_agent_command_group_exists() -> None:
    result = runner.invoke(app, ["agent", "--help"])
    assert result.exit_code == 0
    assert "agent" in result.output.lower()


# ---------------------------------------------------------------------------
# 2. assess command with the example YAML
# ---------------------------------------------------------------------------

def test_assess_command(tmp_path: Path) -> None:
    if not EXAMPLE_YAML.exists():
        pytest.skip("Example YAML not found")
    result = runner.invoke(app, ["agent", "assess", str(EXAMPLE_YAML)])
    assert result.exit_code == 0


def test_assess_command_json(tmp_path: Path) -> None:
    if not EXAMPLE_YAML.exists():
        pytest.skip("Example YAML not found")
    result = runner.invoke(app, ["agent", "assess", str(EXAMPLE_YAML), "--json"])
    assert result.exit_code == 0
    # JSON output should be parseable
    output = result.output.strip()
    if output:
        parsed = json.loads(output)
        assert isinstance(parsed, list)


# ---------------------------------------------------------------------------
# 3. monitor command with the example YAML
# ---------------------------------------------------------------------------

def test_monitor_command() -> None:
    if not EXAMPLE_YAML.exists():
        pytest.skip("Example YAML not found")
    result = runner.invoke(app, ["agent", "monitor", str(EXAMPLE_YAML)])
    assert result.exit_code == 0


def test_monitor_command_json() -> None:
    if not EXAMPLE_YAML.exists():
        pytest.skip("Example YAML not found")
    result = runner.invoke(app, ["agent", "monitor", str(EXAMPLE_YAML), "--json"])
    assert result.exit_code == 0
    output = result.output.strip()
    if output:
        parsed = json.loads(output)
        assert isinstance(parsed, dict)
        assert "rules" in parsed


# ---------------------------------------------------------------------------
# 4. scenarios command with the example YAML
# ---------------------------------------------------------------------------

def test_scenarios_command() -> None:
    if not EXAMPLE_YAML.exists():
        pytest.skip("Example YAML not found")
    result = runner.invoke(app, ["agent", "scenarios", str(EXAMPLE_YAML)])
    assert result.exit_code == 0


def test_scenarios_command_json() -> None:
    if not EXAMPLE_YAML.exists():
        pytest.skip("Example YAML not found")
    result = runner.invoke(app, ["agent", "scenarios", str(EXAMPLE_YAML), "--json"])
    assert result.exit_code == 0
    output = result.output.strip()
    if output:
        parsed = json.loads(output)
        assert isinstance(parsed, list)


# ---------------------------------------------------------------------------
# 5. --json output format for each command (covered above, additional checks)
# ---------------------------------------------------------------------------

def test_assess_json_structure() -> None:
    if not EXAMPLE_YAML.exists():
        pytest.skip("Example YAML not found")
    result = runner.invoke(app, ["agent", "assess", str(EXAMPLE_YAML), "--json"])
    assert result.exit_code == 0
    output = result.output.strip()
    if output:
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        if parsed:
            report = parsed[0]
            assert "agent_id" in report
            assert "risk_score" in report
            assert "risk_level" in report


def test_monitor_json_structure() -> None:
    if not EXAMPLE_YAML.exists():
        pytest.skip("Example YAML not found")
    result = runner.invoke(app, ["agent", "monitor", str(EXAMPLE_YAML), "--json"])
    assert result.exit_code == 0
    output = result.output.strip()
    if output:
        parsed = json.loads(output)
        assert "total_components_monitored" in parsed
        assert "coverage_percent" in parsed


def test_scenarios_json_structure() -> None:
    if not EXAMPLE_YAML.exists():
        pytest.skip("Example YAML not found")
    result = runner.invoke(app, ["agent", "scenarios", str(EXAMPLE_YAML), "--json"])
    assert result.exit_code == 0
    output = result.output.strip()
    if output:
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        if parsed:
            scenario = parsed[0]
            assert "id" in scenario
            assert "name" in scenario
            assert "faults" in scenario


# ---------------------------------------------------------------------------
# 6. Error handling for missing file
# ---------------------------------------------------------------------------

def test_assess_missing_file() -> None:
    result = runner.invoke(app, ["agent", "assess", "/nonexistent/file.yaml"])
    assert result.exit_code == 1


def test_monitor_missing_file() -> None:
    result = runner.invoke(app, ["agent", "monitor", "/nonexistent/file.yaml"])
    assert result.exit_code == 1


def test_scenarios_missing_file() -> None:
    result = runner.invoke(app, ["agent", "scenarios", "/nonexistent/file.yaml"])
    assert result.exit_code == 1
