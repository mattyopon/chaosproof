"""Tests for the Chaos Experiment Marketplace."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from infrasim.marketplace import (
    FairnessProtocol,
    ScenarioManifest,
    ScenarioMarketplace,
)
from infrasim.model.components import Component, ComponentType, FailoverConfig
from infrasim.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(
    mid: str = "test-001",
    name: str = "DB Failover Test",
    category: str = "database",
    domain: str = "general",
    blast_radius: float = 0.8,
    component_types_required: list[str] | None = None,
    scenario_data: dict | None = None,
) -> ScenarioManifest:
    return ScenarioManifest(
        id=mid,
        name=name,
        description="A test chaos scenario",
        category=category,
        domain=domain,
        author="tester",
        version="1.0.0",
        blast_radius=blast_radius,
        component_types_required=component_types_required if component_types_required is not None else ["database"],
        scenario_data=scenario_data or {
            "faults": [
                {
                    "target_component_id": "db-primary",
                    "fault_type": "component_down",
                    "severity": 1.0,
                    "duration_seconds": 300,
                    "_required_type": "database",
                }
            ],
            "traffic_multiplier": 1.0,
        },
    )


def _make_graph(*types: str, failover: bool = False) -> InfraGraph:
    """Build a minimal InfraGraph with the given component types."""
    g = InfraGraph()
    for i, t in enumerate(types):
        g.add_component(
            Component(
                id=f"comp-{i}",
                name=f"Component {i}",
                type=ComponentType(t),
                failover=FailoverConfig(enabled=failover),
            )
        )
    return g


# ---------------------------------------------------------------------------
# ScenarioManifest tests
# ---------------------------------------------------------------------------


class TestScenarioManifest:
    def test_average_rating_no_ratings(self):
        m = _make_manifest()
        assert m.average_rating == 0.0

    def test_average_rating_with_ratings(self):
        m = _make_manifest()
        m.ratings = [
            {"author": "alice", "score": 5, "comment": "great"},
            {"author": "bob", "score": 3, "comment": "ok"},
        ]
        assert m.average_rating == 4.0

    def test_seal_deterministic(self):
        m = _make_manifest()
        seal1 = m.seal("secret")
        seal2 = m.seal("secret")
        assert seal1 == seal2
        assert len(seal1) == 64  # SHA-256 hex

    def test_seal_changes_with_key(self):
        m = _make_manifest()
        assert m.seal("key1") != m.seal("key2")

    def test_to_dict_from_dict_roundtrip(self):
        m = _make_manifest()
        m.ratings = [{"author": "alice", "score": 4, "comment": "nice"}]
        m.downloads = 42
        d = m.to_dict()
        restored = ScenarioManifest.from_dict(d)
        assert restored.id == m.id
        assert restored.name == m.name
        assert restored.downloads == 42
        assert restored.ratings == m.ratings


# ---------------------------------------------------------------------------
# FairnessProtocol tests
# ---------------------------------------------------------------------------


class TestFairnessProtocol:
    def test_no_reduction_when_coverage_high(self):
        m = _make_manifest(component_types_required=["database"])
        graph = _make_graph("database", "cache")
        original_blast = m.blast_radius
        FairnessProtocol.apply(m, graph)
        assert m.blast_radius == original_blast  # coverage = 1.0 >= 0.5

    def test_reduction_when_coverage_low(self):
        m = _make_manifest(
            blast_radius=1.0,
            component_types_required=["database", "cache", "queue"],
        )
        graph = _make_graph("app_server")  # 0/3 coverage
        FairnessProtocol.apply(m, graph)
        assert m.blast_radius == pytest.approx(0.6, abs=0.01)

    def test_no_reduction_empty_required(self):
        m = _make_manifest(blast_radius=0.9, component_types_required=[])
        graph = _make_graph("app_server")
        FairnessProtocol.apply(m, graph)
        assert m.blast_radius == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# ScenarioMarketplace tests
# ---------------------------------------------------------------------------


class TestScenarioMarketplace:
    @pytest.fixture()
    def mp(self, tmp_path: Path) -> ScenarioMarketplace:
        return ScenarioMarketplace(store_path=tmp_path / "marketplace")

    def test_publish_and_download(self, mp: ScenarioMarketplace):
        m = _make_manifest()
        mid = mp.publish(m)
        assert mid == "test-001"

        downloaded = mp.download(mid)
        assert downloaded.name == "DB Failover Test"
        assert downloaded.downloads == 1

    def test_download_increments_counter(self, mp: ScenarioMarketplace):
        m = _make_manifest()
        mp.publish(m)
        mp.download("test-001")
        mp.download("test-001")
        result = mp.download("test-001")
        assert result.downloads == 3

    def test_download_not_found(self, mp: ScenarioMarketplace):
        with pytest.raises(FileNotFoundError):
            mp.download("nonexistent")

    def test_search_all(self, mp: ScenarioMarketplace):
        mp.publish(_make_manifest(mid="a1", name="Scenario A", category="database"))
        mp.publish(_make_manifest(mid="b2", name="Scenario B", category="network"))
        results = mp.search()
        assert len(results) == 2

    def test_search_by_category(self, mp: ScenarioMarketplace):
        mp.publish(_make_manifest(mid="a1", category="database"))
        mp.publish(_make_manifest(mid="b2", category="network"))
        results = mp.search(category="database")
        assert len(results) == 1
        assert results[0].id == "a1"

    def test_search_by_domain(self, mp: ScenarioMarketplace):
        mp.publish(_make_manifest(mid="a1", domain="fintech"))
        mp.publish(_make_manifest(mid="b2", domain="saas"))
        results = mp.search(domain="fintech")
        assert len(results) == 1
        assert results[0].id == "a1"

    def test_search_by_query(self, mp: ScenarioMarketplace):
        mp.publish(_make_manifest(mid="a1", name="Traffic Spike Chaos"))
        mp.publish(_make_manifest(mid="b2", name="DB Failover"))
        results = mp.search(query="traffic")
        assert len(results) == 1
        assert results[0].name == "Traffic Spike Chaos"

    def test_rate_and_top_rated(self, mp: ScenarioMarketplace):
        mp.publish(_make_manifest(mid="a1", name="Scenario A"))
        mp.publish(_make_manifest(mid="b2", name="Scenario B"))
        mp.rate("a1", author="alice", score=5, comment="awesome")
        mp.rate("b2", author="alice", score=3, comment="ok")

        top = mp.top_rated(n=2)
        assert len(top) == 2
        assert top[0].id == "a1"  # Higher rating first

    def test_rate_invalid_score(self, mp: ScenarioMarketplace):
        mp.publish(_make_manifest(mid="a1"))
        with pytest.raises(ValueError, match="between 1 and 5"):
            mp.rate("a1", author="alice", score=0)

    def test_rate_update_existing(self, mp: ScenarioMarketplace):
        mp.publish(_make_manifest(mid="a1"))
        mp.rate("a1", author="alice", score=3)
        mp.rate("a1", author="alice", score=5)  # Update
        m = mp.get("a1")
        assert len(m.ratings) == 1
        assert m.ratings[0]["score"] == 5

    def test_import_to_simulation(self, mp: ScenarioMarketplace):
        m = _make_manifest()
        graph = _make_graph("database", "app_server")
        scenario = mp.import_to_simulation(m, graph)
        assert scenario.id.startswith("marketplace-")
        assert scenario.name == m.name
        assert len(scenario.faults) == 1

    def test_publish_auto_generates_id(self, mp: ScenarioMarketplace):
        m = _make_manifest(mid="")
        mid = mp.publish(m)
        assert mid  # Should have auto-generated a non-empty ID
        assert len(mid) == 12

    def test_get_without_incrementing_downloads(self, mp: ScenarioMarketplace):
        mp.publish(_make_manifest(mid="a1"))
        m = mp.get("a1")
        assert m.downloads == 0
        m2 = mp.get("a1")
        assert m2.downloads == 0
