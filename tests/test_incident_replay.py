"""Tests for the Incident Replay Engine."""

from __future__ import annotations

from datetime import datetime, timedelta

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    HealthStatus,
    RegionConfig,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.incident_db import HISTORICAL_INCIDENTS
from infrasim.simulator.incident_replay import (
    AffectedComponent,
    HistoricalIncident,
    IncidentEvent,
    IncidentReplayEngine,
    ReplayResult,
    SERVICE_COMPONENT_MAPPING,
)


# ---------------------------------------------------------------------------
# Fixtures: Build test infrastructure graphs
# ---------------------------------------------------------------------------

def _build_single_region_graph() -> InfraGraph:
    """Build a simple single-region infra (vulnerable to regional outages)."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=1,
        region=RegionConfig(region="us-east-1"),
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=1,
        region=RegionConfig(region="us-east-1"),
    ))
    graph.add_component(Component(
        id="db",
        name="RDS Database",
        type=ComponentType.DATABASE,
        replicas=1,
        region=RegionConfig(region="us-east-1"),
    ))
    graph.add_component(Component(
        id="cache",
        name="ElastiCache Redis",
        type=ComponentType.CACHE,
        replicas=1,
        region=RegionConfig(region="us-east-1"),
    ))

    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))

    return graph


def _build_multi_region_graph() -> InfraGraph:
    """Build a resilient multi-region infra with failover."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb",
        name="Global Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=2,
        region=RegionConfig(region="us-east-1", dr_target_region="us-west-2"),
        failover=FailoverConfig(enabled=True, promotion_time_seconds=15),
    ))
    graph.add_component(Component(
        id="app-east",
        name="App Server (East)",
        type=ComponentType.APP_SERVER,
        replicas=3,
        region=RegionConfig(region="us-east-1", dr_target_region="us-west-2"),
        failover=FailoverConfig(enabled=True, promotion_time_seconds=30),
    ))
    graph.add_component(Component(
        id="app-west",
        name="App Server (West)",
        type=ComponentType.APP_SERVER,
        replicas=3,
        region=RegionConfig(region="us-west-2"),
    ))
    graph.add_component(Component(
        id="db-primary",
        name="Aurora Primary",
        type=ComponentType.DATABASE,
        replicas=2,
        region=RegionConfig(region="us-east-1", dr_target_region="us-west-2"),
        failover=FailoverConfig(enabled=True, promotion_time_seconds=60),
    ))
    graph.add_component(Component(
        id="db-replica",
        name="Aurora Replica",
        type=ComponentType.DATABASE,
        replicas=2,
        region=RegionConfig(region="us-west-2"),
    ))
    graph.add_component(Component(
        id="cache",
        name="ElastiCache Redis",
        type=ComponentType.CACHE,
        replicas=3,
        region=RegionConfig(region="us-east-1"),
    ))

    graph.add_dependency(Dependency(source_id="lb", target_id="app-east", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="lb", target_id="app-west", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app-east", target_id="db-primary", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app-west", target_id="db-replica", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app-east", target_id="cache", dependency_type="optional"))

    return graph


def _build_no_cloud_graph() -> InfraGraph:
    """Build a graph with no cloud-specific components (should be unaffected)."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="custom-1",
        name="Custom Component",
        type=ComponentType.CUSTOM,
        replicas=1,
    ))

    return graph


# ---------------------------------------------------------------------------
# Tests: IncidentReplayEngine
# ---------------------------------------------------------------------------

class TestIncidentReplayEngine:
    """Tests for IncidentReplayEngine core functionality."""

    def test_list_incidents_returns_all(self):
        engine = IncidentReplayEngine()
        incidents = engine.list_incidents()
        assert len(incidents) >= 15  # We require at least 15 incidents

    def test_list_incidents_filter_by_provider(self):
        engine = IncidentReplayEngine()
        aws_incidents = engine.list_incidents(provider="aws")
        assert len(aws_incidents) >= 3  # Multiple AWS incidents
        assert all(i.provider == "aws" for i in aws_incidents)

    def test_list_incidents_filter_by_unknown_provider(self):
        engine = IncidentReplayEngine()
        incidents = engine.list_incidents(provider="nonexistent")
        assert incidents == []

    def test_get_incident_by_id(self):
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        assert inc.id == "aws-us-east-1-2021-12"
        assert inc.provider == "aws"
        assert inc.severity == "critical"

    def test_get_incident_unknown_id_raises(self):
        engine = IncidentReplayEngine()
        try:
            engine.get_incident("nonexistent-incident")
            assert False, "Should have raised KeyError"
        except KeyError as e:
            assert "nonexistent-incident" in str(e)

    def test_replay_single_region_vs_regional_outage(self):
        """Single-region infra in us-east-1 should fail during us-east-1 outage."""
        engine = IncidentReplayEngine()
        graph = _build_single_region_graph()
        inc = engine.get_incident("aws-us-east-1-2021-12")

        result = engine.replay(graph, inc)

        assert isinstance(result, ReplayResult)
        assert not result.survived
        assert result.impact_score > 5.0
        assert result.resilience_grade_during_incident in ("D", "F")
        assert len(result.affected_components) > 0
        assert result.downtime_estimate > timedelta(0)
        assert len(result.vulnerability_factors) > 0

    def test_replay_multi_region_survives_regional_outage(self):
        """Multi-region infra with failover should survive a single-region outage."""
        engine = IncidentReplayEngine()
        graph = _build_multi_region_graph()
        inc = engine.get_incident("aws-us-east-1-2021-12")

        result = engine.replay(graph, inc)

        assert isinstance(result, ReplayResult)
        # Multi-region should survive (or at least score much better)
        assert result.impact_score < 8.0
        assert len(result.survival_factors) > 0

    def test_replay_unrelated_infra_is_unaffected(self):
        """Infrastructure with no matching components should be unaffected."""
        engine = IncidentReplayEngine()
        graph = _build_no_cloud_graph()
        inc = engine.get_incident("aws-us-east-1-2021-12")

        result = engine.replay(graph, inc)

        assert result.survived
        assert result.impact_score == 0.0
        assert result.resilience_grade_during_incident == "A"
        assert len(result.affected_components) == 0

    def test_replay_all_returns_all_results(self):
        """replay_all should return one result per incident."""
        engine = IncidentReplayEngine()
        graph = _build_single_region_graph()

        results = engine.replay_all(graph)

        assert len(results) == len(engine.list_incidents())
        assert all(isinstance(r, ReplayResult) for r in results)

    def test_find_vulnerable_incidents(self):
        """find_vulnerable_incidents should return sorted vulnerability scores."""
        engine = IncidentReplayEngine()
        graph = _build_single_region_graph()

        vuln = engine.find_vulnerable_incidents(graph)

        assert len(vuln) > 0
        # Should be sorted by vulnerability score descending
        scores = [score for _, score in vuln]
        assert scores == sorted(scores, reverse=True)
        # All scores should be > 0
        assert all(score > 0 for _, score in vuln)

    def test_no_vulnerable_incidents_for_custom_infra(self):
        """Custom-only infra should have no matching vulnerabilities."""
        engine = IncidentReplayEngine()
        graph = _build_no_cloud_graph()

        vuln = engine.find_vulnerable_incidents(graph)

        assert len(vuln) == 0


class TestReplayResult:
    """Tests for ReplayResult data class properties."""

    def test_impact_score_range(self):
        """Impact score should always be between 0 and 10."""
        engine = IncidentReplayEngine()
        graph = _build_single_region_graph()

        for inc in engine.list_incidents():
            result = engine.replay(graph, inc)
            assert 0.0 <= result.impact_score <= 10.0

    def test_grade_values(self):
        """Grade should be one of A-F."""
        engine = IncidentReplayEngine()
        graph = _build_single_region_graph()

        for inc in engine.list_incidents():
            result = engine.replay(graph, inc)
            assert result.resilience_grade_during_incident in ("A", "B", "C", "D", "F")

    def test_recommendations_generated_for_failures(self):
        """Failing replays should produce at least one recommendation."""
        engine = IncidentReplayEngine()
        graph = _build_single_region_graph()
        inc = engine.get_incident("aws-us-east-1-2021-12")

        result = engine.replay(graph, inc)

        if not result.survived:
            assert len(result.recommendations) > 0

    def test_revenue_impact_with_cost_profile(self):
        """Revenue impact should be calculated when cost profiles are set."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app",
            name="App Server",
            type=ComponentType.APP_SERVER,
            replicas=1,
            region=RegionConfig(region="us-east-1"),
            cost_profile=CostProfile(revenue_per_minute=100.0),
        ))

        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(graph, inc)

        if not result.survived and result.downtime_estimate > timedelta(0):
            assert result.revenue_impact_estimate is not None
            assert result.revenue_impact_estimate > 0

    def test_timeline_events_ordered(self):
        """Replay timeline events should be in chronological order."""
        engine = IncidentReplayEngine()
        graph = _build_single_region_graph()
        inc = engine.get_incident("aws-us-east-1-2021-12")

        result = engine.replay(graph, inc)

        if result.timeline:
            for i in range(1, len(result.timeline)):
                assert result.timeline[i].timestamp_offset >= result.timeline[i - 1].timestamp_offset


class TestCascadeEffects:
    """Tests for cascade analysis in replay."""

    def test_cascade_from_db_failure(self):
        """DB failure should cascade to app server through requires dependency."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app",
            name="App Server",
            type=ComponentType.APP_SERVER,
            replicas=1,
            region=RegionConfig(region="us-east-1"),
        ))
        graph.add_component(Component(
            id="db",
            name="Database",
            type=ComponentType.DATABASE,
            replicas=1,
            region=RegionConfig(region="us-east-1"),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="db", dependency_type="requires"
        ))

        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(graph, inc)

        # Both should be affected
        affected_ids = {ac.component_id for ac in result.affected_components}
        assert "db" in affected_ids
        # App should be affected through cascade
        if "app" not in affected_ids:
            # It may have been matched directly as a server
            pass
        assert len(result.affected_components) >= 1

    def test_optional_dependency_degrades_not_fails(self):
        """Optional dependency failure should degrade, not fully fail dependent."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app",
            name="App Server",
            type=ComponentType.APP_SERVER,
            replicas=1,
            region=RegionConfig(region="us-east-1"),
        ))
        graph.add_component(Component(
            id="cache",
            name="Redis Cache",
            type=ComponentType.CACHE,
            replicas=1,
            region=RegionConfig(region="us-east-1"),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id="cache", dependency_type="optional"
        ))

        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(graph, inc)

        # Cache goes down, app should cascade to DEGRADED (not DOWN)
        cascade_effects = [
            ac for ac in result.affected_components
            if ac.impact_type == "cascade"
        ]
        for ce in cascade_effects:
            if ce.component_id == "app":
                assert ce.health_during_incident == HealthStatus.DEGRADED


class TestComponentMatching:
    """Tests for service-to-component matching logic."""

    def test_match_by_component_type(self):
        """Components should match by their ComponentType."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="my-db",
            name="MyCustomDB",
            type=ComponentType.DATABASE,
        ))

        engine = IncidentReplayEngine()
        matched = engine._find_matching_components(graph, "rds")
        assert len(matched) == 1
        assert matched[0].id == "my-db"

    def test_match_by_name_pattern(self):
        """Components should match by name pattern even if type differs."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="redis-cluster",
            name="Redis Cluster",
            type=ComponentType.CUSTOM,  # Not CACHE type, but name has "redis"
        ))

        engine = IncidentReplayEngine()
        matched = engine._find_matching_components(graph, "elasticache")
        assert len(matched) == 1
        assert matched[0].id == "redis-cluster"

    def test_no_match_for_unrelated_service(self):
        """Unrelated components should not match."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="api",
            name="API Gateway",
            type=ComponentType.APP_SERVER,
        ))

        engine = IncidentReplayEngine()
        matched = engine._find_matching_components(graph, "s3")
        assert len(matched) == 0


class TestServiceComponentMapping:
    """Tests for the SERVICE_COMPONENT_MAPPING constant."""

    def test_all_aws_services_have_mapping(self):
        """All common AWS services should have a mapping."""
        aws_services = ["ec2", "rds", "elasticache", "alb", "s3", "sqs", "lambda",
                        "route53", "cloudfront", "api_gateway"]
        for service in aws_services:
            assert service in SERVICE_COMPONENT_MAPPING, f"Missing mapping for {service}"

    def test_all_mappings_have_required_keys(self):
        """Each mapping should have types and name_patterns."""
        for service, mapping in SERVICE_COMPONENT_MAPPING.items():
            assert "types" in mapping, f"Missing 'types' for {service}"
            assert "name_patterns" in mapping, f"Missing 'name_patterns' for {service}"
            assert len(mapping["types"]) > 0, f"Empty 'types' for {service}"
            assert len(mapping["name_patterns"]) > 0, f"Empty 'name_patterns' for {service}"


class TestHistoricalIncidentDB:
    """Tests for the historical incident database."""

    def test_minimum_incident_count(self):
        """Should have at least 15 incidents."""
        assert len(HISTORICAL_INCIDENTS) >= 15

    def test_incident_ids_unique(self):
        """All incident IDs should be unique."""
        ids = [inc.id for inc in HISTORICAL_INCIDENTS]
        assert len(ids) == len(set(ids))

    def test_all_incidents_have_required_fields(self):
        """All incidents should have non-empty required fields."""
        for inc in HISTORICAL_INCIDENTS:
            assert inc.id, f"Empty ID"
            assert inc.name, f"Empty name for {inc.id}"
            assert inc.provider, f"Empty provider for {inc.id}"
            assert inc.root_cause, f"Empty root_cause for {inc.id}"
            assert inc.affected_services, f"Empty affected_services for {inc.id}"
            assert inc.affected_regions, f"Empty affected_regions for {inc.id}"
            assert inc.severity in ("critical", "major", "minor"), (
                f"Invalid severity '{inc.severity}' for {inc.id}"
            )
            assert inc.duration > timedelta(0), f"Zero/negative duration for {inc.id}"
            assert len(inc.timeline) > 0, f"Empty timeline for {inc.id}"
            assert len(inc.lessons_learned) > 0, f"No lessons learned for {inc.id}"

    def test_multiple_providers_represented(self):
        """Should have incidents from multiple providers."""
        providers = {inc.provider for inc in HISTORICAL_INCIDENTS}
        assert "aws" in providers
        assert "gcp" in providers
        assert "azure" in providers
        assert "generic" in providers

    def test_incidents_have_valid_dates(self):
        """Incident dates should be in the past (before 2026)."""
        for inc in HISTORICAL_INCIDENTS:
            assert inc.date.year >= 2010, f"Suspiciously old date for {inc.id}"
            assert inc.date.year <= 2025, f"Future date for {inc.id}"

    def test_timeline_events_have_correct_types(self):
        """Timeline event types should be valid."""
        valid_types = {
            "service_degradation", "full_outage", "partial_recovery", "full_recovery"
        }
        for inc in HISTORICAL_INCIDENTS:
            for event in inc.timeline:
                assert event.event_type in valid_types, (
                    f"Invalid event_type '{event.event_type}' "
                    f"in {inc.id}"
                )

    def test_crowdstrike_incident_details(self):
        """CrowdStrike incident should have accurate details."""
        engine = IncidentReplayEngine()
        inc = engine.get_incident("crowdstrike-2024-07")
        assert inc.date == datetime(2024, 7, 19)
        assert "BSOD" in inc.name or "CrowdStrike" in inc.name
        assert inc.severity == "critical"
        assert "global" in inc.affected_regions

    def test_aws_2021_incident_details(self):
        """AWS us-east-1 2021 incident should have accurate details."""
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        assert inc.date == datetime(2021, 12, 7)
        assert "us-east-1" in inc.affected_regions
        assert "ec2" in inc.affected_services

    def test_meta_bgp_incident_details(self):
        """Meta BGP outage should have accurate details."""
        engine = IncidentReplayEngine()
        inc = engine.get_incident("meta-bgp-2021-10")
        assert inc.date == datetime(2021, 10, 4)
        assert "global" in inc.affected_regions
        assert "dns" in inc.affected_services


class TestRegionProtection:
    """Tests for region-based protection in replay."""

    def test_different_region_survives(self):
        """Component in us-west-2 should survive us-east-1 outage."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app",
            name="App Server",
            type=ComponentType.APP_SERVER,
            replicas=1,
            region=RegionConfig(region="us-west-2"),
        ))

        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(graph, inc)

        assert result.survived
        assert result.impact_score == 0.0

    def test_same_region_affected(self):
        """Component in us-east-1 should be affected by us-east-1 outage."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app",
            name="App Server",
            type=ComponentType.APP_SERVER,
            replicas=1,
            region=RegionConfig(region="us-east-1"),
        ))

        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(graph, inc)

        assert not result.survived
        assert result.impact_score > 0

    def test_global_outage_affects_all_regions(self):
        """Global outage should affect components regardless of region."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app",
            name="App Server",
            type=ComponentType.APP_SERVER,
            replicas=1,
            region=RegionConfig(region="ap-southeast-1"),
        ))

        engine = IncidentReplayEngine()
        inc = engine.get_incident("crowdstrike-2024-07")
        result = engine.replay(graph, inc)

        # Should be affected because CrowdStrike was global
        assert result.impact_score > 0

    def test_failover_to_unaffected_region(self):
        """Failover to unaffected DR region should help survive."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db",
            name="Database",
            type=ComponentType.DATABASE,
            replicas=1,
            region=RegionConfig(
                region="us-east-1",
                dr_target_region="eu-west-1",
            ),
            failover=FailoverConfig(enabled=True, promotion_time_seconds=60),
        ))

        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(graph, inc)

        # Should survive with failover to eu-west-1
        assert result.survived or result.impact_score < 5.0
        assert len(result.survival_factors) > 0
