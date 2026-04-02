# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Tests for VulnerabilityPriorityEngine (Feature D)."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.vulnerability_priority import (
    VulnerabilityPriority,
    VulnerabilityPriorityEngine,
    VulnerabilityPriorityReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_graph_with_one_insecure_lb() -> InfraGraph:
    """Single load balancer with no security controls and downstream components."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Public LB",
        type=ComponentType.LOAD_BALANCER,
        port=80,
        replicas=1,
        security=SecurityProfile(
            encryption_at_rest=False,
            encryption_in_transit=False,
            waf_protected=False,
            auth_required=False,
            rate_limiting=False,
        ),
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
        security=SecurityProfile(encryption_at_rest=False),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


def _make_secure_graph() -> InfraGraph:
    """Graph where all components have full security controls."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Secure LB",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            auth_required=True,
            rate_limiting=True,
        ),
    ))
    graph.add_component(Component(
        id="db",
        name="Secure DB",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            auth_required=True,
            rate_limiting=True,
        ),
    ))
    return graph


def _make_empty_graph() -> InfraGraph:
    return InfraGraph()


def _make_single_node_graph() -> InfraGraph:
    graph = InfraGraph()
    graph.add_component(Component(
        id="solo",
        name="Solo Node",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
        security=SecurityProfile(encryption_at_rest=False, auth_required=False),
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests: _vulnerability_score
# ---------------------------------------------------------------------------


def test_vulnerability_score_insecure_lb() -> None:
    """Insecure load balancer should have max/high vulnerability score."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    lb = graph.get_component("lb")
    assert lb is not None
    score, factors = engine._vulnerability_score(lb)
    # Expected: no enc_rest +2, no enc_transit +2, no WAF on LB +3, no auth +2, no rate_limit +1 = 10
    assert score == 10.0
    assert "no WAF" in factors
    assert "no auth required" in factors
    assert "no rate limiting" in factors


def test_vulnerability_score_secure_lb() -> None:
    """Fully secured load balancer should have score 0."""
    graph = _make_secure_graph()
    engine = VulnerabilityPriorityEngine(graph)
    lb = graph.get_component("lb")
    assert lb is not None
    score, factors = engine._vulnerability_score(lb)
    assert score == 0.0
    assert factors == [] or all(f == "public facing" for f in factors)


def test_vulnerability_score_database_without_encryption_has_extra_penalty() -> None:
    """Database without encryption_at_rest should score +3 extra on top of base."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="DB",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
        security=SecurityProfile(
            encryption_at_rest=False,
            encryption_in_transit=True,
            auth_required=True,
            rate_limiting=True,
            waf_protected=False,
        ),
    ))
    engine = VulnerabilityPriorityEngine(graph)
    db = graph.get_component("db")
    assert db is not None
    score, factors = engine._vulnerability_score(db)
    # enc_at_rest=False: +2 + extra +3 for DB = 5; waf check: LB only so N/A; others ok
    assert score == 5.0
    assert "no encryption at rest" in factors
    assert "database without encryption" in factors


# ---------------------------------------------------------------------------
# Tests: _blast_radius
# ---------------------------------------------------------------------------


def test_blast_radius_db_affects_upstream() -> None:
    """DB (deepest dependency) failing should affect all upstream callers.

    Graph: lb -> app -> db
    get_all_affected("db") returns {lb, app} = 2 out of 3 components.
    """
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    # get_all_affected("db") = {lb, app} = 2 out of 3 components
    br = engine._blast_radius("db", len(graph.components))
    assert br == pytest.approx(2 / 3 * 100, abs=1.0)


def test_blast_radius_root_node_is_zero() -> None:
    """Root node (lb) has no upstream dependents, so blast_radius == 0.

    Graph: lb -> app -> db
    get_all_affected("lb") = {} (nothing upstream depends on lb).
    """
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    br = engine._blast_radius("lb", len(graph.components))
    assert br == 0.0


def test_blast_radius_empty_graph_is_zero() -> None:
    """Empty graph should return 0 blast radius."""
    graph = _make_empty_graph()
    engine = VulnerabilityPriorityEngine(graph)
    assert engine._blast_radius("nonexistent", 0) == 0.0


# ---------------------------------------------------------------------------
# Tests: analyze
# ---------------------------------------------------------------------------


def test_analyze_returns_report_type() -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert isinstance(report, VulnerabilityPriorityReport)


def test_analyze_priorities_count_matches_components() -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert len(report.priorities) == len(graph.components)


def test_analyze_ranks_are_unique_and_sequential() -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    ranks = [p.priority_rank for p in report.priorities]
    assert sorted(ranks) == list(range(1, len(ranks) + 1))


def test_analyze_priorities_sorted_by_score_descending() -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    scores = [p.priority_score for p in report.priorities]
    assert scores == sorted(scores, reverse=True)


def test_analyze_db_ranked_first_insecure() -> None:
    """In lb->app->db, the database is most critical because it has both high
    vulnerability (database without encryption penalty) and high blast radius
    (all upstream components depend on it).

    Graph: lb -> app -> db
    get_all_affected("db") = {lb, app} → blast_radius ≈ 66.7%
    get_all_affected("lb") = {} → blast_radius = 0%
    """
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    top = report.priorities[0]
    # db has highest priority_score: vulnerability(10) * blast_radius(66.7) / 10 ≈ 66.7
    assert top.component_id == "db"
    assert top.priority_rank == 1
    assert top.blast_radius > 0.0


def test_analyze_secure_graph_all_zero_scores() -> None:
    """Fully secured graph should have zero vulnerability scores."""
    graph = _make_secure_graph()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    for p in report.priorities:
        assert p.vulnerability_score == 0.0
        assert p.priority_score == 0.0


def test_analyze_empty_graph() -> None:
    graph = _make_empty_graph()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert report.priorities == []
    assert report.critical_count == 0
    assert report.high_count == 0
    assert report.risk_score == 0.0


def test_analyze_single_node_no_blast_radius() -> None:
    """Single isolated node has no downstream, so blast_radius == 0 and priority_score == 0."""
    graph = _make_single_node_graph()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert len(report.priorities) == 1
    p = report.priorities[0]
    assert p.blast_radius == 0.0
    assert p.priority_score == 0.0


def test_analyze_critical_count_correct() -> None:
    """critical_count should equal number of priorities with score >= 70."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    expected = sum(1 for p in report.priorities if p.priority_score >= 70.0)
    assert report.critical_count == expected


def test_analyze_high_count_correct() -> None:
    """high_count should equal priorities with 40 <= score < 70."""
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    expected = sum(1 for p in report.priorities if 40.0 <= p.priority_score < 70.0)
    assert report.high_count == expected


def test_analyze_summary_is_nonempty_string() -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    assert isinstance(report.summary, str)
    assert len(report.summary) > 0


def test_analyze_recommendation_nonempty_for_insecure(  # noqa: D103
) -> None:
    graph = _make_graph_with_one_insecure_lb()
    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()
    lb_entry = next((p for p in report.priorities if p.component_id == "lb"), None)
    assert lb_entry is not None
    assert lb_entry.recommendation != ""
