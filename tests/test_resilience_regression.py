"""Tests for resilience regression detector."""

from __future__ import annotations

import pytest

from infrasim.model.components import Component, ComponentType, Dependency, HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.resilience_regression import (
    CheckOutcome,
    CheckResult,
    InfraSnapshot,
    RegressionCheck,
    RegressionReport,
    RegressionSeverity,
    ResilientRegressionDetector,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
    encryption_rest: bool = False,
    encryption_transit: bool = False,
    log_enabled: bool = False,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover.enabled = True
    c.security.encryption_at_rest = encryption_rest
    c.security.encryption_in_transit = encryption_transit
    c.security.log_enabled = log_enabled
    return c


def _baseline_graph() -> InfraGraph:
    g = InfraGraph()
    g.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api", "API Server", replicas=2, failover=True))
    g.add_component(
        _comp("db", "Database", ComponentType.DATABASE, replicas=3, failover=True,
              encryption_rest=True, encryption_transit=True, log_enabled=True)
    )
    g.add_component(_comp("cache", "Cache", ComponentType.CACHE, replicas=2))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    g.add_dependency(Dependency(source_id="api", target_id="cache"))
    return g


def _degraded_graph() -> InfraGraph:
    """Graph with worse resilience than baseline."""
    g = InfraGraph()
    g.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER, replicas=1))
    g.add_component(_comp("api", "API Server", replicas=1))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE, replicas=1))
    g.add_component(_comp("cache", "Cache", ComponentType.CACHE, replicas=1))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    g.add_dependency(Dependency(source_id="api", target_id="cache"))
    return g


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_severity_values(self):
        assert RegressionSeverity.CRITICAL.value == "critical"
        assert RegressionSeverity.WARNING.value == "warning"
        assert RegressionSeverity.INFO.value == "info"

    def test_check_result_values(self):
        assert CheckResult.PASS.value == "pass"
        assert CheckResult.FAIL.value == "fail"
        assert CheckResult.WARN.value == "warn"
        assert CheckResult.SKIP.value == "skip"


# ---------------------------------------------------------------------------
# Tests: InfraSnapshot
# ---------------------------------------------------------------------------


class TestSnapshot:
    def test_snapshot_from_graph(self):
        detector = ResilientRegressionDetector()
        g = _baseline_graph()
        snap = detector.snapshot(g)
        assert snap.component_count == 4
        assert snap.resilience_score > 0

    def test_snapshot_empty_graph(self):
        detector = ResilientRegressionDetector()
        g = InfraGraph()
        snap = detector.snapshot(g)
        assert snap.component_count == 0
        assert snap.resilience_score == 100.0
        assert snap.spof_count == 0
        assert snap.failover_coverage == 100.0

    def test_snapshot_spof_detection(self):
        detector = ResilientRegressionDetector()
        g = InfraGraph()
        api = _comp("api", "API", replicas=1)
        db = _comp("db", "DB", ComponentType.DATABASE, replicas=1)
        g.add_component(api)
        g.add_component(db)
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        snap = detector.snapshot(g)
        # db has 1 replica and has dependents (api depends on it)
        assert snap.spof_count >= 1
        assert "DB" in snap.single_points_of_failure

    def test_snapshot_avg_replicas(self):
        detector = ResilientRegressionDetector()
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=2))
        g.add_component(_comp("b", "B", replicas=4))
        snap = detector.snapshot(g)
        assert snap.avg_replicas == 3.0

    def test_snapshot_encryption_coverage(self):
        detector = ResilientRegressionDetector()
        g = InfraGraph()
        g.add_component(_comp("a", "A", encryption_rest=True))
        g.add_component(_comp("b", "B"))
        snap = detector.snapshot(g)
        assert snap.encryption_coverage == 50.0

    def test_snapshot_monitoring_coverage(self):
        detector = ResilientRegressionDetector()
        g = InfraGraph()
        g.add_component(_comp("a", "A", log_enabled=True))
        g.add_component(_comp("b", "B", log_enabled=True))
        g.add_component(_comp("c", "C"))
        snap = detector.snapshot(g)
        assert abs(snap.monitoring_coverage - 66.7) < 0.1

    def test_snapshot_external_dependency_count(self):
        detector = ResilientRegressionDetector()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        g.add_component(_comp("ext1", "Stripe", ComponentType.EXTERNAL_API))
        g.add_component(_comp("ext2", "Twilio", ComponentType.EXTERNAL_API))
        snap = detector.snapshot(g)
        assert snap.external_dependency_count == 2

    def test_snapshot_failover_coverage(self):
        detector = ResilientRegressionDetector()
        g = InfraGraph()
        g.add_component(_comp("api", "API", failover=True))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, failover=False))
        snap = detector.snapshot(g)
        assert snap.failover_coverage == 50.0

    def test_snapshot_max_dependency_depth(self):
        detector = ResilientRegressionDetector()
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        snap = detector.snapshot(g)
        assert snap.max_dependency_depth >= 2


# ---------------------------------------------------------------------------
# Tests: Compare
# ---------------------------------------------------------------------------


class TestCompare:
    def test_no_regression(self):
        detector = ResilientRegressionDetector()
        snap = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(snap, snap)
        assert report.overall_result == CheckResult.PASS
        assert report.exit_code == 0
        assert report.failed_count == 0

    def test_critical_regression(self):
        detector = ResilientRegressionDetector()
        baseline = InfraSnapshot(
            resilience_score=90.0, component_count=4, spof_count=0,
            avg_replicas=3.0, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        current = InfraSnapshot(
            resilience_score=50.0, component_count=4, spof_count=3,
            avg_replicas=1.0, max_dependency_depth=5, failover_coverage=30.0,
            encryption_coverage=50.0, monitoring_coverage=50.0,
            avg_utilization=90.0, single_points_of_failure=["A", "B", "C"],
            external_dependency_count=1,
        )
        report = detector.compare(baseline, current)
        assert report.overall_result == CheckResult.FAIL
        assert report.exit_code == 1
        assert report.failed_count > 0

    def test_warning_regression(self):
        detector = ResilientRegressionDetector()
        baseline = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=3.0, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        # Only avg_replicas drops (WARNING severity) — no CRITICAL regression
        current = InfraSnapshot(
            resilience_score=84.0, component_count=4, spof_count=0,
            avg_replicas=2.0, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(baseline, current)
        assert report.overall_result in (CheckResult.WARN, CheckResult.PASS)
        assert report.exit_code in (0, 2)

    def test_improvement_detected(self):
        detector = ResilientRegressionDetector()
        baseline = InfraSnapshot(
            resilience_score=50.0, component_count=4, spof_count=3,
            avg_replicas=1.0, max_dependency_depth=5, failover_coverage=30.0,
            encryption_coverage=30.0, monitoring_coverage=30.0,
            avg_utilization=90.0, single_points_of_failure=["A", "B", "C"],
            external_dependency_count=1,
        )
        current = InfraSnapshot(
            resilience_score=90.0, component_count=4, spof_count=0,
            avg_replicas=3.0, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(baseline, current)
        assert report.overall_result == CheckResult.PASS
        assert report.exit_code == 0

    def test_report_counts(self):
        detector = ResilientRegressionDetector()
        snap = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(snap, snap)
        total = report.passed_count + report.failed_count + report.warned_count + report.skipped_count
        assert total == len(report.outcomes)

    def test_report_summary_string(self):
        detector = ResilientRegressionDetector()
        snap = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(snap, snap)
        assert "passed" in report.summary


# ---------------------------------------------------------------------------
# Tests: check_graph
# ---------------------------------------------------------------------------


class TestCheckGraph:
    def test_check_graph_same(self):
        detector = ResilientRegressionDetector()
        g = _baseline_graph()
        report = detector.check_graph(g, g)
        assert report.overall_result == CheckResult.PASS

    def test_check_graph_regression(self):
        detector = ResilientRegressionDetector()
        baseline = _baseline_graph()
        degraded = _degraded_graph()
        report = detector.check_graph(baseline, degraded)
        # Degraded graph has fewer replicas, no failover, no encryption, no monitoring
        assert report.failed_count > 0 or report.warned_count > 0

    def test_check_graph_empty_baseline(self):
        detector = ResilientRegressionDetector()
        g1 = InfraGraph()
        g2 = _baseline_graph()
        report = detector.check_graph(g1, g2)
        # Empty baseline → current is same or improved
        assert report.exit_code in (0, 2)


# ---------------------------------------------------------------------------
# Tests: Custom checks
# ---------------------------------------------------------------------------


class TestCustomChecks:
    def test_add_custom_check(self):
        detector = ResilientRegressionDetector()
        custom = RegressionCheck(
            id="custom-ext-deps",
            name="External Dependencies",
            description="External API count must not increase",
            severity=RegressionSeverity.WARNING,
            metric="external_dependency_count",
            direction="lower_is_better",
            threshold_percent=0.0,
        )
        detector.add_check(custom)
        checks = detector.get_checks()
        assert any(c.id == "custom-ext-deps" for c in checks)

    def test_custom_check_triggered(self):
        detector = ResilientRegressionDetector(checks=[])
        detector.add_check(RegressionCheck(
            id="ext-deps",
            name="Ext Deps",
            description="No new external deps",
            severity=RegressionSeverity.CRITICAL,
            metric="external_dependency_count",
            direction="lower_is_better",
            threshold_percent=0.0,
        ))
        baseline = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        current = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=5,
        )
        report = detector.compare(baseline, current)
        assert report.overall_result == CheckResult.FAIL

    def test_get_checks_returns_copy(self):
        detector = ResilientRegressionDetector()
        checks = detector.get_checks()
        original_len = len(checks)
        checks.append(RegressionCheck(
            id="extra", name="Extra", description="", severity=RegressionSeverity.INFO,
            metric="component_count", direction="higher_is_better", threshold_percent=10.0,
        ))
        assert len(detector.get_checks()) == original_len

    def test_empty_checks(self):
        # Note: checks=[] is falsy, so constructor uses defaults.
        # To get truly empty checks, we manipulate _checks directly.
        detector = ResilientRegressionDetector()
        detector._checks = []
        snap = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(snap, snap)
        assert report.overall_result == CheckResult.PASS
        assert len(report.outcomes) == 0

    def test_default_checks_count(self):
        detector = ResilientRegressionDetector()
        assert len(detector.get_checks()) == 8


# ---------------------------------------------------------------------------
# Tests: format_report
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_format_report_pass(self):
        detector = ResilientRegressionDetector()
        snap = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(snap, snap)
        text = detector.format_report(report)
        assert "Resilience Regression Report" in text
        assert "PASS" in text

    def test_format_report_fail(self):
        detector = ResilientRegressionDetector()
        baseline = InfraSnapshot(
            resilience_score=90.0, component_count=4, spof_count=0,
            avg_replicas=3.0, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        current = InfraSnapshot(
            resilience_score=40.0, component_count=4, spof_count=5,
            avg_replicas=1.0, max_dependency_depth=8, failover_coverage=0.0,
            encryption_coverage=0.0, monitoring_coverage=0.0,
            avg_utilization=95.0, single_points_of_failure=["A"] * 5,
            external_dependency_count=1,
        )
        report = detector.compare(baseline, current)
        text = detector.format_report(report)
        assert "FAIL" in text
        assert "REGRESSION" in text

    def test_format_report_contains_arrows(self):
        detector = ResilientRegressionDetector()
        snap = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(snap, snap)
        text = detector.format_report(report)
        assert "→" in text

    def test_format_report_exit_code(self):
        detector = ResilientRegressionDetector()
        snap = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(snap, snap)
        text = detector.format_report(report)
        assert "Exit code: 0" in text


# ---------------------------------------------------------------------------
# Tests: _evaluate_check edge cases
# ---------------------------------------------------------------------------


class TestEvaluateCheck:
    def test_missing_metric_skipped(self):
        detector = ResilientRegressionDetector(checks=[
            RegressionCheck(
                id="nonexistent", name="Nonexistent", description="",
                severity=RegressionSeverity.INFO, metric="nonexistent_metric",
                direction="higher_is_better", threshold_percent=5.0,
            )
        ])
        snap = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(snap, snap)
        assert report.skipped_count == 1
        assert report.outcomes[0].result == CheckResult.SKIP

    def test_zero_baseline_no_change(self):
        detector = ResilientRegressionDetector(checks=[
            RegressionCheck(
                id="spof", name="SPOF", description="",
                severity=RegressionSeverity.CRITICAL, metric="spof_count",
                direction="lower_is_better", threshold_percent=0.0,
            )
        ])
        snap = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(snap, snap)
        assert report.outcomes[0].result == CheckResult.PASS
        assert report.outcomes[0].delta_percent == 0

    def test_zero_baseline_with_increase(self):
        detector = ResilientRegressionDetector(checks=[
            RegressionCheck(
                id="spof", name="SPOF", description="",
                severity=RegressionSeverity.CRITICAL, metric="spof_count",
                direction="lower_is_better", threshold_percent=0.0,
            )
        ])
        baseline = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        current = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=2,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=["A", "B"],
            external_dependency_count=1,
        )
        report = detector.compare(baseline, current)
        assert report.outcomes[0].result == CheckResult.FAIL
        assert report.outcomes[0].delta_percent == 100

    def test_higher_is_better_improvement_message(self):
        detector = ResilientRegressionDetector(checks=[
            RegressionCheck(
                id="res", name="Resilience", description="",
                severity=RegressionSeverity.CRITICAL, metric="resilience_score",
                direction="higher_is_better", threshold_percent=5.0,
            )
        ])
        baseline = InfraSnapshot(
            resilience_score=70.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        current = InfraSnapshot(
            resilience_score=90.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(baseline, current)
        assert report.outcomes[0].result == CheckResult.PASS
        assert "Improved" in report.outcomes[0].message

    def test_lower_is_better_improvement_message(self):
        detector = ResilientRegressionDetector(checks=[
            RegressionCheck(
                id="util", name="Utilization", description="",
                severity=RegressionSeverity.INFO, metric="avg_utilization",
                direction="lower_is_better", threshold_percent=15.0,
            )
        ])
        baseline = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=80.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        current = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(baseline, current)
        assert report.outcomes[0].result == CheckResult.PASS
        assert "Improved" in report.outcomes[0].message

    def test_within_threshold_no_regression(self):
        detector = ResilientRegressionDetector(checks=[
            RegressionCheck(
                id="res", name="Resilience", description="",
                severity=RegressionSeverity.CRITICAL, metric="resilience_score",
                direction="higher_is_better", threshold_percent=10.0,
            )
        ])
        baseline = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        current = InfraSnapshot(
            resilience_score=80.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(baseline, current)
        # -5.9% is within 10% threshold
        assert report.outcomes[0].result == CheckResult.PASS

    def test_delta_values(self):
        detector = ResilientRegressionDetector(checks=[
            RegressionCheck(
                id="res", name="Resilience", description="",
                severity=RegressionSeverity.CRITICAL, metric="resilience_score",
                direction="higher_is_better", threshold_percent=5.0,
            )
        ])
        baseline = InfraSnapshot(
            resilience_score=80.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        current = InfraSnapshot(
            resilience_score=60.0, component_count=4, spof_count=0,
            avg_replicas=2.5, max_dependency_depth=2, failover_coverage=100.0,
            encryption_coverage=100.0, monitoring_coverage=100.0,
            avg_utilization=40.0, single_points_of_failure=[],
            external_dependency_count=1,
        )
        report = detector.compare(baseline, current)
        outcome = report.outcomes[0]
        assert outcome.baseline_value == 80.0
        assert outcome.current_value == 60.0
        assert outcome.delta == -20.0
        assert outcome.delta_percent == -25.0


# ---------------------------------------------------------------------------
# Tests: _calculate_depth
# ---------------------------------------------------------------------------


class TestCalculateDepth:
    def test_depth_linear_chain(self):
        detector = ResilientRegressionDetector()
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        g.add_component(_comp("d", "D"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        g.add_dependency(Dependency(source_id="c", target_id="d"))
        depth = detector._calculate_depth(g, "a")
        assert depth == 3

    def test_depth_no_deps(self):
        detector = ResilientRegressionDetector()
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        depth = detector._calculate_depth(g, "a")
        assert depth == 0

    def test_depth_with_cycle(self):
        detector = ResilientRegressionDetector()
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        depth = detector._calculate_depth(g, "a")
        assert depth >= 1  # Should not infinite loop


# ---------------------------------------------------------------------------
# Tests: Data classes
# ---------------------------------------------------------------------------


class TestDataClasses:
    def test_regression_check_fields(self):
        check = RegressionCheck(
            id="test", name="Test", description="Test check",
            severity=RegressionSeverity.WARNING, metric="spof_count",
            direction="lower_is_better", threshold_percent=5.0,
        )
        assert check.id == "test"
        assert check.threshold_percent == 5.0

    def test_check_outcome_fields(self):
        check = RegressionCheck(
            id="test", name="Test", description="",
            severity=RegressionSeverity.INFO, metric="spof_count",
            direction="lower_is_better", threshold_percent=5.0,
        )
        outcome = CheckOutcome(
            check=check, result=CheckResult.PASS,
            baseline_value=2, current_value=1,
            delta=-1, delta_percent=-50.0,
            message="Improved",
        )
        assert outcome.delta == -1
        assert outcome.delta_percent == -50.0

    def test_regression_report_fields(self):
        report = RegressionReport(
            outcomes=[], overall_result=CheckResult.PASS,
            passed_count=5, failed_count=0, warned_count=0, skipped_count=0,
            summary="5 passed", exit_code=0,
        )
        assert report.exit_code == 0
        assert report.summary == "5 passed"

    def test_infra_snapshot_fields(self):
        snap = InfraSnapshot(
            resilience_score=85.0, component_count=4, spof_count=1,
            avg_replicas=2.5, max_dependency_depth=3, failover_coverage=75.0,
            encryption_coverage=50.0, monitoring_coverage=100.0,
            avg_utilization=45.0, single_points_of_failure=["DB"],
            external_dependency_count=2,
        )
        assert snap.single_points_of_failure == ["DB"]
        assert snap.external_dependency_count == 2
