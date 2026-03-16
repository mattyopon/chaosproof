"""Test that SDK quickstart example runs without errors."""
import subprocess
import sys


class TestSDKQuickstart:
    def test_quickstart_runs(self):
        result = subprocess.run(
            [sys.executable, "examples/sdk_quickstart.py"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"SDK quickstart failed:\n{result.stderr}"
        assert "All analyses complete" in result.stdout

    def test_quickstart_cost_output(self):
        result = subprocess.run(
            [sys.executable, "examples/sdk_quickstart.py"],
            capture_output=True, text=True, timeout=30,
        )
        assert "Cost Impact Analysis" in result.stdout
        assert "Total Cost: $" in result.stdout

    def test_quickstart_security_output(self):
        result = subprocess.run(
            [sys.executable, "examples/sdk_quickstart.py"],
            capture_output=True, text=True, timeout=30,
        )
        assert "Security Score:" in result.stdout
        assert "Grade:" in result.stdout

    def test_quickstart_compliance_output(self):
        result = subprocess.run(
            [sys.executable, "examples/sdk_quickstart.py"],
            capture_output=True, text=True, timeout=30,
        )
        assert "SOC 2 Score:" in result.stdout

    def test_quickstart_dr_output(self):
        result = subprocess.run(
            [sys.executable, "examples/sdk_quickstart.py"],
            capture_output=True, text=True, timeout=30,
        )
        assert "RTO:" in result.stdout
        assert "RPO:" in result.stdout

    def test_quickstart_prediction_output(self):
        result = subprocess.run(
            [sys.executable, "examples/sdk_quickstart.py"],
            capture_output=True, text=True, timeout=30,
        )
        assert "Failure Prediction" in result.stdout
        assert "Capacity Forecast" in result.stdout
