"""Tests for FaultRay APM anomaly detection engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.apm.anomaly import AnomalyEngine, DEFAULT_ALERT_RULES
from faultray.apm.models import AlertRule, AlertSeverity, HostMetrics


@pytest.fixture()
def engine() -> AnomalyEngine:
    return AnomalyEngine(rules=list(DEFAULT_ALERT_RULES), window_size=10, sigma_threshold=2.0)


# ---------------------------------------------------------------------------
# Threshold alerts
# ---------------------------------------------------------------------------


class TestThresholdAlerts:
    def test_high_cpu_fires_alert(self, engine: AnomalyEngine) -> None:
        hm = HostMetrics(cpu_percent=95.0)
        # No duration requirement at first — duration_seconds=60 means we need to breach for 60s
        # Simulate repeated checks
        alerts = engine.check_batch("a1", hm)
        # First check starts the timer but doesn't fire yet (duration=60s)
        assert len(alerts) == 0

    def test_no_duration_rule_fires_immediately(self, engine: AnomalyEngine) -> None:
        # high_disk has duration_seconds=0
        hm = HostMetrics(disk_percent=90.0)
        alerts = engine.check_batch("a1", hm)
        assert len(alerts) == 1
        assert alerts[0].rule_name == "high_disk"

    def test_no_alert_when_below_threshold(self, engine: AnomalyEngine) -> None:
        hm = HostMetrics(cpu_percent=50.0, memory_percent=40.0, disk_percent=30.0)
        alerts = engine.check_batch("a1", hm)
        assert len(alerts) == 0

    def test_alert_resolves_when_condition_clears(self, engine: AnomalyEngine) -> None:
        # Trigger disk alert
        hm_high = HostMetrics(disk_percent=90.0)
        engine.check_batch("a1", hm_high)
        assert ("a1", "high_disk") in engine._active_alerts

        # Resolve it
        hm_low = HostMetrics(disk_percent=50.0)
        engine.check_batch("a1", hm_low)
        assert ("a1", "high_disk") not in engine._active_alerts

    def test_no_duplicate_alerts(self, engine: AnomalyEngine) -> None:
        hm = HostMetrics(disk_percent=90.0)
        alerts1 = engine.check_batch("a1", hm)
        alerts2 = engine.check_batch("a1", hm)
        assert len(alerts1) == 1
        assert len(alerts2) == 0  # Already active, no duplicate

    def test_custom_rule(self, engine: AnomalyEngine) -> None:
        engine.add_rule(AlertRule(
            name="test_conns",
            metric_name="network_connections",
            condition="gt",
            threshold=100.0,
            duration_seconds=0,
            severity=AlertSeverity.WARNING,
        ))
        hm = HostMetrics(network_connections=150)
        alerts = engine.check_batch("a1", hm)
        rule_names = [a.rule_name for a in alerts]
        assert "test_conns" in rule_names


# ---------------------------------------------------------------------------
# Condition checker
# ---------------------------------------------------------------------------


class TestConditionChecker:
    def test_gt(self) -> None:
        assert AnomalyEngine._check_condition(10.0, "gt", 5.0) is True
        assert AnomalyEngine._check_condition(5.0, "gt", 10.0) is False

    def test_lt(self) -> None:
        assert AnomalyEngine._check_condition(3.0, "lt", 5.0) is True
        assert AnomalyEngine._check_condition(5.0, "lt", 3.0) is False

    def test_gte(self) -> None:
        assert AnomalyEngine._check_condition(5.0, "gte", 5.0) is True
        assert AnomalyEngine._check_condition(4.9, "gte", 5.0) is False

    def test_lte(self) -> None:
        assert AnomalyEngine._check_condition(5.0, "lte", 5.0) is True

    def test_eq(self) -> None:
        assert AnomalyEngine._check_condition(5.0, "eq", 5.0) is True
        assert AnomalyEngine._check_condition(5.1, "eq", 5.0) is False

    def test_unknown_condition(self) -> None:
        assert AnomalyEngine._check_condition(5.0, "invalid", 5.0) is False


# ---------------------------------------------------------------------------
# Statistical anomaly detection
# ---------------------------------------------------------------------------


class TestStatisticalAnomaly:
    def test_no_anomaly_with_stable_data(self, engine: AnomalyEngine) -> None:
        for v in [50.0, 51.0, 49.0, 50.5, 50.2, 49.8]:
            hm = HostMetrics(cpu_percent=v)
            engine.check_batch("a1", hm)

        results = engine.detect_anomalies("a1")
        cpu_result = next((r for r in results if r.metric_name == "cpu_percent"), None)
        assert cpu_result is not None
        assert cpu_result.is_anomaly is False

    def test_anomaly_with_spike(self, engine: AnomalyEngine) -> None:
        # Feed stable data then a spike
        for v in [50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0]:
            hm = HostMetrics(cpu_percent=v)
            engine.check_batch("a1", hm)

        # Inject a huge spike
        hm = HostMetrics(cpu_percent=99.0)
        engine.check_batch("a1", hm)

        results = engine.detect_anomalies("a1")
        cpu_result = next((r for r in results if r.metric_name == "cpu_percent"), None)
        assert cpu_result is not None
        assert cpu_result.is_anomaly is True
        assert cpu_result.deviation_sigma > 2.0

    def test_no_data_returns_empty(self, engine: AnomalyEngine) -> None:
        results = engine.detect_anomalies("nonexistent")
        assert results == []


# ---------------------------------------------------------------------------
# Trend detection
# ---------------------------------------------------------------------------


class TestTrendDetection:
    def test_increasing_trend(self) -> None:
        values = [10.0, 15.0, 20.0, 25.0, 30.0, 35.0]
        assert AnomalyEngine._detect_trend(values) == "increasing"

    def test_decreasing_trend(self) -> None:
        values = [35.0, 30.0, 25.0, 20.0, 15.0, 10.0]
        assert AnomalyEngine._detect_trend(values) == "decreasing"

    def test_stable_trend(self) -> None:
        values = [50.0, 50.1, 49.9, 50.0, 50.2, 49.8]
        assert AnomalyEngine._detect_trend(values) == "stable"

    def test_too_few_points(self) -> None:
        assert AnomalyEngine._detect_trend([10.0, 20.0]) == "stable"


# ---------------------------------------------------------------------------
# Rule management
# ---------------------------------------------------------------------------


class TestRuleManagement:
    def test_add_rule(self, engine: AnomalyEngine) -> None:
        initial = len(engine.rules)
        engine.add_rule(AlertRule(name="test", metric_name="x"))
        assert len(engine.rules) == initial + 1

    def test_remove_rule(self, engine: AnomalyEngine) -> None:
        engine.add_rule(AlertRule(name="removeme", metric_name="x"))
        assert engine.remove_rule("removeme") is True
        assert engine.remove_rule("nonexistent") is False

    def test_load_rules_from_nonexistent_file(self, engine: AnomalyEngine) -> None:
        count = engine.load_rules_from_file("/nonexistent/path.yaml")
        assert count == 0

    def test_load_rules_from_json(self, tmp_path: Path) -> None:
        import json

        rules_file = tmp_path / "rules.json"
        rules_file.write_text(json.dumps({
            "rules": [
                {"name": "test1", "metric_name": "cpu", "threshold": 80.0},
                {"name": "test2", "metric_name": "mem", "threshold": 90.0},
            ]
        }))

        engine = AnomalyEngine(rules=[])
        count = engine.load_rules_from_file(rules_file)
        assert count == 2
        assert len(engine.rules) == 2
