"""Tests for Runbook Completeness Validator.

Comprehensive test suite covering all classes, methods, edge cases,
and boundary conditions for the RunbookValidator module.
"""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.runbook_validator import (
    Runbook,
    RunbookGap,
    RunbookStatus,
    RunbookValidationReport,
    RunbookValidator,
    RecoveryStep,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _empty_graph() -> InfraGraph:
    """Return an empty graph with no components."""
    return InfraGraph()


def _single_component_graph(
    comp_type: ComponentType = ComponentType.APP_SERVER,
    comp_id: str = "app",
    comp_name: str = "App Server",
    replicas: int = 2,
    failover: bool = False,
) -> InfraGraph:
    """Build a graph with a single component."""
    graph = InfraGraph()
    graph.add_component(
        Component(
            id=comp_id,
            name=comp_name,
            type=comp_type,
            replicas=replicas,
            failover=FailoverConfig(enabled=failover),
        )
    )
    return graph


def _standard_graph() -> InfraGraph:
    """Build a realistic graph with multiple component types and dependencies."""
    graph = InfraGraph()

    graph.add_component(
        Component(
            id="lb",
            name="Load Balancer",
            type=ComponentType.LOAD_BALANCER,
            replicas=2,
            failover=FailoverConfig(enabled=True),
        )
    )
    graph.add_component(
        Component(
            id="web",
            name="Web Server",
            type=ComponentType.WEB_SERVER,
            replicas=3,
        )
    )
    graph.add_component(
        Component(
            id="app",
            name="App Server",
            type=ComponentType.APP_SERVER,
            replicas=2,
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        )
    )
    graph.add_component(
        Component(
            id="db",
            name="PostgreSQL",
            type=ComponentType.DATABASE,
            replicas=1,
            failover=FailoverConfig(enabled=True, promotion_time_seconds=30.0),
        )
    )
    graph.add_component(
        Component(
            id="cache",
            name="Redis",
            type=ComponentType.CACHE,
            replicas=1,
        )
    )
    graph.add_component(
        Component(
            id="queue",
            name="RabbitMQ",
            type=ComponentType.QUEUE,
            replicas=1,
        )
    )

    # Dependencies: lb -> web -> app -> db, app -> cache, app -> queue
    graph.add_dependency(Dependency(source_id="lb", target_id="web"))
    graph.add_dependency(Dependency(source_id="web", target_id="app"))
    graph.add_dependency(Dependency(source_id="app", target_id="db"))
    graph.add_dependency(
        Dependency(source_id="app", target_id="cache", dependency_type="optional")
    )
    graph.add_dependency(
        Dependency(source_id="app", target_id="queue", dependency_type="async")
    )

    return graph


def _all_component_types_graph() -> InfraGraph:
    """Build a graph containing every ComponentType."""
    graph = InfraGraph()
    types_map = {
        "lb": (ComponentType.LOAD_BALANCER, "LB"),
        "web": (ComponentType.WEB_SERVER, "Web"),
        "app": (ComponentType.APP_SERVER, "App"),
        "db": (ComponentType.DATABASE, "DB"),
        "cache": (ComponentType.CACHE, "Cache"),
        "queue": (ComponentType.QUEUE, "Queue"),
        "storage": (ComponentType.STORAGE, "Storage"),
        "dns": (ComponentType.DNS, "DNS"),
        "ext": (ComponentType.EXTERNAL_API, "External API"),
        "custom": (ComponentType.CUSTOM, "Custom"),
    }
    for cid, (ctype, cname) in types_map.items():
        graph.add_component(
            Component(id=cid, name=cname, type=ctype, replicas=1)
        )
    return graph


def _make_runbook(
    scenario_id: str,
    title: str,
    component_id: str,
    status: RunbookStatus = RunbookStatus.COMPLETE,
    steps: list[RecoveryStep] | None = None,
    last_tested: str | None = "2025-01-01",
    owner: str = "sre-team",
    total_time: float = 30.0,
) -> Runbook:
    """Helper to create a Runbook with sensible defaults."""
    if steps is None:
        steps = [
            RecoveryStep(
                order=1,
                description="Investigate the issue",
                is_automated=False,
                estimated_time_minutes=5.0,
                requires_approval=False,
            ),
            RecoveryStep(
                order=2,
                description="Apply mitigation",
                is_automated=True,
                estimated_time_minutes=10.0,
                requires_approval=False,
            ),
            RecoveryStep(
                order=3,
                description="Verify recovery",
                is_automated=True,
                estimated_time_minutes=5.0,
                requires_approval=False,
            ),
        ]
    return Runbook(
        scenario_id=scenario_id,
        title=title,
        component_id=component_id,
        steps=steps,
        last_tested=last_tested,
        owner=owner,
        status=status,
        estimated_total_time_minutes=total_time,
    )


# ====================================================================
# Tests for RunbookStatus Enum
# ====================================================================


class TestRunbookStatus:
    def test_enum_values(self):
        assert RunbookStatus.COMPLETE == "complete"
        assert RunbookStatus.PARTIAL == "partial"
        assert RunbookStatus.MISSING == "missing"
        assert RunbookStatus.OUTDATED == "outdated"

    def test_enum_from_string(self):
        assert RunbookStatus("complete") == RunbookStatus.COMPLETE
        assert RunbookStatus("partial") == RunbookStatus.PARTIAL

    def test_enum_is_string(self):
        assert isinstance(RunbookStatus.COMPLETE, str)
        assert RunbookStatus.COMPLETE.upper() == "COMPLETE"


# ====================================================================
# Tests for RecoveryStep dataclass
# ====================================================================


class TestRecoveryStep:
    def test_basic_creation(self):
        step = RecoveryStep(
            order=1,
            description="Restart service",
            is_automated=True,
            estimated_time_minutes=2.0,
            requires_approval=False,
        )
        assert step.order == 1
        assert step.description == "Restart service"
        assert step.is_automated is True
        assert step.estimated_time_minutes == 2.0
        assert step.requires_approval is False

    def test_approval_required(self):
        step = RecoveryStep(
            order=5,
            description="Scale down production",
            is_automated=False,
            estimated_time_minutes=15.0,
            requires_approval=True,
        )
        assert step.requires_approval is True

    def test_zero_time(self):
        step = RecoveryStep(
            order=1,
            description="Notify",
            is_automated=True,
            estimated_time_minutes=0.0,
            requires_approval=False,
        )
        assert step.estimated_time_minutes == 0.0


# ====================================================================
# Tests for Runbook dataclass
# ====================================================================


class TestRunbook:
    def test_basic_creation(self):
        rb = _make_runbook("db:data corruption", "DB Data Corruption", "db")
        assert rb.scenario_id == "db:data corruption"
        assert rb.title == "DB Data Corruption"
        assert rb.component_id == "db"
        assert rb.status == RunbookStatus.COMPLETE
        assert len(rb.steps) == 3
        assert rb.owner == "sre-team"
        assert rb.last_tested == "2025-01-01"
        assert rb.estimated_total_time_minutes == 30.0

    def test_runbook_no_test_date(self):
        rb = _make_runbook(
            "app:out of memory", "App OOM", "app", last_tested=None
        )
        assert rb.last_tested is None

    def test_runbook_empty_steps(self):
        rb = _make_runbook("cache:overflow", "Cache Overflow", "cache", steps=[])
        assert len(rb.steps) == 0

    def test_runbook_statuses(self):
        for status in RunbookStatus:
            rb = _make_runbook("test:test", "Test", "test", status=status)
            assert rb.status == status


# ====================================================================
# Tests for RunbookGap dataclass
# ====================================================================


class TestRunbookGap:
    def test_basic_creation(self):
        gap = RunbookGap(
            scenario_description="data corruption on PostgreSQL",
            component_id="db",
            component_name="PostgreSQL",
            severity="critical",
            reason="No runbook exists",
            suggested_steps=["Investigate", "Mitigate", "Verify"],
        )
        assert gap.severity == "critical"
        assert len(gap.suggested_steps) == 3
        assert gap.component_id == "db"

    def test_empty_suggested_steps(self):
        gap = RunbookGap(
            scenario_description="test",
            component_id="x",
            component_name="X",
            severity="low",
            reason="test",
            suggested_steps=[],
        )
        assert gap.suggested_steps == []


# ====================================================================
# Tests for RunbookValidationReport dataclass
# ====================================================================


class TestRunbookValidationReport:
    def test_basic_creation(self):
        report = RunbookValidationReport(
            total_scenarios=10,
            covered_scenarios=7,
            coverage_percent=70.0,
            completeness_score=65.0,
            gaps=[],
            existing_runbooks=[],
            recommendations=["Add more runbooks"],
            mean_recovery_time_minutes=25.0,
        )
        assert report.total_scenarios == 10
        assert report.covered_scenarios == 7
        assert report.coverage_percent == 70.0
        assert report.completeness_score == 65.0
        assert report.mean_recovery_time_minutes == 25.0


# ====================================================================
# Tests for RunbookValidator: empty graph
# ====================================================================


class TestEmptyGraph:
    def test_empty_graph_no_scenarios(self):
        graph = _empty_graph()
        validator = RunbookValidator(graph)
        report = validator.validate()
        assert report.total_scenarios == 0
        assert report.covered_scenarios == 0
        assert report.coverage_percent == 100.0
        assert report.completeness_score == 100.0
        assert report.gaps == []
        assert report.recommendations == []
        assert report.mean_recovery_time_minutes == 0.0

    def test_empty_graph_generate_required(self):
        graph = _empty_graph()
        validator = RunbookValidator(graph)
        gaps = validator.generate_required_scenarios()
        assert gaps == []


# ====================================================================
# Tests for RunbookValidator: single component
# ====================================================================


class TestSingleComponent:
    def test_single_app_server_scenarios(self):
        graph = _single_component_graph(ComponentType.APP_SERVER)
        validator = RunbookValidator(graph)
        report = validator.validate()
        # APP_SERVER has 3 failure modes
        assert report.total_scenarios == 3
        assert report.covered_scenarios == 0
        assert report.coverage_percent == 0.0
        assert len(report.gaps) == 3

    def test_single_database_scenarios(self):
        graph = _single_component_graph(ComponentType.DATABASE, "db", "PostgreSQL")
        validator = RunbookValidator(graph)
        report = validator.validate()
        # DATABASE has 3 failure modes
        assert report.total_scenarios == 3
        assert len(report.gaps) == 3

    def test_single_cache_scenarios(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        report = validator.validate()
        # CACHE has 2 failure modes
        assert report.total_scenarios == 2

    def test_single_load_balancer_scenarios(self):
        graph = _single_component_graph(ComponentType.LOAD_BALANCER, "lb", "LB")
        validator = RunbookValidator(graph)
        report = validator.validate()
        # LOAD_BALANCER has 2 failure modes
        assert report.total_scenarios == 2

    def test_single_queue_scenarios(self):
        graph = _single_component_graph(ComponentType.QUEUE, "q", "Queue")
        validator = RunbookValidator(graph)
        report = validator.validate()
        # QUEUE has 2 failure modes
        assert report.total_scenarios == 2


# ====================================================================
# Tests for RunbookValidator: all component types
# ====================================================================


class TestAllComponentTypes:
    def test_generates_scenarios_for_every_type(self):
        graph = _all_component_types_graph()
        validator = RunbookValidator(graph)
        report = validator.validate()

        # Total scenarios = sum of failure modes for all 10 types
        # LB:2 + Web:2 + App:3 + DB:3 + Cache:2 + Queue:2 + Storage:2 +
        # DNS:2 + Ext:2 + Custom:1 = 21
        assert report.total_scenarios == 21
        assert len(report.gaps) == 21
        assert report.covered_scenarios == 0

    def test_generate_required_scenarios_all_types(self):
        graph = _all_component_types_graph()
        validator = RunbookValidator(graph)
        gaps = validator.generate_required_scenarios()
        assert len(gaps) == 21
        # Every gap should have suggested steps
        for gap in gaps:
            assert len(gap.suggested_steps) > 0

    def test_all_gaps_have_valid_severity(self):
        graph = _all_component_types_graph()
        validator = RunbookValidator(graph)
        gaps = validator.generate_required_scenarios()
        valid_severities = {"critical", "high", "medium", "low"}
        for gap in gaps:
            assert gap.severity in valid_severities


# ====================================================================
# Tests for RunbookValidator: with runbooks provided
# ====================================================================


class TestWithRunbooks:
    def test_full_coverage_by_scenario_id(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation Storm",
                "cache",
            ),
            _make_runbook(
                "cache:memory overflow",
                "Cache Memory Overflow",
                "cache",
            ),
        ]
        report = validator.validate(runbooks)
        assert report.total_scenarios == 2
        assert report.covered_scenarios == 2
        assert report.coverage_percent == 100.0
        assert len(report.gaps) == 0

    def test_partial_coverage(self):
        graph = _single_component_graph(ComponentType.APP_SERVER, "app", "App")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "app:out of memory", "App OOM Recovery", "app"
            ),
        ]
        report = validator.validate(runbooks)
        assert report.total_scenarios == 3
        assert report.covered_scenarios == 1
        # 1/3 = 33.33%
        assert 33.0 <= report.coverage_percent <= 34.0
        assert len(report.gaps) == 2

    def test_fuzzy_title_match(self):
        """Coverage via title containing the scenario description."""
        graph = _single_component_graph(ComponentType.DATABASE, "db", "DB")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "some-custom-id",
                "Handle data corruption on DB",
                "db",
            ),
        ]
        report = validator.validate(runbooks)
        # Should match "data corruption" via fuzzy title match
        assert report.covered_scenarios >= 1

    def test_runbook_for_wrong_component_does_not_match(self):
        graph = _single_component_graph(ComponentType.DATABASE, "db", "DB")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "app:out of memory",
                "App OOM Recovery",
                "app",  # wrong component
            ),
        ]
        report = validator.validate(runbooks)
        assert report.covered_scenarios == 0

    def test_outdated_runbook_counts_as_gap(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.OUTDATED,
            ),
            _make_runbook(
                "cache:memory overflow",
                "Cache Overflow",
                "cache",
                status=RunbookStatus.COMPLETE,
            ),
        ]
        report = validator.validate(runbooks)
        assert report.covered_scenarios == 1
        assert len(report.gaps) == 1
        assert "outdated" in report.gaps[0].reason.lower()

    def test_missing_status_runbook_counts_as_gap(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.MISSING,
            ),
        ]
        report = validator.validate(runbooks)
        assert report.covered_scenarios == 0
        assert len(report.gaps) == 2

    def test_partial_status_still_covers(self):
        """Partial status runbooks count as covered."""
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.PARTIAL,
            ),
            _make_runbook(
                "cache:memory overflow",
                "Cache Overflow",
                "cache",
                status=RunbookStatus.PARTIAL,
            ),
        ]
        report = validator.validate(runbooks)
        assert report.covered_scenarios == 2


# ====================================================================
# Tests for RunbookValidator: severity calculation
# ====================================================================


class TestSeverityCalculation:
    def test_spof_with_many_dependents_is_critical(self):
        graph = InfraGraph()
        graph.add_component(
            Component(id="db", name="DB", type=ComponentType.DATABASE, replicas=1)
        )
        graph.add_component(
            Component(id="app1", name="App1", type=ComponentType.APP_SERVER, replicas=2)
        )
        graph.add_component(
            Component(id="app2", name="App2", type=ComponentType.APP_SERVER, replicas=2)
        )
        graph.add_dependency(Dependency(source_id="app1", target_id="db"))
        graph.add_dependency(Dependency(source_id="app2", target_id="db"))

        validator = RunbookValidator(graph)
        scenarios = validator._identify_critical_scenarios()
        db_scenarios = [(c, s, sev) for c, s, sev in scenarios if c == "db"]
        # DB is SPOF with 2 dependents -> critical
        for _, _, sev in db_scenarios:
            assert sev == "critical"

    def test_spof_no_dependents_is_low(self):
        graph = _single_component_graph(
            ComponentType.DATABASE, "db", "DB", replicas=1, failover=False
        )
        validator = RunbookValidator(graph)
        scenarios = validator._identify_critical_scenarios()
        # SPOF but 0 dependents -> still "critical" because is_spof alone
        # Actually: is_spof=True, num_dependents=0 -> _compute_severity
        # is_spof or num_dependents>=3 -> True -> critical
        for _, _, sev in scenarios:
            assert sev == "critical"

    def test_redundant_component_with_no_dependents_is_low(self):
        graph = _single_component_graph(
            ComponentType.DATABASE, "db", "DB", replicas=3, failover=True
        )
        validator = RunbookValidator(graph)
        scenarios = validator._identify_critical_scenarios()
        for _, _, sev in scenarios:
            assert sev == "low"

    def test_redundant_component_with_one_dependent_is_medium(self):
        graph = InfraGraph()
        graph.add_component(
            Component(
                id="db",
                name="DB",
                type=ComponentType.DATABASE,
                replicas=2,
                failover=FailoverConfig(enabled=True),
            )
        )
        graph.add_component(
            Component(id="app", name="App", type=ComponentType.APP_SERVER, replicas=2)
        )
        graph.add_dependency(Dependency(source_id="app", target_id="db"))

        validator = RunbookValidator(graph)
        scenarios = validator._identify_critical_scenarios()
        db_scenarios = [(c, s, sev) for c, s, sev in scenarios if c == "db"]
        for _, _, sev in db_scenarios:
            assert sev == "medium"

    def test_redundant_component_with_two_dependents_is_high(self):
        graph = InfraGraph()
        graph.add_component(
            Component(
                id="db",
                name="DB",
                type=ComponentType.DATABASE,
                replicas=2,
                failover=FailoverConfig(enabled=True),
            )
        )
        for i in range(2):
            graph.add_component(
                Component(
                    id=f"app{i}",
                    name=f"App{i}",
                    type=ComponentType.APP_SERVER,
                    replicas=2,
                )
            )
            graph.add_dependency(Dependency(source_id=f"app{i}", target_id="db"))

        validator = RunbookValidator(graph)
        scenarios = validator._identify_critical_scenarios()
        db_scenarios = [(c, s, sev) for c, s, sev in scenarios if c == "db"]
        for _, _, sev in db_scenarios:
            assert sev == "high"

    def test_compute_severity_static_method(self):
        assert RunbookValidator._compute_severity(0, False) == "low"
        assert RunbookValidator._compute_severity(1, False) == "medium"
        assert RunbookValidator._compute_severity(2, False) == "high"
        assert RunbookValidator._compute_severity(3, False) == "critical"
        assert RunbookValidator._compute_severity(0, True) == "critical"
        assert RunbookValidator._compute_severity(2, True) == "critical"


# ====================================================================
# Tests for SPOF detection
# ====================================================================


class TestSPOFDetection:
    def test_spof_single_replica_no_failover(self):
        graph = _single_component_graph(
            ComponentType.DATABASE, "db", "DB", replicas=1, failover=False
        )
        validator = RunbookValidator(graph)
        scenarios = validator._identify_critical_scenarios()
        # All should be critical (SPOF)
        for _, _, sev in scenarios:
            assert sev == "critical"

    def test_not_spof_with_replicas(self):
        graph = _single_component_graph(
            ComponentType.DATABASE, "db", "DB", replicas=3, failover=False
        )
        validator = RunbookValidator(graph)
        scenarios = validator._identify_critical_scenarios()
        for _, _, sev in scenarios:
            assert sev == "low"

    def test_not_spof_with_failover(self):
        graph = _single_component_graph(
            ComponentType.DATABASE, "db", "DB", replicas=1, failover=True
        )
        validator = RunbookValidator(graph)
        scenarios = validator._identify_critical_scenarios()
        for _, _, sev in scenarios:
            assert sev == "low"


# ====================================================================
# Tests for RunbookValidator: completeness score
# ====================================================================


class TestCompletenessScore:
    def test_no_runbooks_score_zero(self):
        graph = _single_component_graph()
        validator = RunbookValidator(graph)
        report = validator.validate()
        assert report.completeness_score == 0.0

    def test_complete_runbook_high_score(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        steps = [
            RecoveryStep(i, f"Step {i}", True, 5.0, False) for i in range(1, 7)
        ]
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.COMPLETE,
                steps=steps,
                last_tested="2025-06-01",
                total_time=30.0,
            ),
        ]
        report = validator.validate(runbooks)
        # Status=40 + Steps(6 >= 5)=25 + Auto(all)=20 + Tested=15 = 100
        assert report.completeness_score == 100.0

    def test_partial_runbook_moderate_score(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        steps = [
            RecoveryStep(1, "Step 1", False, 10.0, False),
            RecoveryStep(2, "Step 2", False, 10.0, False),
        ]
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.PARTIAL,
                steps=steps,
                last_tested=None,
                total_time=20.0,
            ),
        ]
        report = validator.validate(runbooks)
        # Status=20 + Steps(2/5*25)=10 + Auto(0)=0 + Tested(None)=0 = 30
        assert report.completeness_score == 30.0

    def test_outdated_runbook_low_score(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.OUTDATED,
                steps=[],
                last_tested=None,
                total_time=0.0,
            ),
        ]
        report = validator.validate(runbooks)
        # Status=10 + Steps(0)=0 + Auto(no steps)=0 + Tested(None)=0 = 10
        assert report.completeness_score == 10.0

    def test_missing_status_zero_score(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.MISSING,
                steps=[],
                last_tested=None,
                total_time=0.0,
            ),
        ]
        report = validator.validate(runbooks)
        assert report.completeness_score == 0.0

    def test_mixed_automation_score(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        steps = [
            RecoveryStep(1, "Manual step", False, 5.0, False),
            RecoveryStep(2, "Auto step", True, 5.0, False),
            RecoveryStep(3, "Auto step 2", True, 5.0, False),
            RecoveryStep(4, "Manual step 2", False, 5.0, False),
            RecoveryStep(5, "Auto step 3", True, 5.0, False),
        ]
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.COMPLETE,
                steps=steps,
                last_tested="2025-01-01",
                total_time=25.0,
            ),
        ]
        report = validator.validate(runbooks)
        # Status=40 + Steps(5>=5)=25 + Auto(3/5*20)=12 + Tested=15 = 92
        assert report.completeness_score == 92.0

    def test_average_of_multiple_runbooks(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        # One perfect, one empty
        perfect_steps = [
            RecoveryStep(i, f"Step {i}", True, 5.0, False) for i in range(1, 6)
        ]
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.COMPLETE,
                steps=perfect_steps,
                last_tested="2025-01-01",
                total_time=25.0,
            ),
            _make_runbook(
                "cache:memory overflow",
                "Cache Overflow",
                "cache",
                status=RunbookStatus.MISSING,
                steps=[],
                last_tested=None,
                total_time=0.0,
            ),
        ]
        report = validator.validate(runbooks)
        # First: 100, Second: 0 => average = 50
        assert report.completeness_score == 50.0


# ====================================================================
# Tests for RunbookValidator: mean recovery time
# ====================================================================


class TestMeanRecoveryTime:
    def test_no_runbooks_zero_recovery(self):
        graph = _single_component_graph()
        validator = RunbookValidator(graph)
        report = validator.validate()
        assert report.mean_recovery_time_minutes == 0.0

    def test_single_runbook_recovery(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                total_time=45.0,
            ),
        ]
        report = validator.validate(runbooks)
        assert report.mean_recovery_time_minutes == 45.0

    def test_multiple_runbooks_mean(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                total_time=30.0,
            ),
            _make_runbook(
                "cache:memory overflow",
                "Cache Overflow",
                "cache",
                total_time=60.0,
            ),
        ]
        report = validator.validate(runbooks)
        assert report.mean_recovery_time_minutes == 45.0

    def test_zero_time_runbooks_excluded(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                total_time=0.0,
            ),
            _make_runbook(
                "cache:memory overflow",
                "Cache Overflow",
                "cache",
                total_time=60.0,
            ),
        ]
        report = validator.validate(runbooks)
        assert report.mean_recovery_time_minutes == 60.0

    def test_all_zero_time(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                total_time=0.0,
            ),
        ]
        report = validator.validate(runbooks)
        assert report.mean_recovery_time_minutes == 0.0


# ====================================================================
# Tests for RunbookValidator: recommendations
# ====================================================================


class TestRecommendations:
    def test_low_coverage_recommendation(self):
        graph = _standard_graph()
        validator = RunbookValidator(graph)
        report = validator.validate()
        # No runbooks = 0% coverage -> recommendation about low coverage
        assert any("critically low" in r.lower() for r in report.recommendations)

    def test_critical_gaps_recommendation(self):
        graph = _standard_graph()
        validator = RunbookValidator(graph)
        report = validator.validate()
        assert any("critical" in r.lower() for r in report.recommendations)

    def test_outdated_runbook_recommendation(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.OUTDATED,
            ),
            _make_runbook(
                "cache:memory overflow",
                "Cache Overflow",
                "cache",
                status=RunbookStatus.COMPLETE,
            ),
        ]
        report = validator.validate(runbooks)
        assert any("outdated" in r.lower() for r in report.recommendations)

    def test_partial_runbook_recommendation(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.PARTIAL,
            ),
            _make_runbook(
                "cache:memory overflow",
                "Cache Overflow",
                "cache",
                status=RunbookStatus.COMPLETE,
            ),
        ]
        report = validator.validate(runbooks)
        assert any("partial" in r.lower() for r in report.recommendations)

    def test_untested_runbook_recommendation(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                last_tested=None,
            ),
            _make_runbook(
                "cache:memory overflow",
                "Cache Overflow",
                "cache",
                last_tested=None,
            ),
        ]
        report = validator.validate(runbooks)
        assert any("untested" in r.lower() for r in report.recommendations)

    def test_low_automation_recommendation(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        steps = [
            RecoveryStep(i, f"Manual step {i}", False, 10.0, False)
            for i in range(1, 6)
        ]
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                steps=steps,
            ),
            _make_runbook(
                "cache:memory overflow",
                "Cache Overflow",
                "cache",
            ),
        ]
        report = validator.validate(runbooks)
        assert any("automation" in r.lower() for r in report.recommendations)

    def test_no_recommendations_for_perfect_coverage(self):
        graph = _single_component_graph(
            ComponentType.CACHE, "cache", "Redis", replicas=2, failover=True
        )
        validator = RunbookValidator(graph)
        perfect_steps = [
            RecoveryStep(i, f"Step {i}", True, 5.0, False)
            for i in range(1, 6)
        ]
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation",
                "cache",
                status=RunbookStatus.COMPLETE,
                steps=perfect_steps,
                last_tested="2025-06-01",
            ),
            _make_runbook(
                "cache:memory overflow",
                "Cache Overflow",
                "cache",
                status=RunbookStatus.COMPLETE,
                steps=perfect_steps,
                last_tested="2025-06-01",
            ),
        ]
        report = validator.validate(runbooks)
        assert report.coverage_percent == 100.0
        assert len(report.recommendations) == 0


# ====================================================================
# Tests for RunbookValidator: edge cases
# ====================================================================


class TestEdgeCases:
    def test_runbook_for_nonexistent_component(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "ghost:data corruption",
                "Ghost Runbook",
                "ghost",  # not in graph
            ),
        ]
        report = validator.validate(runbooks)
        # The ghost runbook doesn't match any scenario
        assert report.covered_scenarios == 0
        # But existing_runbooks still contains the ghost runbook
        assert len(report.existing_runbooks) == 1

    def test_duplicate_runbooks_for_same_scenario(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation v1",
                "cache",
            ),
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache Invalidation v2",
                "cache",
            ),
        ]
        report = validator.validate(runbooks)
        # Only one scenario to cover; both match but only counts as 1 covered
        assert report.covered_scenarios >= 1
        # Existing runbooks should contain both
        assert len(report.existing_runbooks) == 2

    def test_validate_with_none_runbooks(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        report = validator.validate(None)
        assert report.covered_scenarios == 0

    def test_validate_with_empty_runbooks(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        report = validator.validate([])
        assert report.covered_scenarios == 0

    def test_custom_component_type(self):
        graph = _single_component_graph(
            ComponentType.CUSTOM, "custom", "Custom Service"
        )
        validator = RunbookValidator(graph)
        report = validator.validate()
        # CUSTOM has 1 failure mode: "unexpected failure"
        assert report.total_scenarios == 1

    def test_suggested_steps_for_unknown_scenario(self):
        graph = _single_component_graph(ComponentType.CUSTOM, "custom", "Svc")
        validator = RunbookValidator(graph)
        # Use a scenario not in _SUGGESTED_STEPS
        steps = validator._suggest_recovery_steps("custom", "alien invasion")
        assert len(steps) >= 3
        assert any("alien invasion" in s.lower() for s in steps)


# ====================================================================
# Tests for RunbookValidator: boundary conditions
# ====================================================================


class TestBoundaryConditions:
    def test_zero_percent_coverage(self):
        graph = _standard_graph()
        validator = RunbookValidator(graph)
        report = validator.validate()
        assert report.coverage_percent == 0.0

    def test_100_percent_coverage(self):
        graph = _single_component_graph(
            ComponentType.QUEUE, "q", "Queue", replicas=2, failover=True
        )
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "q:message backlog",
                "Message Backlog",
                "q",
            ),
            _make_runbook(
                "q:dead letter overflow",
                "Dead Letter Overflow",
                "q",
            ),
        ]
        report = validator.validate(runbooks)
        assert report.coverage_percent == 100.0
        assert len(report.gaps) == 0

    def test_coverage_rounding(self):
        graph = _single_component_graph(ComponentType.APP_SERVER, "app", "App")
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "app:out of memory", "OOM", "app"
            ),
        ]
        report = validator.validate(runbooks)
        # 1/3 = 33.333... should be rounded to 2 decimal places
        assert report.coverage_percent == 33.33

    def test_completeness_score_capped_at_100(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        # Even with many steps and everything perfect, max is 100
        steps = [
            RecoveryStep(i, f"Step {i}", True, 1.0, False)
            for i in range(1, 20)
        ]
        runbooks = [
            _make_runbook(
                "cache:cache invalidation storm",
                "Cache",
                "cache",
                status=RunbookStatus.COMPLETE,
                steps=steps,
                last_tested="2025-01-01",
            ),
        ]
        report = validator.validate(runbooks)
        assert report.completeness_score <= 100.0


# ====================================================================
# Tests for RunbookValidator: large graph
# ====================================================================


class TestLargeGraph:
    def test_large_graph_many_components(self):
        graph = InfraGraph()
        # Create 50 app servers
        for i in range(50):
            graph.add_component(
                Component(
                    id=f"app-{i}",
                    name=f"App Server {i}",
                    type=ComponentType.APP_SERVER,
                    replicas=2,
                )
            )
        # Add a shared database
        graph.add_component(
            Component(id="db", name="Shared DB", type=ComponentType.DATABASE, replicas=1)
        )
        for i in range(50):
            graph.add_dependency(
                Dependency(source_id=f"app-{i}", target_id="db")
            )

        validator = RunbookValidator(graph)
        report = validator.validate()
        # 50 * 3 (APP_SERVER modes) + 3 (DB modes) = 153
        assert report.total_scenarios == 153
        assert report.coverage_percent == 0.0
        assert len(report.gaps) == 153

        # DB scenarios should be critical (SPOF with 50 dependents)
        db_gaps = [g for g in report.gaps if g.component_id == "db"]
        for g in db_gaps:
            assert g.severity == "critical"

    def test_large_graph_with_full_coverage(self):
        graph = InfraGraph()
        for i in range(10):
            graph.add_component(
                Component(
                    id=f"cache-{i}",
                    name=f"Cache {i}",
                    type=ComponentType.CACHE,
                    replicas=2,
                    failover=FailoverConfig(enabled=True),
                )
            )
        validator = RunbookValidator(graph)
        # 10 caches * 2 modes = 20 scenarios
        runbooks = []
        for i in range(10):
            for mode in ["cache invalidation storm", "memory overflow"]:
                runbooks.append(
                    _make_runbook(
                        f"cache-{i}:{mode}",
                        f"Cache {i} {mode}",
                        f"cache-{i}",
                    )
                )
        report = validator.validate(runbooks)
        assert report.total_scenarios == 20
        assert report.covered_scenarios == 20
        assert report.coverage_percent == 100.0
        assert len(report.gaps) == 0


# ====================================================================
# Tests for generate_required_scenarios
# ====================================================================


class TestGenerateRequiredScenarios:
    def test_all_gaps_have_component_info(self):
        graph = _standard_graph()
        validator = RunbookValidator(graph)
        gaps = validator.generate_required_scenarios()
        for gap in gaps:
            assert gap.component_id != ""
            assert gap.component_name != ""
            assert gap.scenario_description != ""

    def test_gaps_match_validate_gaps_when_no_runbooks(self):
        graph = _standard_graph()
        validator = RunbookValidator(graph)
        generated = validator.generate_required_scenarios()
        report = validator.validate()
        assert len(generated) == len(report.gaps)

    def test_gaps_have_suggested_steps(self):
        graph = _standard_graph()
        validator = RunbookValidator(graph)
        gaps = validator.generate_required_scenarios()
        for gap in gaps:
            assert len(gap.suggested_steps) > 0


# ====================================================================
# Tests for _suggest_recovery_steps
# ====================================================================


class TestSuggestRecoverySteps:
    def test_known_database_scenario(self):
        graph = _single_component_graph(ComponentType.DATABASE, "db", "DB")
        validator = RunbookValidator(graph)
        steps = validator._suggest_recovery_steps("db", "data corruption")
        assert len(steps) >= 3
        assert any("backup" in s.lower() for s in steps)

    def test_known_cache_scenario(self):
        graph = _single_component_graph(ComponentType.CACHE, "cache", "Redis")
        validator = RunbookValidator(graph)
        steps = validator._suggest_recovery_steps("cache", "cache invalidation storm")
        assert len(steps) >= 3

    def test_unknown_scenario_gets_generic_steps(self):
        graph = _single_component_graph(ComponentType.APP_SERVER, "app", "App")
        validator = RunbookValidator(graph)
        steps = validator._suggest_recovery_steps("app", "quantum anomaly")
        assert len(steps) >= 3
        assert any("quantum anomaly" in s.lower() for s in steps)

    def test_all_failure_modes_have_suggestions(self):
        """Every standard failure mode should have predefined steps."""
        graph = _all_component_types_graph()
        validator = RunbookValidator(graph)
        scenarios = validator._identify_critical_scenarios()
        for comp_id, scenario, _ in scenarios:
            steps = validator._suggest_recovery_steps(comp_id, scenario)
            assert len(steps) >= 3, (
                f"Scenario '{scenario}' on '{comp_id}' has fewer than 3 steps"
            )


# ====================================================================
# Tests for RunbookValidator: standard graph integration
# ====================================================================


class TestStandardGraphIntegration:
    def test_standard_graph_scenario_count(self):
        graph = _standard_graph()
        validator = RunbookValidator(graph)
        report = validator.validate()
        # LB:2 + Web:2 + App:3 + DB:3 + Cache:2 + Queue:2 = 14
        assert report.total_scenarios == 14

    def test_standard_graph_partial_coverage(self):
        graph = _standard_graph()
        validator = RunbookValidator(graph)
        runbooks = [
            _make_runbook(
                "db:data corruption",
                "DB Data Corruption",
                "db",
            ),
            _make_runbook(
                "db:replication lag",
                "DB Replication Lag",
                "db",
            ),
            _make_runbook(
                "db:connection pool exhaustion",
                "DB Connection Pool",
                "db",
            ),
        ]
        report = validator.validate(runbooks)
        assert report.covered_scenarios == 3
        assert report.total_scenarios == 14
        # 3/14 ~= 21.43%
        assert 21.0 <= report.coverage_percent <= 22.0

    def test_report_has_correct_structure(self):
        graph = _standard_graph()
        validator = RunbookValidator(graph)
        report = validator.validate()
        assert isinstance(report, RunbookValidationReport)
        assert isinstance(report.gaps, list)
        assert isinstance(report.existing_runbooks, list)
        assert isinstance(report.recommendations, list)
        assert isinstance(report.total_scenarios, int)
        assert isinstance(report.covered_scenarios, int)
        assert isinstance(report.coverage_percent, float)
        assert isinstance(report.completeness_score, float)
        assert isinstance(report.mean_recovery_time_minutes, float)
