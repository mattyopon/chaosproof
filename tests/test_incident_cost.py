"""Tests for incident cost calculator."""

from __future__ import annotations

import pytest

from infrasim.model.components import Component, ComponentType, Dependency, HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.incident_cost import (
    CostBreakdown,
    CostCategory,
    CostReport,
    ComponentCost,
    IncidentCostCalculator,
    ScenarioCost,
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
    backup: bool = False,
    pci: bool = False,
    pii: bool = False,
    revenue_pm: float = 0.0,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    if failover:
        c.failover.enabled = True
    c.security.backup_enabled = backup
    c.compliance_tags.pci_scope = pci
    c.compliance_tags.contains_pii = pii
    c.cost_profile.revenue_per_minute = revenue_pm
    return c


def _simple_graph() -> InfraGraph:
    g = InfraGraph()
    g.add_component(_comp("api", "API Server", replicas=2))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE, revenue_pm=500.0))
    g.add_component(_comp("cache", "Cache", ComponentType.CACHE, replicas=2))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    g.add_dependency(Dependency(source_id="api", target_id="cache"))
    return g


# ---------------------------------------------------------------------------
# Tests: calculate_component_cost
# ---------------------------------------------------------------------------


class TestComponentCost:
    def test_basic_cost(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("api", "API Server"))
        cost = calc.calculate_component_cost(g, "api", downtime_minutes=60)
        assert cost is not None
        assert cost.total_cost_usd > 0
        assert cost.downtime_minutes == 60

    def test_nonexistent_component(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        cost = calc.calculate_component_cost(g, "nonexistent")
        assert cost is None

    def test_revenue_loss_category(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("api", "API", revenue_pm=200.0))
        cost = calc.calculate_component_cost(g, "api", downtime_minutes=60)
        assert cost is not None
        rev = [b for b in cost.breakdowns if b.category == CostCategory.REVENUE_LOSS]
        assert len(rev) == 1
        assert rev[0].amount_usd == 12000.0  # 200 * 60

    def test_sla_credits_triggered(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        cost = calc.calculate_component_cost(g, "api", downtime_minutes=60)
        assert cost is not None
        sla = [b for b in cost.breakdowns if b.category == CostCategory.SLA_CREDITS]
        assert len(sla) == 1  # 60 > 43 minutes

    def test_sla_credits_not_triggered(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        cost = calc.calculate_component_cost(g, "api", downtime_minutes=30)
        assert cost is not None
        sla = [b for b in cost.breakdowns if b.category == CostCategory.SLA_CREDITS]
        assert len(sla) == 0  # 30 < 43 minutes

    def test_engineer_time_cost(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        cost = calc.calculate_component_cost(g, "api", downtime_minutes=60)
        assert cost is not None
        eng = [b for b in cost.breakdowns if b.category == CostCategory.ENGINEER_TIME]
        assert len(eng) == 1
        assert eng[0].amount_usd > 0

    def test_customer_churn_cost(self):
        calc = IncidentCostCalculator(default_customer_count=10000)
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        cost = calc.calculate_component_cost(g, "api", downtime_minutes=120)
        assert cost is not None
        churn = [b for b in cost.breakdowns if b.category == CostCategory.CUSTOMER_CHURN]
        assert len(churn) == 1
        assert churn[0].amount_usd > 0

    def test_data_loss_for_db_without_backup(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, backup=False))
        cost = calc.calculate_component_cost(g, "db", downtime_minutes=60)
        assert cost is not None
        dl = [b for b in cost.breakdowns if b.category == CostCategory.DATA_LOSS]
        assert len(dl) == 1

    def test_no_data_loss_with_backup(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, backup=True))
        cost = calc.calculate_component_cost(g, "db", downtime_minutes=60)
        assert cost is not None
        dl = [b for b in cost.breakdowns if b.category == CostCategory.DATA_LOSS]
        assert len(dl) == 0

    def test_regulatory_fine_pci(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("pay", "Payment", pci=True))
        cost = calc.calculate_component_cost(g, "pay", downtime_minutes=60)
        assert cost is not None
        reg = [b for b in cost.breakdowns if b.category == CostCategory.REGULATORY_FINE]
        assert len(reg) == 1

    def test_regulatory_fine_pii(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("user", "UserDB", pii=True))
        cost = calc.calculate_component_cost(g, "user", downtime_minutes=60)
        assert cost is not None
        reg = [b for b in cost.breakdowns if b.category == CostCategory.REGULATORY_FINE]
        assert len(reg) == 1

    def test_risk_adjusted_with_replicas(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("api1", "API-1", replicas=1))
        g.add_component(_comp("api3", "API-3", replicas=3))
        cost1 = calc.calculate_component_cost(g, "api1", downtime_minutes=60)
        cost3 = calc.calculate_component_cost(g, "api3", downtime_minutes=60)
        assert cost1 is not None and cost3 is not None
        assert cost3.risk_adjusted_cost < cost1.risk_adjusted_cost

    def test_risk_adjusted_with_failover(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("db1", "DB-No-FO", ComponentType.DATABASE))
        g.add_component(_comp("db2", "DB-FO", ComponentType.DATABASE, failover=True))
        cost1 = calc.calculate_component_cost(g, "db1", downtime_minutes=60)
        cost2 = calc.calculate_component_cost(g, "db2", downtime_minutes=60)
        assert cost1 is not None and cost2 is not None
        assert cost2.risk_adjusted_cost < cost1.risk_adjusted_cost


# ---------------------------------------------------------------------------
# Tests: calculate_scenario_cost
# ---------------------------------------------------------------------------


class TestScenarioCost:
    def test_scenario_cost(self):
        calc = IncidentCostCalculator()
        g = _simple_graph()
        scenario = calc.calculate_scenario_cost(g, "db", downtime_minutes=60)
        assert scenario is not None
        assert scenario.total_cost_usd > 0
        assert scenario.cost_per_minute > 0

    def test_scenario_nonexistent(self):
        calc = IncidentCostCalculator()
        g = _simple_graph()
        scenario = calc.calculate_scenario_cost(g, "nonexistent")
        assert scenario is None

    def test_scenario_includes_cascading(self):
        calc = IncidentCostCalculator()
        g = _simple_graph()
        scenario = calc.calculate_scenario_cost(g, "db", downtime_minutes=60)
        assert scenario is not None
        # DB failure should affect API (its dependent)
        names = [c.component_name for c in scenario.component_costs]
        assert "Database" in names

    def test_scenario_severity_classification(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("api", "API", revenue_pm=5000.0))
        scenario = calc.calculate_scenario_cost(g, "api", downtime_minutes=60)
        assert scenario is not None
        assert scenario.severity in ("SEV1", "SEV2", "SEV3", "SEV4")


# ---------------------------------------------------------------------------
# Tests: full_analysis
# ---------------------------------------------------------------------------


class TestFullAnalysis:
    def test_full_analysis(self):
        calc = IncidentCostCalculator()
        g = _simple_graph()
        report = calc.full_analysis(g)
        assert len(report.component_costs) == 3
        assert report.total_annual_risk_usd >= 0
        assert report.highest_risk_component != "N/A"

    def test_empty_graph(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        report = calc.full_analysis(g)
        assert len(report.component_costs) == 0
        assert report.total_annual_risk_usd == 0
        assert report.highest_risk_component == "N/A"

    def test_report_has_categories(self):
        calc = IncidentCostCalculator()
        g = _simple_graph()
        report = calc.full_analysis(g)
        assert "revenue_loss" in report.cost_by_category

    def test_report_has_roi(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, revenue_pm=1000.0))
        report = calc.full_analysis(g)
        assert len(report.roi_of_improvements) >= 0

    def test_report_recommendations(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, revenue_pm=5000.0))
        report = calc.full_analysis(g, downtime_minutes=120)
        assert len(report.recommendations) > 0

    def test_report_data_loss_recommendation(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        report = calc.full_analysis(g)
        backup_recs = [r for r in report.recommendations if "backup" in r.lower()]
        assert len(backup_recs) >= 1


# ---------------------------------------------------------------------------
# Tests: Custom parameters
# ---------------------------------------------------------------------------


class TestCustomParameters:
    def test_custom_revenue(self):
        calc = IncidentCostCalculator(default_revenue_per_minute=1000.0)
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        cost = calc.calculate_component_cost(g, "api", downtime_minutes=60)
        assert cost is not None
        rev = [b for b in cost.breakdowns if b.category == CostCategory.REVENUE_LOSS]
        assert rev[0].amount_usd == 60000.0

    def test_custom_customer_count(self):
        calc = IncidentCostCalculator(default_customer_count=50000)
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        cost = calc.calculate_component_cost(g, "api", downtime_minutes=120)
        assert cost is not None


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_cost_categories(self):
        assert len(CostCategory) == 7

    def test_category_values(self):
        assert CostCategory.REVENUE_LOSS.value == "revenue_loss"
        assert CostCategory.SLA_CREDITS.value == "sla_credits"
        assert CostCategory.REGULATORY_FINE.value == "regulatory_fine"


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_zero_downtime(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        cost = calc.calculate_component_cost(g, "api", downtime_minutes=0)
        assert cost is not None
        rev = [b for b in cost.breakdowns if b.category == CostCategory.REVENUE_LOSS]
        assert rev[0].amount_usd == 0

    def test_storage_without_backup(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("s3", "S3 Storage", ComponentType.STORAGE))
        cost = calc.calculate_component_cost(g, "s3")
        assert cost is not None
        dl = [b for b in cost.breakdowns if b.category == CostCategory.DATA_LOSS]
        assert len(dl) == 1

    def test_breakdown_descriptions(self):
        calc = IncidentCostCalculator()
        g = InfraGraph()
        g.add_component(_comp("api", "API"))
        cost = calc.calculate_component_cost(g, "api", downtime_minutes=60)
        assert cost is not None
        for bd in cost.breakdowns:
            assert bd.description
            assert bd.calculation
