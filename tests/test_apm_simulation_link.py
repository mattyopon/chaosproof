"""Tests for FaultRay APM simulation link."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.apm.metrics_db import MetricsDB
from faultray.apm.simulation_link import SimulationAPMLink
from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


@pytest.fixture()
def db(tmp_path: Path) -> MetricsDB:
    mdb = MetricsDB(db_path=tmp_path / "sim_link.db")
    mdb.open()
    yield mdb
    mdb.close()


@pytest.fixture()
def graph() -> InfraGraph:
    g = InfraGraph()
    g.add_component(Component(id="web-01", name="web-01.example.com", type=ComponentType.WEB_SERVER))
    g.add_component(Component(id="db-01", name="db-01.example.com", type=ComponentType.DATABASE))
    return g


@pytest.fixture()
def link(graph: InfraGraph, db: MetricsDB) -> SimulationAPMLink:
    return SimulationAPMLink(graph, db)


# ---------------------------------------------------------------------------
# Critical component marking
# ---------------------------------------------------------------------------


class TestCriticalComponents:
    def test_marks_critical_scenarios(self, link: SimulationAPMLink) -> None:
        sim_results = {
            "scenarios": [
                {"component_id": "web-01", "severity": "critical"},
                {"component_id": "db-01", "severity": "low"},
            ],
        }
        critical = link.mark_critical_components(sim_results)
        assert "web-01" in critical
        assert "db-01" not in critical

    def test_marks_high_severity(self, link: SimulationAPMLink) -> None:
        sim_results = {
            "scenarios": [
                {"component_id": "web-01", "severity": "high"},
            ],
        }
        critical = link.mark_critical_components(sim_results)
        assert "web-01" in critical

    def test_empty_scenarios(self, link: SimulationAPMLink) -> None:
        assert link.mark_critical_components({"scenarios": []}) == []

    def test_no_duplicates(self, link: SimulationAPMLink) -> None:
        sim_results = {
            "scenarios": [
                {"component_id": "web-01", "severity": "critical"},
                {"component_id": "web-01", "severity": "high"},
            ],
        }
        critical = link.mark_critical_components(sim_results)
        assert critical.count("web-01") == 1


# ---------------------------------------------------------------------------
# Model calibration
# ---------------------------------------------------------------------------


class TestCalibration:
    def test_calibrate_with_mapping(self, link: SimulationAPMLink, db: MetricsDB) -> None:
        db.register_agent({"agent_id": "a1", "hostname": "web-01"})
        db.insert_metrics("a1", [
            {"name": "cpu_percent", "value": 65.0},
            {"name": "memory_percent", "value": 45.0},
        ])

        count = link.calibrate_model({"a1": "web-01"})
        assert count == 1

        comp = link.graph.get_component("web-01")
        assert comp is not None
        assert comp.metrics.cpu_percent == 65.0
        assert comp.metrics.memory_percent == 45.0

    def test_calibrate_no_metrics(self, link: SimulationAPMLink, db: MetricsDB) -> None:
        db.register_agent({"agent_id": "a1", "hostname": "web-01"})
        count = link.calibrate_model({"a1": "web-01"})
        assert count == 0

    def test_calibrate_unknown_component(self, link: SimulationAPMLink, db: MetricsDB) -> None:
        db.register_agent({"agent_id": "a1", "hostname": "unknown"})
        db.insert_metrics("a1", [{"name": "cpu_percent", "value": 50.0}])
        count = link.calibrate_model({"a1": "nonexistent-comp"})
        assert count == 0


# ---------------------------------------------------------------------------
# Predicted vs Actual comparison
# ---------------------------------------------------------------------------


class TestPredictionComparison:
    def test_compare(self, link: SimulationAPMLink, db: MetricsDB) -> None:
        db.register_agent({"agent_id": "a1", "hostname": "web-01"})
        db.insert_metrics("a1", [
            {"name": "cpu_percent", "value": 85.0},
            {"name": "memory_percent", "value": 70.0},
        ])

        sim_results = {"component_scores": {"web-01": 7.5}}
        comparisons = link.compare_prediction_vs_actual(
            sim_results, {"a1": "web-01"}
        )
        assert len(comparisons) == 1
        c = comparisons[0]
        assert c["component_id"] == "web-01"
        assert c["actual_cpu_percent"] == 85.0
        assert c["cpu_stress_level"] == "high"

    def test_compare_no_mapping(self, link: SimulationAPMLink) -> None:
        sim_results = {"component_scores": {"web-01": 7.5}}
        comparisons = link.compare_prediction_vs_actual(sim_results, {})
        assert comparisons == []


# ---------------------------------------------------------------------------
# Auto-mapping
# ---------------------------------------------------------------------------


class TestAutoMapping:
    def test_auto_map_by_label(self, link: SimulationAPMLink, db: MetricsDB) -> None:
        db.register_agent({
            "agent_id": "a1",
            "hostname": "some-host",
            "labels": {"component_id": "web-01"},
        })
        mapping = link._auto_map_agents()
        assert mapping == {"a1": "web-01"}

    def test_auto_map_by_hostname(self, link: SimulationAPMLink, db: MetricsDB) -> None:
        db.register_agent({
            "agent_id": "a1",
            "hostname": "web-01",
        })
        mapping = link._auto_map_agents()
        assert "a1" in mapping
