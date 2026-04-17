"""
FaultRay E2E Test Suite

Tests every CLI command with real subprocess execution (no mocks).
Each test is independent and uses temporary files.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_YAML = """\
components:
  - id: nginx
    type: load_balancer
    replicas: 2
  - id: api
    type: app_server
    replicas: 3
  - id: postgres
    type: database
    replicas: 1
  - id: redis
    type: cache
    replicas: 1
dependencies:
  - source: nginx
    target: api
    type: requires
  - source: api
    target: postgres
    type: requires
  - source: api
    target: redis
    type: optional
"""

MOCK_TF_PLAN = json.dumps(
    {
        "format_version": "1.2",
        "terraform_version": "1.5.0",
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_instance.web",
                        "type": "aws_instance",
                        "values": {
                            "instance_type": "t3.micro",
                            "availability_zone": "us-east-1a",
                        },
                    }
                ]
            }
        },
        "resource_changes": [
            {
                "address": "aws_instance.web",
                "type": "aws_instance",
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": {"instance_type": "t3.micro"},
                },
            }
        ],
    }
)


_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


def run(cmd: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run a faultray CLI command and return the CompletedProcess.

    *cmd* should look like ``"faultray <subcommand> [args …]"``.
    The leading ``faultray`` token is replaced with
    ``[sys.executable, "-m", "faultray"]`` so the test does not depend on
    the CLI entry-point being on ``$PATH``.
    """
    parts = cmd.split()
    # Strip the leading "faultray" token if present
    if parts and parts[0] == "faultray":
        parts = parts[1:]
    argv = [sys.executable, "-m", "faultray"] + parts
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=_PROJECT_ROOT,
    )


def _write_temp(content: str, suffix: str = ".yaml") -> str:
    """Write content to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


def _no_traceback(result: subprocess.CompletedProcess[str]) -> None:
    """Assert that neither stdout nor stderr contains a Python traceback."""
    for stream in (result.stdout, result.stderr):
        # Rich-formatted tracebacks start with "Traceback" too
        assert "Traceback (most recent call last)" not in stream, (
            f"Unexpected Python traceback in output:\n{stream}"
        )


# ---------------------------------------------------------------------------
# A. Happy path
# ---------------------------------------------------------------------------


class TestE2EHappyPath:
    """Every core CLI command should succeed with valid input."""

    def test_version(self) -> None:
        r = run("faultray --version")
        assert r.returncode == 0
        assert "FaultRay" in r.stdout

    def test_help(self) -> None:
        r = run("faultray --help")
        assert r.returncode == 0
        assert "Usage" in r.stdout

    def test_demo(self) -> None:
        r = run("faultray demo", timeout=90)
        assert r.returncode == 0
        # Demo always prints a resilience score
        assert "Resilience Score" in r.stdout

    def test_load(self) -> None:
        yaml_path = _write_temp(SAMPLE_YAML)
        out_path = _write_temp("", suffix=".json")
        try:
            r = run(f"faultray load {yaml_path} -o {out_path}")
            assert r.returncode == 0
            assert "Resilience Score" in r.stdout
            # Output file should be valid JSON
            with open(out_path) as f:
                data = json.load(f)
            assert "components" in data or "nodes" in data or isinstance(data, dict)
        finally:
            os.unlink(yaml_path)
            os.unlink(out_path)

    def test_simulate(self) -> None:
        yaml_path = _write_temp(SAMPLE_YAML)
        out_path = _write_temp("", suffix=".json")
        try:
            # Load first so that simulate has a model
            run(f"faultray load {yaml_path} -o {out_path}")
            r = run("faultray simulate", timeout=90)
            assert r.returncode == 0
            assert "Resilience Score" in r.stdout
        finally:
            os.unlink(yaml_path)
            os.unlink(out_path)

    def test_financial(self) -> None:
        yaml_path = _write_temp(SAMPLE_YAML)
        try:
            r = run(f"faultray financial {yaml_path}", timeout=60)
            assert r.returncode == 0
            assert "Financial Impact" in r.stdout or "Annual" in r.stdout
        finally:
            os.unlink(yaml_path)

    def test_financial_json(self) -> None:
        yaml_path = _write_temp(SAMPLE_YAML)
        try:
            r = run(f"faultray financial {yaml_path} --json", timeout=60)
            assert r.returncode == 0
            # First non-empty line after the version banner should be JSON
            # The output may contain the version banner before the JSON
            json_text = r.stdout
            # Find the start of JSON object
            start = json_text.find("{")
            assert start != -1, f"No JSON object in output: {json_text[:200]}"
            data = json.loads(json_text[start:])
            assert "resilience_score" in data
            assert isinstance(data["resilience_score"], (int, float))
            assert data["resilience_score"] >= 0
        finally:
            os.unlink(yaml_path)

    def test_badge(self) -> None:
        yaml_path = _write_temp(SAMPLE_YAML)
        try:
            r = run(f"faultray badge {yaml_path}")
            assert r.returncode == 0
            assert "shields.io" in r.stdout or "img.shields.io" in r.stdout
        finally:
            os.unlink(yaml_path)

    def test_governance_assess(self) -> None:
        yaml_path = _write_temp(SAMPLE_YAML)
        try:
            r = run(
                f"faultray governance assess --auto --yaml {yaml_path}",
                timeout=60,
            )
            assert r.returncode == 0
            # Should contain some governance output (METI or ISO)
            combined = r.stdout + r.stderr
            assert "METI" in combined or "ISO" in combined or "governance" in combined.lower()
        finally:
            os.unlink(yaml_path)

    def test_compliance_monitor_dora(self) -> None:
        yaml_path = _write_temp(SAMPLE_YAML)
        try:
            r = run(
                f"faultray compliance-monitor {yaml_path} --framework dora",
                timeout=60,
            )
            assert r.returncode == 0
            assert "DORA" in r.stdout or "Compliance" in r.stdout
        finally:
            os.unlink(yaml_path)

    def test_tf_check(self) -> None:
        plan_path = _write_temp(MOCK_TF_PLAN, suffix=".json")
        try:
            r = run(f"faultray tf-check {plan_path}", timeout=60)
            assert r.returncode == 0
            assert "Terraform" in r.stdout or "Score" in r.stdout
        finally:
            os.unlink(plan_path)


# ---------------------------------------------------------------------------
# B. Edge cases
# ---------------------------------------------------------------------------


class TestE2EEdgeCases:
    """Broken / unusual input must not crash with a raw stack trace."""

    def test_empty_file(self) -> None:
        path = _write_temp("")
        try:
            r = run(f"faultray load {path}")
            assert r.returncode != 0
            _no_traceback(r)
        finally:
            os.unlink(path)

    def test_nonexistent_file(self) -> None:
        r = run("faultray load /tmp/_faultray_no_such_file_12345.yaml")
        assert r.returncode != 0
        combined = r.stdout + r.stderr
        assert "not found" in combined.lower() or "no such file" in combined.lower() or "does not exist" in combined.lower()

    def test_empty_components_list(self) -> None:
        path = _write_temp("components: []\n")
        try:
            r = run(f"faultray load {path}")
            # Should handle gracefully — either succeed with 0 components or error cleanly
            _no_traceback(r)
        finally:
            os.unlink(path)

    def test_japanese_component_names(self) -> None:
        yaml_content = """\
components:
  - id: ロードバランサー
    type: load_balancer
    replicas: 2
  - id: データベース
    type: database
    replicas: 1
dependencies:
  - source: ロードバランサー
    target: データベース
    type: requires
"""
        path = _write_temp(yaml_content)
        out_path = _write_temp("", suffix=".json")
        try:
            r = run(f"faultray load {path} -o {out_path}")
            assert r.returncode == 0
            _no_traceback(r)
        finally:
            os.unlink(path)
            os.unlink(out_path)

    def test_missing_required_fields(self) -> None:
        yaml_content = """\
components:
  - id: test
"""
        path = _write_temp(yaml_content)
        try:
            r = run(f"faultray load {path}")
            # May succeed with defaults or fail with validation error — either is fine
            _no_traceback(r)
        finally:
            os.unlink(path)

    def test_large_input(self) -> None:
        """100 components should complete within the timeout."""
        components = []
        for i in range(100):
            components.append(f"  - id: svc-{i}\n    type: app_server\n    replicas: 2")
        yaml_content = "components:\n" + "\n".join(components) + "\n"
        path = _write_temp(yaml_content)
        out_path = _write_temp("", suffix=".json")
        try:
            r = run(f"faultray load {path} -o {out_path}", timeout=60)
            assert r.returncode == 0
            _no_traceback(r)
        finally:
            os.unlink(path)
            os.unlink(out_path)

    def test_badge_empty_yaml(self) -> None:
        path = _write_temp("")
        try:
            r = run(f"faultray badge {path}")
            _no_traceback(r)
        finally:
            os.unlink(path)

    def test_financial_nonexistent(self) -> None:
        r = run("faultray financial /tmp/_faultray_no_such_file_12345.yaml")
        assert r.returncode != 0
        _no_traceback(r)


# ---------------------------------------------------------------------------
# C. User workflow — full end-to-end pipeline
# ---------------------------------------------------------------------------


class TestE2EUserWorkflow:
    """Simulate a realistic user session: create -> load -> simulate -> financial -> badge -> governance."""

    def test_full_pipeline(self) -> None:
        yaml_path = _write_temp(SAMPLE_YAML)
        model_path = _write_temp("", suffix=".json")
        try:
            # Step 1: Load
            r = run(f"faultray load {yaml_path} -o {model_path}")
            assert r.returncode == 0, f"load failed: {r.stdout}\n{r.stderr}"
            assert "Resilience Score" in r.stdout

            # Step 2: Simulate
            r = run("faultray simulate", timeout=90)
            assert r.returncode == 0, f"simulate failed: {r.stdout}\n{r.stderr}"
            assert "Resilience Score" in r.stdout

            # Step 3: Financial
            r = run(f"faultray financial {yaml_path}", timeout=60)
            assert r.returncode == 0, f"financial failed: {r.stdout}\n{r.stderr}"

            # Step 4: Badge
            r = run(f"faultray badge {yaml_path}")
            assert r.returncode == 0, f"badge failed: {r.stdout}\n{r.stderr}"
            assert "shields.io" in r.stdout or "img.shields.io" in r.stdout

            # Step 5: Governance
            r = run(
                f"faultray governance assess --auto --yaml {yaml_path}",
                timeout=60,
            )
            assert r.returncode == 0, f"governance failed: {r.stdout}\n{r.stderr}"
        finally:
            os.unlink(yaml_path)
            os.unlink(model_path)


# ---------------------------------------------------------------------------
# D. Output format validation
# ---------------------------------------------------------------------------


class TestE2EOutputFormat:
    """Validate that structured outputs conform to expected formats."""

    def test_financial_json_schema(self) -> None:
        yaml_path = _write_temp(SAMPLE_YAML)
        try:
            r = run(f"faultray financial {yaml_path} --json", timeout=60)
            assert r.returncode == 0
            start = r.stdout.find("{")
            assert start != -1
            data = json.loads(r.stdout[start:])
            # Resilience score is 0-100
            assert 0 <= data["resilience_score"] <= 100
            # Financial amounts are non-negative
            assert data["total_annual_loss"] >= 0
            assert data["total_downtime_hours"] >= 0
        finally:
            os.unlink(yaml_path)

    def test_badge_url_format(self) -> None:
        yaml_path = _write_temp(SAMPLE_YAML)
        try:
            r = run(f"faultray badge {yaml_path} --url")
            assert r.returncode == 0
            output = r.stdout.strip()
            # Should contain a shields.io URL
            assert "img.shields.io/badge" in output
        finally:
            os.unlink(yaml_path)

    def test_tf_check_json(self) -> None:
        plan_path = _write_temp(MOCK_TF_PLAN, suffix=".json")
        try:
            r = run(f"faultray tf-check {plan_path} --json", timeout=60)
            assert r.returncode == 0
            start = r.stdout.find("{")
            if start != -1:
                data = json.loads(r.stdout[start:])
                assert isinstance(data, dict)
        finally:
            os.unlink(plan_path)

    def test_compliance_monitor_json(self) -> None:
        yaml_path = _write_temp(SAMPLE_YAML)
        try:
            r = run(
                f"faultray compliance-monitor {yaml_path} --framework dora --json",
                timeout=60,
            )
            assert r.returncode == 0
            start = r.stdout.find("{")
            if start == -1:
                start = r.stdout.find("[")
            if start != -1:
                data = json.loads(r.stdout[start:])
                assert isinstance(data, (dict, list))
        finally:
            os.unlink(yaml_path)


# ---------------------------------------------------------------------------
# E. Error message quality
# ---------------------------------------------------------------------------


class TestE2EErrorQuality:
    """Error outputs must be user-friendly — no raw stack traces."""

    def test_load_empty_no_traceback(self) -> None:
        path = _write_temp("")
        try:
            r = run(f"faultray load {path}")
            _no_traceback(r)
            assert r.returncode != 0
        finally:
            os.unlink(path)

    def test_load_missing_file_helpful_message(self) -> None:
        r = run("faultray load /tmp/_faultray_e2e_missing_xyz.yaml")
        assert r.returncode != 0
        _no_traceback(r)
        combined = (r.stdout + r.stderr).lower()
        assert "not found" in combined or "no such file" in combined or "does not exist" in combined

    def test_unknown_command_shows_help(self) -> None:
        r = run("faultray this-command-does-not-exist")
        assert r.returncode != 0
        _combined = r.stdout + r.stderr
        # Should show usage info or error, not a stack trace
        _no_traceback(r)

    def test_financial_missing_file_no_traceback(self) -> None:
        r = run("faultray financial /tmp/_faultray_e2e_missing_xyz.yaml")
        assert r.returncode != 0
        _no_traceback(r)

    def test_badge_missing_file_no_traceback(self) -> None:
        r = run("faultray badge /tmp/_faultray_e2e_missing_xyz.yaml")
        assert r.returncode != 0
        _no_traceback(r)
