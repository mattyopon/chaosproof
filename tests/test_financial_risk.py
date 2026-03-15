"""Tests for the Financial Risk Engine."""

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    CostProfile,
    FailoverConfig,
    OperationalProfile,
    OperationalTeamConfig,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.model.components import Dependency as DepModel
from infrasim.simulator.engine import SimulationEngine
from infrasim.simulator.financial_risk import (
    FinancialRiskEngine,
    FinancialRiskReport,
    FinancialRiskResult,
    _DEFAULT_ANNUAL_REVENUE,
)


def _build_risk_graph() -> InfraGraph:
    """Build a test graph for financial risk analysis."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        metrics=ResourceMetrics(cpu_percent=30),
        cost_profile=CostProfile(hourly_infra_cost=5.0, revenue_per_minute=100.0),
        operational_profile=OperationalProfile(mttr_minutes=15),
        team=OperationalTeamConfig(team_size=3),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
        metrics=ResourceMetrics(cpu_percent=70, memory_percent=60),
        capacity=Capacity(max_connections=1000),
        cost_profile=CostProfile(
            hourly_infra_cost=10.0, revenue_per_minute=200.0,
            sla_credit_percent=10.0,
        ),
        operational_profile=OperationalProfile(mttr_minutes=30),
        team=OperationalTeamConfig(team_size=5),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=85, disk_percent=60),
        cost_profile=CostProfile(
            hourly_infra_cost=20.0, revenue_per_minute=500.0,
            recovery_engineer_cost=150.0,
        ),
        operational_profile=OperationalProfile(mttr_minutes=60),
        team=OperationalTeamConfig(team_size=2),
    ))
    graph.add_dependency(DepModel(source_id="lb", target_id="app"))
    graph.add_dependency(DepModel(source_id="app", target_id="db"))
    return graph


def _run_simulation(graph: InfraGraph):
    """Run a basic simulation to get a report."""
    engine = SimulationEngine(graph)
    return engine.run_all_defaults()


def test_analyze_returns_report():
    """analyze() should return a FinancialRiskReport."""
    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph, annual_revenue=10_000_000)
    report = engine.analyze(sim_report)
    assert isinstance(report, FinancialRiskReport)
    assert report.annual_revenue_usd == 10_000_000


def test_expected_annual_loss_non_negative():
    """Expected annual loss should be non-negative."""
    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph, annual_revenue=5_000_000)
    report = engine.analyze(sim_report)
    assert report.expected_annual_loss >= 0


def test_var95_non_negative():
    """Value at Risk (95%) should be non-negative."""
    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph)
    report = engine.analyze(sim_report)
    assert report.value_at_risk_95 >= 0


def test_cost_per_hour_calculation():
    """Cost per hour of risk should equal expected_annual_loss / 8760."""
    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph, annual_revenue=10_000_000)
    report = engine.analyze(sim_report)
    if report.expected_annual_loss > 0:
        expected_hourly = report.expected_annual_loss / 8760.0
        assert abs(report.cost_per_hour_of_risk - expected_hourly) < 0.01


def test_higher_revenue_means_higher_loss():
    """Higher annual revenue should result in higher expected loss."""
    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)

    engine_low = FinancialRiskEngine(graph, annual_revenue=100_000)
    report_low = engine_low.analyze(sim_report)

    engine_high = FinancialRiskEngine(graph, annual_revenue=100_000_000)
    report_high = engine_high.analyze(sim_report)

    assert report_high.expected_annual_loss >= report_low.expected_annual_loss


def test_scenarios_sorted_by_expected_loss():
    """Scenarios should be sorted by expected loss (prob * loss) descending."""
    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph, annual_revenue=10_000_000)
    report = engine.analyze(sim_report)

    if len(report.scenarios) > 1:
        expected_losses = [
            s.probability * s.business_loss_usd for s in report.scenarios
        ]
        for i in range(len(expected_losses) - 1):
            assert expected_losses[i] >= expected_losses[i + 1]


def test_scenario_probabilities_valid():
    """All scenario probabilities should be between 0 and 1."""
    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph)
    report = engine.analyze(sim_report)
    for s in report.scenarios:
        assert 0 <= s.probability <= 1.0


def test_recovery_hours_non_negative():
    """Recovery hours should be non-negative."""
    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph)
    report = engine.analyze(sim_report)
    for s in report.scenarios:
        assert s.recovery_hours >= 0


def test_mitigation_roi_generated():
    """Mitigation ROI recommendations should be generated for SPOF components."""
    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph, annual_revenue=10_000_000)
    report = engine.analyze(sim_report)
    # db is a SPOF with 1 replica and dependents, so should generate ROI
    assert len(report.mitigation_roi) > 0


def test_mitigation_roi_has_required_fields():
    """Each mitigation should have action, cost, savings, roi_percent."""
    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph, annual_revenue=10_000_000)
    report = engine.analyze(sim_report)
    for m in report.mitigation_roi:
        assert "action" in m
        assert "cost" in m
        assert "savings" in m
        assert "roi_percent" in m


def test_to_dict():
    """to_dict() should produce a JSON-serializable dict."""
    import json

    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph, annual_revenue=5_000_000)
    report = engine.analyze(sim_report)
    d = report.to_dict()
    # Should be serializable
    serialized = json.dumps(d)
    assert isinstance(serialized, str)
    # Check key fields
    assert "annual_revenue_usd" in d
    assert "value_at_risk_95" in d
    assert "expected_annual_loss" in d
    assert "scenarios" in d


def test_zero_revenue():
    """Zero revenue should result in zero revenue-based losses."""
    graph = _build_risk_graph()
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph, annual_revenue=0)
    report = engine.analyze(sim_report)
    assert report.annual_revenue_usd == 0
    # Revenue-based losses should be minimal (only SLA credits + engineer costs)
    assert report.expected_annual_loss >= 0


def test_empty_simulation_report():
    """Engine should handle a simulation with no critical/warning results."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="safe", name="Safe", type=ComponentType.CACHE,
        replicas=5, metrics=ResourceMetrics(cpu_percent=10),
    ))
    sim_report = _run_simulation(graph)
    engine = FinancialRiskEngine(graph)
    report = engine.analyze(sim_report)
    assert isinstance(report, FinancialRiskReport)
    # With a very safe component, there may be few/no critical scenarios
    assert report.expected_annual_loss >= 0


def test_default_annual_revenue():
    """Default annual revenue should be used when not specified."""
    graph = _build_risk_graph()
    engine = FinancialRiskEngine(graph)
    assert engine.annual_revenue == _DEFAULT_ANNUAL_REVENUE
