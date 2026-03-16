"""Tests for the enhanced backtest engine with CascadeEngine integration."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.backtest_engine import BacktestEngine, BacktestResult, RealIncident
from faultray.simulator.cascade import CascadeChain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_small_graph() -> InfraGraph:
    """Build a minimal 4-component graph for testing.

    Structure:
        lb -> app -> db
                  -> cache (optional)
    """
    graph = InfraGraph()

    components = [
        Component(
            id="lb",
            name="Load Balancer",
            type=ComponentType.LOAD_BALANCER,
            host="lb01",
            port=443,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=20, memory_percent=30),
            capacity=Capacity(max_connections=10000, timeout_seconds=30),
        ),
        Component(
            id="app",
            name="App Server",
            type=ComponentType.APP_SERVER,
            host="app01",
            port=8080,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=50, memory_percent=60, network_connections=80,
            ),
            capacity=Capacity(
                max_connections=500, connection_pool_size=100, timeout_seconds=30,
            ),
        ),
        Component(
            id="db",
            name="Database",
            type=ComponentType.DATABASE,
            host="db01",
            port=5432,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=40, memory_percent=70, disk_percent=60),
            capacity=Capacity(max_connections=100),
        ),
        Component(
            id="cache",
            name="Cache",
            type=ComponentType.CACHE,
            host="cache01",
            port=6379,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=10, memory_percent=40),
            capacity=Capacity(max_connections=5000),
        ),
    ]
    for comp in components:
        graph.add_component(comp)

    dependencies = [
        Dependency(source_id="lb", target_id="app", dependency_type="requires", weight=1.0),
        Dependency(source_id="app", target_id="db", dependency_type="requires", weight=1.0),
        Dependency(source_id="app", target_id="cache", dependency_type="optional", weight=0.5),
    ]
    for dep in dependencies:
        graph.add_dependency(dep)

    return graph


def _make_incident(
    incident_id: str = "INC-001",
    failed_component: str = "db",
    actual_affected: list[str] | None = None,
    actual_downtime_minutes: float = 30.0,
    actual_severity: str = "high",
) -> RealIncident:
    return RealIncident(
        incident_id=incident_id,
        timestamp="2025-01-01T00:00:00Z",
        failed_component=failed_component,
        actual_affected_components=actual_affected or ["db", "app", "lb"],
        actual_downtime_minutes=actual_downtime_minutes,
        actual_severity=actual_severity,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBacktestBasic:
    """test_backtest_basic: basic backtest execution with a small graph."""

    def test_single_incident_returns_result(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        incident = _make_incident()
        results = engine.run_backtest([incident])

        assert len(results) == 1
        r = results[0]
        assert isinstance(r, BacktestResult)
        assert r.incident is incident
        assert isinstance(r.predicted_affected, list)
        assert isinstance(r.predicted_severity, float)
        assert isinstance(r.predicted_downtime_minutes, float)
        assert isinstance(r.cascade_chain, CascadeChain)

    def test_skipped_when_component_missing(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        incident = _make_incident(failed_component="nonexistent")
        results = engine.run_backtest([incident])

        assert len(results) == 1
        r = results[0]
        assert r.details.get("skipped") is True
        assert r.predicted_affected == []
        assert r.precision == 0.0
        assert r.cascade_chain is None

    def test_predicted_affected_contains_failed_component(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        incident = _make_incident(failed_component="db")
        results = engine.run_backtest([incident])

        r = results[0]
        # The failed component itself should appear in predicted_affected
        # (CascadeEngine includes the direct effect on the target)
        assert "db" in r.predicted_affected


class TestPrecisionRecallF1:
    """test_precision_recall_f1: verify PR/F1 accuracy."""

    def test_perfect_match(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        # Run simulation first to see what it predicts
        incident = _make_incident(failed_component="db")
        results = engine.run_backtest([incident])
        predicted = results[0].predicted_affected

        # Create a new incident with actual == predicted for perfect match
        incident2 = _make_incident(
            incident_id="INC-PERFECT",
            failed_component="db",
            actual_affected=predicted,
        )
        results2 = engine.run_backtest([incident2])
        r = results2[0]

        assert r.precision == 1.0
        assert r.recall == 1.0
        assert r.f1_score == 1.0

    def test_no_overlap(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        # Actual affected has components that don't exist in graph predictions
        incident = _make_incident(
            failed_component="db",
            actual_affected=["zzzz-nonexistent"],
        )
        results = engine.run_backtest([incident])
        r = results[0]

        # predicted_affected will have at least "db", but actual has only "zzzz-nonexistent"
        assert r.recall == 0.0
        # precision may be 0 if no true positives
        assert r.f1_score == 0.0

    def test_partial_overlap(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        incident = _make_incident(
            failed_component="db",
            actual_affected=["db", "some-other-service"],
        )
        results = engine.run_backtest([incident])
        r = results[0]

        # "db" is in both predicted and actual → tp=1
        # "some-other-service" is only in actual → fn=1
        # recall should be < 1.0
        assert 0.0 < r.recall < 1.0
        assert r.precision > 0.0
        assert r.f1_score > 0.0


class TestSeverityAccuracy:
    """test_severity_accuracy: severity accuracy calculation."""

    def test_exact_severity_match(self) -> None:
        engine = BacktestEngine(_build_small_graph())
        # _severity_str_to_float("critical") = 9.0
        # If predicted_severity is also 9.0, accuracy should be 1.0
        acc = engine._calc_severity_accuracy(9.0, "critical")
        assert acc == 1.0

    def test_opposite_severity(self) -> None:
        engine = BacktestEngine(_build_small_graph())
        # predicted=0.0 vs actual="critical"(9.0) → distance=9.0, accuracy=0.1
        acc = engine._calc_severity_accuracy(0.0, "critical")
        assert acc == pytest.approx(0.1, abs=0.01)

    def test_medium_severity_close(self) -> None:
        engine = BacktestEngine(_build_small_graph())
        # predicted=5.0 vs actual="medium"(5.0) → exact match
        acc = engine._calc_severity_accuracy(5.0, "medium")
        assert acc == 1.0

    def test_severity_str_to_float_mapping(self) -> None:
        engine = BacktestEngine(_build_small_graph())
        assert engine._severity_str_to_float("critical") == 9.0
        assert engine._severity_str_to_float("high") == 7.0
        assert engine._severity_str_to_float("medium") == 5.0
        assert engine._severity_str_to_float("low") == 2.0
        assert engine._severity_str_to_float("unknown") == 5.0  # default

    def test_severity_accuracy_in_backtest_result(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        incident = _make_incident(actual_severity="critical")
        results = engine.run_backtest([incident])
        r = results[0]
        assert 0.0 <= r.severity_accuracy <= 1.0


class TestDowntimeMAE:
    """test_downtime_mae: downtime MAE calculation."""

    def test_downtime_mae_is_absolute_error(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        incident = _make_incident(actual_downtime_minutes=30.0)
        results = engine.run_backtest([incident])
        r = results[0]

        expected_mae = abs(r.predicted_downtime_minutes - 30.0)
        assert r.downtime_mae == pytest.approx(expected_mae, abs=0.01)

    def test_downtime_mae_zero_when_perfect(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        # First run to get predicted downtime
        incident = _make_incident()
        results = engine.run_backtest([incident])
        predicted_dt = results[0].predicted_downtime_minutes

        # Create incident with actual matching predicted
        incident2 = _make_incident(
            incident_id="INC-DT",
            actual_downtime_minutes=predicted_dt,
        )
        results2 = engine.run_backtest([incident2])
        assert results2[0].downtime_mae == pytest.approx(0.0, abs=0.01)

    def test_estimate_downtime_empty_chain(self) -> None:
        chain = CascadeChain(trigger="test", total_components=4)
        dt = BacktestEngine._estimate_downtime(chain)
        assert dt == 0.0


class TestConfidenceScore:
    """test_confidence_score: prediction confidence calculation."""

    def test_confidence_in_range(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        incident = _make_incident()
        results = engine.run_backtest([incident])
        r = results[0]

        assert 0.0 <= r.prediction_confidence <= 1.0

    def test_confidence_components(self) -> None:
        """Confidence = f1*0.5 + severity_accuracy*0.3 + max(0,1-dt_mae/60)*0.2"""
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        incident = _make_incident()
        results = engine.run_backtest([incident])
        r = results[0]

        dt_component = max(0.0, 1.0 - r.downtime_mae / 60)
        expected = r.f1_score * 0.5 + r.severity_accuracy * 0.3 + dt_component * 0.2
        assert r.prediction_confidence == pytest.approx(expected, abs=0.01)


class TestCalibrate:
    """test_calibrate: calibration recommendations."""

    def test_calibrate_empty(self) -> None:
        engine = BacktestEngine(_build_small_graph())
        result = engine.calibrate([])
        assert result == {}

    def test_calibrate_downtime_bias(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        # Create incidents where actual downtime is much higher than predicted
        incidents = [
            _make_incident(
                incident_id=f"INC-{i}",
                actual_downtime_minutes=120.0,  # very high actual downtime
            )
            for i in range(3)
        ]
        results = engine.run_backtest(incidents)
        cal = engine.calibrate(results)

        # If predicted is much lower than actual, avg_error is negative,
        # so downtime_bias_correction should be positive
        if "downtime_bias_correction" in cal:
            # The correction should push predictions UP
            assert isinstance(cal["downtime_bias_correction"], float)

    def test_calibrate_low_recall(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        # Create incidents with many actual_affected that won't be predicted
        incident = _make_incident(
            actual_affected=["db", "app", "lb", "cache", "x1", "x2", "x3", "x4", "x5"],
        )
        results = engine.run_backtest([incident])
        cal = engine.calibrate(results)

        # With many unpredicted components, recall < 0.7 → threshold reduction
        if results[0].recall < 0.7:
            assert "dependency_weight_threshold_reduction" in cal
            assert cal["dependency_weight_threshold_reduction"] == 0.1


class TestSummary:
    """test_summary: summary report structure."""

    def test_summary_structure(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        incidents = [
            _make_incident(incident_id="INC-001"),
            _make_incident(incident_id="INC-002", failed_component="app"),
        ]
        results = engine.run_backtest(incidents)
        summary = engine.summary(results)

        assert summary["total_incidents"] == 2
        assert "avg_precision" in summary
        assert "avg_recall" in summary
        assert "avg_f1" in summary
        assert "avg_severity_accuracy" in summary
        assert "avg_downtime_mae_minutes" in summary
        assert "avg_confidence" in summary
        assert "calibration" in summary
        assert isinstance(summary["calibration"], dict)
        assert "per_incident" in summary
        assert len(summary["per_incident"]) == 2

    def test_summary_per_incident_fields(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        results = engine.run_backtest([_make_incident()])
        summary = engine.summary(results)

        item = summary["per_incident"][0]
        assert "incident_id" in item
        assert "component" in item
        assert "precision" in item
        assert "recall" in item
        assert "f1" in item
        assert "severity_accuracy" in item
        assert "downtime_mae" in item
        assert "confidence" in item


class TestEmptyIncidents:
    """test_empty_incidents: empty incident list produces no errors."""

    def test_run_backtest_empty(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        results = engine.run_backtest([])
        assert results == []

    def test_summary_empty(self) -> None:
        graph = _build_small_graph()
        engine = BacktestEngine(graph)
        summary = engine.summary([])
        assert summary["total_incidents"] == 0
        assert summary["avg_f1"] == 0.0

    def test_calibrate_empty_results(self) -> None:
        engine = BacktestEngine(_build_small_graph())
        assert engine.calibrate([]) == {}


class TestDemoGraph:
    """Integration test using the demo graph."""

    def test_backtest_with_demo_graph(self) -> None:
        from faultray.model.demo import create_demo_graph

        graph = create_demo_graph()
        engine = BacktestEngine(graph)

        incidents = [
            RealIncident(
                incident_id="DEMO-001",
                timestamp="2025-06-01T00:00:00Z",
                failed_component="postgres",
                actual_affected_components=["postgres", "app-1", "app-2", "nginx"],
                actual_downtime_minutes=45.0,
                actual_severity="critical",
            ),
            RealIncident(
                incident_id="DEMO-002",
                timestamp="2025-06-02T00:00:00Z",
                failed_component="redis",
                actual_affected_components=["redis", "app-1", "app-2"],
                actual_downtime_minutes=10.0,
                actual_severity="medium",
            ),
        ]

        results = engine.run_backtest(incidents)
        assert len(results) == 2

        summary = engine.summary(results)
        assert summary["total_incidents"] == 2
        assert 0.0 <= summary["avg_f1"] <= 1.0
        assert 0.0 <= summary["avg_severity_accuracy"] <= 1.0
        assert summary["avg_downtime_mae_minutes"] >= 0.0
        assert 0.0 <= summary["avg_confidence"] <= 1.0

        # Cascade chain should be present for both
        for r in results:
            assert r.cascade_chain is not None
            assert len(r.cascade_chain.effects) > 0
