"""Tests for Predictive Engine v2 — Failure Prediction, Capacity Forecast, SLA Projection.

Contains 90+ test cases covering:
- ComponentReliability (MTBF/MTTR-based failure prediction)
- CapacityForecast (resource exhaustion with threshold alerts)
- SLAForecast (SLA achievement probability and error budget)
- RiskTimelineEvent (time-ordered risk event generation)
- Helper functions (_poisson_at_least_one, _compound_failure_probability, etc.)
- Edge cases and boundary values
"""

from __future__ import annotations

import math

import pytest

from faultray.simulator.predictive_engine import (
    CapacityForecast,
    ComponentReliability,
    PredictiveEngine,
    RiskTimelineEvent,
    SLAForecast,
    _capacity_recommendation,
    _classify_risk,
    _compound_failure_probability,
    _days_to_threshold,
    _monthly_sla_probability,
    _poisson_at_least_one,
    _sla_trend,
)


# ---------------------------------------------------------------------------
# Helper: engine fixture (no graph needed for v2 API)
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> PredictiveEngine:
    """PredictiveEngine without a graph — uses standalone API only."""
    return PredictiveEngine()


# ===========================================================================
# Section 1: _poisson_at_least_one
# ===========================================================================


class TestPoissonAtLeastOne:
    """Tests for _poisson_at_least_one helper."""

    def test_zero_rate_zero_probability(self) -> None:
        assert _poisson_at_least_one(0.0, 30.0) == 0.0

    def test_negative_rate_zero_probability(self) -> None:
        assert _poisson_at_least_one(-1.0, 30.0) == 0.0

    def test_zero_days_zero_probability(self) -> None:
        assert _poisson_at_least_one(0.5, 0.0) == 0.0

    def test_negative_days_zero_probability(self) -> None:
        assert _poisson_at_least_one(0.5, -10.0) == 0.0

    def test_known_value_one_event_per_day_one_day(self) -> None:
        # P = 1 - exp(-1) ~ 0.6321
        p = _poisson_at_least_one(1.0, 1.0)
        assert abs(p - (1 - math.exp(-1))) < 1e-10

    def test_high_rate_approaches_one(self) -> None:
        p = _poisson_at_least_one(10.0, 30.0)
        assert p > 0.999

    def test_very_large_exponent_returns_one(self) -> None:
        # Overflow guard: lambda * t > 700
        p = _poisson_at_least_one(100.0, 100.0)
        assert p == 1.0

    def test_small_rate_small_probability(self) -> None:
        # lambda=0.001/day, t=1 day -> P ~ 0.001
        p = _poisson_at_least_one(0.001, 1.0)
        assert 0.0009 < p < 0.0011


# ===========================================================================
# Section 2: _compound_failure_probability
# ===========================================================================


class TestCompoundFailureProbability:
    """Tests for _compound_failure_probability helper."""

    def test_empty_list_zero(self) -> None:
        assert _compound_failure_probability([]) == 0.0

    def test_single_component(self) -> None:
        assert abs(_compound_failure_probability([0.3]) - 0.3) < 1e-10

    def test_two_independent_components(self) -> None:
        # P(>=1) = 1 - (1-0.1)*(1-0.2) = 1 - 0.72 = 0.28
        p = _compound_failure_probability([0.1, 0.2])
        assert abs(p - 0.28) < 1e-10

    def test_all_certain_failure(self) -> None:
        p = _compound_failure_probability([1.0, 1.0, 1.0])
        assert p == 1.0

    def test_all_zero_probability(self) -> None:
        p = _compound_failure_probability([0.0, 0.0, 0.0])
        assert p == 0.0

    def test_many_small_probabilities(self) -> None:
        # 10 components each at 5% -> P(>=1) = 1 - 0.95^10 ~ 0.4013
        p = _compound_failure_probability([0.05] * 10)
        expected = 1 - 0.95 ** 10
        assert abs(p - expected) < 1e-10

    def test_mixed_probabilities(self) -> None:
        probs = [0.01, 0.5, 0.99]
        p = _compound_failure_probability(probs)
        expected = 1 - (0.99 * 0.5 * 0.01)
        assert abs(p - expected) < 1e-10


# ===========================================================================
# Section 3: _classify_risk
# ===========================================================================


class TestClassifyRisk:
    """Tests for _classify_risk helper."""

    def test_critical_threshold(self) -> None:
        assert _classify_risk(0.7) == "critical"

    def test_critical_above(self) -> None:
        assert _classify_risk(0.99) == "critical"

    def test_high_threshold(self) -> None:
        assert _classify_risk(0.4) == "high"

    def test_high_range(self) -> None:
        assert _classify_risk(0.55) == "high"

    def test_medium_threshold(self) -> None:
        assert _classify_risk(0.15) == "medium"

    def test_medium_range(self) -> None:
        assert _classify_risk(0.3) == "medium"

    def test_low_below_threshold(self) -> None:
        assert _classify_risk(0.1) == "low"

    def test_low_zero(self) -> None:
        assert _classify_risk(0.0) == "low"

    def test_boundary_just_below_critical(self) -> None:
        assert _classify_risk(0.69999) == "high"

    def test_boundary_just_below_high(self) -> None:
        assert _classify_risk(0.39999) == "medium"

    def test_boundary_just_below_medium(self) -> None:
        assert _classify_risk(0.14999) == "low"


# ===========================================================================
# Section 4: _days_to_threshold
# ===========================================================================


class TestDaysToThreshold:
    """Tests for _days_to_threshold helper."""

    def test_already_above_threshold(self) -> None:
        result = _days_to_threshold(85.0, 5.0, 80.0)
        assert result == 0.0

    def test_at_threshold_returns_zero(self) -> None:
        result = _days_to_threshold(80.0, 5.0, 80.0)
        assert result == 0.0

    def test_zero_growth_returns_none(self) -> None:
        result = _days_to_threshold(50.0, 0.0, 80.0)
        assert result is None

    def test_negative_growth_returns_none(self) -> None:
        result = _days_to_threshold(50.0, -2.0, 80.0)
        assert result is None

    def test_known_calculation(self) -> None:
        # 50% current, 5%/month growth, threshold 80%
        # remaining = 30 points, days_per_point = 30/5 = 6
        # result = 30 * 6 = 180 days
        result = _days_to_threshold(50.0, 5.0, 80.0)
        assert result is not None
        assert abs(result - 180.0) < 0.01

    def test_small_gap_fast_growth(self) -> None:
        # 79% current, 10%/month growth, threshold 80%
        # remaining = 1, days_per_point = 30/10 = 3, result = 3 days
        result = _days_to_threshold(79.0, 10.0, 80.0)
        assert result is not None
        assert abs(result - 3.0) < 0.01

    def test_threshold_100_percent(self) -> None:
        # 60%, 4%/month, threshold 100%
        # remaining = 40, days_per_point = 30/4 = 7.5, result = 300
        result = _days_to_threshold(60.0, 4.0, 100.0)
        assert result is not None
        assert abs(result - 300.0) < 0.01


# ===========================================================================
# Section 5: _capacity_recommendation
# ===========================================================================


class TestCapacityRecommendation:
    """Tests for _capacity_recommendation helper."""

    def test_critical_exhaustion_within_7_days(self) -> None:
        rec = _capacity_recommendation("storage", None, None, 5.0)
        assert "CRITICAL" in rec
        assert "storage" in rec

    def test_high_90_percent_within_14_days(self) -> None:
        rec = _capacity_recommendation("memory", None, 10.0, 30.0)
        assert "HIGH" in rec
        assert "memory" in rec

    def test_medium_80_percent_within_30_days(self) -> None:
        rec = _capacity_recommendation("cpu", 20.0, 60.0, 120.0)
        assert "MEDIUM" in rec
        assert "cpu" in rec

    def test_ok_when_all_none(self) -> None:
        rec = _capacity_recommendation("network", None, None, None)
        assert "OK" in rec
        assert "network" in rec

    def test_low_when_far_out(self) -> None:
        rec = _capacity_recommendation("cpu", 90.0, 120.0, 200.0)
        assert "LOW" in rec


# ===========================================================================
# Section 6: _sla_trend
# ===========================================================================


class TestSLATrend:
    """Tests for _sla_trend helper."""

    def test_improving_low_burn(self) -> None:
        # Sustainable rate = 0.1 / 30 = 0.00333/day
        # burn = 0.001/day -> ratio = 0.3 -> improving
        assert _sla_trend(0.001, 0.1) == "improving"

    def test_stable_moderate_burn(self) -> None:
        # Sustainable = 0.1/30 ~ 0.00333
        # burn = 0.003 -> ratio ~ 0.9 -> stable
        assert _sla_trend(0.003, 0.1) == "stable"

    def test_degrading_high_burn(self) -> None:
        # Sustainable = 0.1/30 ~ 0.00333
        # burn = 0.01 -> ratio ~ 3.0 -> degrading
        assert _sla_trend(0.01, 0.1) == "degrading"

    def test_zero_budget_degrading(self) -> None:
        assert _sla_trend(0.001, 0.0) == "degrading"

    def test_zero_burn_improving(self) -> None:
        # ratio = 0 / anything = 0 -> improving
        assert _sla_trend(0.0, 0.1) == "improving"


# ===========================================================================
# Section 7: _monthly_sla_probability
# ===========================================================================


class TestMonthlySLAProbability:
    """Tests for _monthly_sla_probability helper."""

    def test_zero_budget_total_returns_zero(self) -> None:
        assert _monthly_sla_probability(50.0, 0.001, 0.0) == 0.0

    def test_zero_burn_rate_returns_one(self) -> None:
        assert _monthly_sla_probability(50.0, 0.0, 0.1) == 1.0

    def test_high_remaining_high_probability(self) -> None:
        # 80% remaining, low burn, large budget
        prob = _monthly_sla_probability(80.0, 0.001, 0.1, 30.0)
        assert prob > 0.7

    def test_low_remaining_high_burn_low_probability(self) -> None:
        # 5% remaining, high burn
        prob = _monthly_sla_probability(5.0, 0.01, 0.1, 30.0)
        assert prob < 0.5

    def test_output_between_0_and_1(self) -> None:
        prob = _monthly_sla_probability(50.0, 0.002, 0.1, 30.0)
        assert 0.0 <= prob <= 1.0


# ===========================================================================
# Section 8: PredictiveEngine.predict_failure (single component)
# ===========================================================================


class TestPredictFailure:
    """Tests for PredictiveEngine.predict_failure."""

    def test_basic_structure(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("web-01", 2160.0, 1.0)
        assert isinstance(r, ComponentReliability)
        assert r.component_id == "web-01"
        assert r.mtbf_hours == 2160.0
        assert r.mttr_hours == 1.0

    def test_expected_days_to_failure(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("db-01", 720.0, 2.0)
        # 720 hours / 24 = 30 days
        assert abs(r.expected_days_to_failure - 30.0) < 0.01

    def test_probabilities_increase_over_time(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("svc-01", 2000.0, 1.0)
        assert r.failure_probability_30d <= r.failure_probability_90d

    def test_high_mtbf_low_probability(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("dns-01", 87600.0, 0.5)
        assert r.failure_probability_30d < 0.05
        assert r.risk_level == "low"

    def test_low_mtbf_high_probability(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("cache-01", 100.0, 1.0)
        assert r.failure_probability_30d > 0.9
        assert r.risk_level == "critical"

    def test_zero_mtbf_certain_failure(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("broken-01", 0.0, 1.0)
        assert r.failure_probability_30d == 1.0
        assert r.failure_probability_90d == 1.0
        assert r.expected_days_to_failure == 0.0
        assert r.risk_level == "critical"

    def test_negative_mtbf_certain_failure(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("neg-01", -100.0, 1.0)
        assert r.failure_probability_30d == 1.0
        assert r.risk_level == "critical"

    def test_negative_mttr_clamped_to_zero(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("svc-01", 1000.0, -5.0)
        assert r.mttr_hours == 0.0

    def test_probability_values_rounded(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("svc-01", 5000.0, 1.0)
        # Check that probabilities are rounded to 6 decimal places
        p30_str = f"{r.failure_probability_30d:.6f}"
        assert len(p30_str.split(".")[1]) <= 6

    def test_risk_level_medium(self, engine: PredictiveEngine) -> None:
        # MTBF that gives ~20-30% 30d probability
        # P(30d) = 1 - exp(-720/MTBF). For P~0.25, MTBF ~ 720/0.288 ~ 2500
        r = engine.predict_failure("svc-02", 2500.0, 1.0)
        assert r.risk_level == "medium"

    def test_risk_level_high(self, engine: PredictiveEngine) -> None:
        # P(30d) for MTBF=1000: 1 - exp(-720/1000) = 1 - exp(-0.72) ~ 0.513
        r = engine.predict_failure("svc-03", 1000.0, 1.0)
        assert r.risk_level == "high"

    def test_very_large_mtbf(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("ultra", 1_000_000.0, 0.1)
        assert r.failure_probability_30d < 0.01
        assert r.risk_level == "low"
        assert r.expected_days_to_failure > 40000


# ===========================================================================
# Section 9: PredictiveEngine.predict_failures (multiple components)
# ===========================================================================


class TestPredictFailures:
    """Tests for PredictiveEngine.predict_failures (batch)."""

    def test_multiple_components(self, engine: PredictiveEngine) -> None:
        comps = [
            {"component_id": "web", "mtbf_hours": 2160.0, "mttr_hours": 0.5},
            {"component_id": "db", "mtbf_hours": 4320.0, "mttr_hours": 2.0},
            {"component_id": "cache", "mtbf_hours": 720.0, "mttr_hours": 0.25},
        ]
        results = engine.predict_failures(comps)
        assert len(results) == 3

    def test_sorted_by_risk_descending(self, engine: PredictiveEngine) -> None:
        comps = [
            {"component_id": "safe", "mtbf_hours": 87600.0, "mttr_hours": 0.5},
            {"component_id": "risky", "mtbf_hours": 100.0, "mttr_hours": 1.0},
            {"component_id": "moderate", "mtbf_hours": 2000.0, "mttr_hours": 1.0},
        ]
        results = engine.predict_failures(comps)
        assert results[0].component_id == "risky"
        assert results[-1].component_id == "safe"
        # Verify descending order
        for i in range(len(results) - 1):
            assert results[i].failure_probability_30d >= results[i + 1].failure_probability_30d

    def test_empty_list(self, engine: PredictiveEngine) -> None:
        results = engine.predict_failures([])
        assert results == []

    def test_single_component_in_list(self, engine: PredictiveEngine) -> None:
        comps = [{"component_id": "solo", "mtbf_hours": 1000.0, "mttr_hours": 1.0}]
        results = engine.predict_failures(comps)
        assert len(results) == 1
        assert results[0].component_id == "solo"

    def test_missing_fields_default(self, engine: PredictiveEngine) -> None:
        comps = [{"component_id": "partial"}]  # no mtbf/mttr
        results = engine.predict_failures(comps)
        assert len(results) == 1
        # Should default to 0.0 mtbf -> certain failure
        assert results[0].failure_probability_30d == 1.0

    def test_all_ids_preserved(self, engine: PredictiveEngine) -> None:
        comps = [
            {"component_id": f"svc-{i}", "mtbf_hours": 1000.0 + i * 100, "mttr_hours": 1.0}
            for i in range(5)
        ]
        results = engine.predict_failures(comps)
        ids = {r.component_id for r in results}
        expected_ids = {f"svc-{i}" for i in range(5)}
        assert ids == expected_ids


# ===========================================================================
# Section 10: PredictiveEngine.compound_failure_probability
# ===========================================================================


class TestCompoundFailureProbabilityMethod:
    """Tests for PredictiveEngine.compound_failure_probability."""

    def test_empty_reliabilities(self, engine: PredictiveEngine) -> None:
        result = engine.compound_failure_probability([], horizon_days=30)
        assert result == 0.0

    def test_single_component_matches_individual(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("svc-01", 2000.0, 1.0)
        p = engine.compound_failure_probability([r], horizon_days=30)
        assert abs(p - r.failure_probability_30d) < 1e-5

    def test_multiple_components_higher_than_individual(self, engine: PredictiveEngine) -> None:
        r1 = engine.predict_failure("svc-01", 2000.0, 1.0)
        r2 = engine.predict_failure("svc-02", 3000.0, 1.0)
        p = engine.compound_failure_probability([r1, r2], horizon_days=30)
        assert p > r1.failure_probability_30d
        assert p > r2.failure_probability_30d

    def test_90_day_horizon(self, engine: PredictiveEngine) -> None:
        r = engine.predict_failure("svc-01", 2000.0, 1.0)
        p30 = engine.compound_failure_probability([r], horizon_days=30)
        p90 = engine.compound_failure_probability([r], horizon_days=90)
        assert p90 >= p30

    def test_horizon_31_uses_90d(self, engine: PredictiveEngine) -> None:
        """Horizon > 30 should use 90d probability."""
        r = engine.predict_failure("svc-01", 2000.0, 1.0)
        p = engine.compound_failure_probability([r], horizon_days=31)
        assert abs(p - r.failure_probability_90d) < 1e-5


# ===========================================================================
# Section 11: PredictiveEngine.forecast_capacity
# ===========================================================================


class TestForecastCapacity:
    """Tests for PredictiveEngine.forecast_capacity."""

    def test_basic_structure(self, engine: PredictiveEngine) -> None:
        fc = engine.forecast_capacity("cpu", 50.0, 5.0)
        assert isinstance(fc, CapacityForecast)
        assert fc.resource_type == "cpu"
        assert fc.current_usage_percent == 50.0
        assert fc.growth_rate_per_month == 5.0

    def test_days_to_thresholds_calculated(self, engine: PredictiveEngine) -> None:
        fc = engine.forecast_capacity("memory", 60.0, 5.0)
        assert fc.days_to_80_percent is not None
        assert fc.days_to_90_percent is not None
        assert fc.days_to_100_percent is not None
        # 80%: 20pp/5pp/mo = 4 months = 120 days
        assert abs(fc.days_to_80_percent - 120.0) < 0.1

    def test_already_above_80(self, engine: PredictiveEngine) -> None:
        fc = engine.forecast_capacity("storage", 85.0, 2.0)
        assert fc.days_to_80_percent == 0.0
        assert fc.days_to_90_percent is not None
        assert fc.days_to_90_percent > 0

    def test_already_above_100(self, engine: PredictiveEngine) -> None:
        fc = engine.forecast_capacity("disk", 105.0, 1.0)
        assert fc.days_to_80_percent == 0.0
        assert fc.days_to_90_percent == 0.0
        assert fc.days_to_100_percent == 0.0

    def test_zero_growth_all_none(self, engine: PredictiveEngine) -> None:
        fc = engine.forecast_capacity("network", 50.0, 0.0)
        assert fc.days_to_80_percent is None
        assert fc.days_to_90_percent is None
        assert fc.days_to_100_percent is None

    def test_negative_growth_all_none(self, engine: PredictiveEngine) -> None:
        fc = engine.forecast_capacity("cpu", 70.0, -3.0)
        assert fc.days_to_80_percent is None
        assert fc.days_to_90_percent is None
        assert fc.days_to_100_percent is None

    def test_recommendation_critical(self, engine: PredictiveEngine) -> None:
        # 95% usage, 10%/month -> 100% in 15 days -> less than 7? No, 15 days.
        # Try 98% usage, 10%/month -> 100% in 6 days
        fc = engine.forecast_capacity("storage", 98.0, 10.0)
        assert "CRITICAL" in fc.recommendation

    def test_recommendation_ok(self, engine: PredictiveEngine) -> None:
        fc = engine.forecast_capacity("cpu", 30.0, 0.0)
        assert "OK" in fc.recommendation

    def test_thresholds_ordering(self, engine: PredictiveEngine) -> None:
        fc = engine.forecast_capacity("memory", 50.0, 3.0)
        if fc.days_to_80_percent is not None and fc.days_to_90_percent is not None:
            assert fc.days_to_80_percent <= fc.days_to_90_percent
        if fc.days_to_90_percent is not None and fc.days_to_100_percent is not None:
            assert fc.days_to_90_percent <= fc.days_to_100_percent

    def test_fast_growth_short_timeline(self, engine: PredictiveEngine) -> None:
        fc = engine.forecast_capacity("storage", 75.0, 30.0)
        # 5pp to 80%, 30pp/month -> 30/30=1 day per point -> 5 days
        assert fc.days_to_80_percent is not None
        assert abs(fc.days_to_80_percent - 5.0) < 0.1

    def test_values_rounded(self, engine: PredictiveEngine) -> None:
        fc = engine.forecast_capacity("cpu", 33.333, 7.777)
        assert fc.current_usage_percent == 33.33
        assert fc.growth_rate_per_month == 7.777


# ===========================================================================
# Section 12: PredictiveEngine.forecast_sla
# ===========================================================================


class TestForecastSLA:
    """Tests for PredictiveEngine.forecast_sla."""

    def test_basic_structure(self, engine: PredictiveEngine) -> None:
        sla = engine.forecast_sla(99.9, 99.95, 80.0, 0.001)
        assert isinstance(sla, SLAForecast)
        assert sla.slo_target == 99.9
        assert sla.current_availability == 99.95

    def test_healthy_sla(self, engine: PredictiveEngine) -> None:
        # 99.9% target, 99.95% current, 80% budget remaining, low burn
        sla = engine.forecast_sla(99.9, 99.95, 80.0, 0.0005)
        assert sla.monthly_sla_probability > 0.5
        assert sla.trend in ("improving", "stable")

    def test_degrading_sla(self, engine: PredictiveEngine) -> None:
        # 99.9% target, 99.85% current, 10% remaining, high burn
        sla = engine.forecast_sla(99.9, 99.85, 10.0, 0.01)
        assert sla.trend == "degrading"
        assert sla.days_until_budget_exhaustion is not None
        assert sla.days_until_budget_exhaustion < 5

    def test_zero_burn_rate_no_exhaustion(self, engine: PredictiveEngine) -> None:
        sla = engine.forecast_sla(99.9, 99.99, 90.0, 0.0)
        assert sla.days_until_budget_exhaustion is None
        assert sla.monthly_sla_probability == 1.0

    def test_budget_already_exhausted(self, engine: PredictiveEngine) -> None:
        sla = engine.forecast_sla(99.9, 99.8, 0.0, 0.01)
        assert sla.days_until_budget_exhaustion == 0.0

    def test_days_to_exhaustion_calculation(self, engine: PredictiveEngine) -> None:
        # budget_total = 100 - 99.9 = 0.1
        # remaining_abs = 50% * 0.1 = 0.05
        # burn = 0.005/day -> days = 0.05/0.005 = 10
        sla = engine.forecast_sla(99.9, 99.95, 50.0, 0.005)
        assert sla.days_until_budget_exhaustion is not None
        assert abs(sla.days_until_budget_exhaustion - 10.0) < 0.1

    def test_quarterly_lower_than_monthly_with_high_burn(self, engine: PredictiveEngine) -> None:
        sla = engine.forecast_sla(99.9, 99.92, 40.0, 0.003)
        # Over 90 days, more likely to exhaust budget than over 30 days
        assert sla.quarterly_sla_probability <= sla.monthly_sla_probability

    def test_slo_target_99_99(self, engine: PredictiveEngine) -> None:
        sla = engine.forecast_sla(99.99, 99.995, 70.0, 0.0001)
        assert sla.slo_target == 99.99
        assert sla.monthly_sla_probability > 0.0

    def test_trend_improving(self, engine: PredictiveEngine) -> None:
        # Very low burn rate -> improving
        sla = engine.forecast_sla(99.9, 99.99, 90.0, 0.0001)
        assert sla.trend == "improving"

    def test_trend_stable(self, engine: PredictiveEngine) -> None:
        # Sustainable burn = 0.1/30 ~ 0.00333
        # burn = 0.003 -> ratio ~ 0.9 -> stable
        sla = engine.forecast_sla(99.9, 99.95, 50.0, 0.003)
        assert sla.trend == "stable"

    def test_error_budget_remaining_percent_preserved(self, engine: PredictiveEngine) -> None:
        sla = engine.forecast_sla(99.9, 99.95, 42.7, 0.001)
        assert sla.error_budget_remaining_percent == 42.7

    def test_probabilities_between_0_and_1(self, engine: PredictiveEngine) -> None:
        sla = engine.forecast_sla(99.5, 99.6, 60.0, 0.005)
        assert 0.0 <= sla.monthly_sla_probability <= 1.0
        assert 0.0 <= sla.quarterly_sla_probability <= 1.0


# ===========================================================================
# Section 13: PredictiveEngine.generate_risk_timeline
# ===========================================================================


class TestGenerateRiskTimeline:
    """Tests for PredictiveEngine.generate_risk_timeline."""

    def test_empty_inputs_empty_timeline(self, engine: PredictiveEngine) -> None:
        events = engine.generate_risk_timeline()
        assert events == []

    def test_failure_events_generated(self, engine: PredictiveEngine) -> None:
        preds = [engine.predict_failure("svc-01", 2000.0, 1.0)]
        events = engine.generate_risk_timeline(predictions=preds)
        assert len(events) >= 1
        assert events[0].event_type == "failure"

    def test_capacity_events_generated(self, engine: PredictiveEngine) -> None:
        fcs = [engine.forecast_capacity("cpu", 50.0, 5.0)]
        events = engine.generate_risk_timeline(forecasts=fcs)
        assert len(events) >= 1
        assert all(e.event_type == "capacity" for e in events)

    def test_sla_events_generated(self, engine: PredictiveEngine) -> None:
        slas = [engine.forecast_sla(99.9, 99.95, 50.0, 0.005)]
        events = engine.generate_risk_timeline(sla_forecasts=slas)
        assert len(events) >= 1
        assert events[0].event_type == "sla"

    def test_sorted_by_days_ascending(self, engine: PredictiveEngine) -> None:
        preds = [
            engine.predict_failure("slow", 87600.0, 1.0),
            engine.predict_failure("fast", 100.0, 1.0),
        ]
        fcs = [engine.forecast_capacity("cpu", 90.0, 10.0)]
        slas = [engine.forecast_sla(99.9, 99.85, 10.0, 0.01)]
        events = engine.generate_risk_timeline(
            predictions=preds, forecasts=fcs, sla_forecasts=slas,
        )
        for i in range(len(events) - 1):
            assert events[i].days_from_now <= events[i + 1].days_from_now

    def test_combined_event_types(self, engine: PredictiveEngine) -> None:
        preds = [engine.predict_failure("svc-01", 2000.0, 1.0)]
        fcs = [engine.forecast_capacity("cpu", 50.0, 5.0)]
        slas = [engine.forecast_sla(99.9, 99.95, 50.0, 0.005)]
        events = engine.generate_risk_timeline(
            predictions=preds, forecasts=fcs, sla_forecasts=slas,
        )
        types = {e.event_type for e in events}
        assert "failure" in types
        assert "capacity" in types
        assert "sla" in types

    def test_capacity_threshold_events(self, engine: PredictiveEngine) -> None:
        # Should generate events for 80%, 90%, 100% thresholds
        fc = engine.forecast_capacity("storage", 50.0, 5.0)
        events = engine.generate_risk_timeline(forecasts=[fc])
        # All 3 thresholds should be present (80%, 90%, 100%)
        assert len(events) == 3
        severities = [e.severity for e in events]
        assert "medium" in severities
        assert "high" in severities
        assert "critical" in severities

    def test_event_descriptions_contain_details(self, engine: PredictiveEngine) -> None:
        preds = [engine.predict_failure("web-01", 2000.0, 1.0)]
        events = engine.generate_risk_timeline(predictions=preds)
        assert "web-01" in events[0].description
        assert "MTBF" in events[0].description

    def test_sla_severity_critical_for_imminent(self, engine: PredictiveEngine) -> None:
        sla = engine.forecast_sla(99.9, 99.85, 5.0, 0.01)
        events = engine.generate_risk_timeline(sla_forecasts=[sla])
        assert len(events) >= 1
        assert events[0].severity == "critical"

    def test_capacity_already_at_threshold(self, engine: PredictiveEngine) -> None:
        fc = engine.forecast_capacity("disk", 95.0, 2.0)
        events = engine.generate_risk_timeline(forecasts=[fc])
        # 80% and 90% are already exceeded (days=0), 100% is not yet
        at_zero = [e for e in events if e.days_from_now == 0.0]
        assert len(at_zero) >= 2  # 80% and 90% both at 0

    def test_component_or_resource_field(self, engine: PredictiveEngine) -> None:
        preds = [engine.predict_failure("db-01", 2000.0, 1.0)]
        fcs = [engine.forecast_capacity("memory", 50.0, 5.0)]
        events = engine.generate_risk_timeline(predictions=preds, forecasts=fcs)
        comp_names = {e.component_or_resource for e in events}
        assert "db-01" in comp_names
        assert "memory" in comp_names

    def test_sla_component_field_format(self, engine: PredictiveEngine) -> None:
        slas = [engine.forecast_sla(99.9, 99.95, 50.0, 0.005)]
        events = engine.generate_risk_timeline(sla_forecasts=slas)
        assert events[0].component_or_resource == "SLO-99.9"


# ===========================================================================
# Section 14: Dataclass field verification
# ===========================================================================


class TestNewDataclasses:
    """Test new dataclass instantiation and field defaults."""

    def test_component_reliability_all_fields(self) -> None:
        cr = ComponentReliability(
            component_id="test",
            mtbf_hours=1000.0,
            mttr_hours=2.0,
            failure_probability_30d=0.5,
            failure_probability_90d=0.9,
            expected_days_to_failure=41.67,
            risk_level="high",
        )
        assert cr.component_id == "test"
        assert cr.mtbf_hours == 1000.0
        assert cr.mttr_hours == 2.0
        assert cr.risk_level == "high"

    def test_capacity_forecast_with_none_thresholds(self) -> None:
        cf = CapacityForecast(
            resource_type="cpu",
            current_usage_percent=30.0,
            growth_rate_per_month=0.0,
            days_to_80_percent=None,
            days_to_90_percent=None,
            days_to_100_percent=None,
            recommendation="No action.",
        )
        assert cf.days_to_80_percent is None
        assert cf.resource_type == "cpu"

    def test_sla_forecast_all_fields(self) -> None:
        sf = SLAForecast(
            slo_target=99.9,
            current_availability=99.95,
            error_budget_remaining_percent=50.0,
            days_until_budget_exhaustion=15.0,
            monthly_sla_probability=0.85,
            quarterly_sla_probability=0.6,
            trend="stable",
        )
        assert sf.slo_target == 99.9
        assert sf.trend == "stable"

    def test_risk_timeline_event_all_fields(self) -> None:
        rte = RiskTimelineEvent(
            days_from_now=7.5,
            event_type="failure",
            severity="high",
            description="Expected failure",
            component_or_resource="web-01",
        )
        assert rte.days_from_now == 7.5
        assert rte.event_type == "failure"


# ===========================================================================
# Section 15: Integration / end-to-end scenarios
# ===========================================================================


class TestIntegrationScenarios:
    """End-to-end integration tests combining multiple engine features."""

    def test_full_risk_assessment_workflow(self, engine: PredictiveEngine) -> None:
        """Simulate a complete risk assessment workflow."""
        # 1. Predict failures for infrastructure
        components = [
            {"component_id": "web-01", "mtbf_hours": 2160.0, "mttr_hours": 0.5},
            {"component_id": "api-01", "mtbf_hours": 1440.0, "mttr_hours": 1.0},
            {"component_id": "db-01", "mtbf_hours": 4320.0, "mttr_hours": 2.0},
            {"component_id": "cache-01", "mtbf_hours": 720.0, "mttr_hours": 0.25},
        ]
        reliabilities = engine.predict_failures(components)
        assert len(reliabilities) == 4

        # 2. Calculate compound failure probability
        compound_30d = engine.compound_failure_probability(reliabilities, 30)
        compound_90d = engine.compound_failure_probability(reliabilities, 90)
        assert compound_90d >= compound_30d
        assert compound_30d > 0

        # 3. Forecast capacity for resources
        cpu_fc = engine.forecast_capacity("cpu", 55.0, 3.0)
        mem_fc = engine.forecast_capacity("memory", 70.0, 5.0)
        disk_fc = engine.forecast_capacity("storage", 40.0, 2.0)

        # 4. Forecast SLA
        sla = engine.forecast_sla(99.9, 99.95, 60.0, 0.002)

        # 5. Generate timeline
        events = engine.generate_risk_timeline(
            predictions=reliabilities,
            forecasts=[cpu_fc, mem_fc, disk_fc],
            sla_forecasts=[sla],
        )
        assert len(events) > 0

        # Timeline should be sorted
        for i in range(len(events) - 1):
            assert events[i].days_from_now <= events[i + 1].days_from_now

    def test_worst_case_all_critical(self, engine: PredictiveEngine) -> None:
        """Everything is in critical state."""
        reliability = engine.predict_failure("dying", 50.0, 24.0)
        assert reliability.risk_level == "critical"

        capacity = engine.forecast_capacity("storage", 99.0, 30.0)
        assert "CRITICAL" in capacity.recommendation

        sla = engine.forecast_sla(99.9, 99.0, 2.0, 0.05)
        assert sla.trend == "degrading"
        assert sla.days_until_budget_exhaustion is not None
        assert sla.days_until_budget_exhaustion < 1

        events = engine.generate_risk_timeline(
            predictions=[reliability],
            forecasts=[capacity],
            sla_forecasts=[sla],
        )
        critical_events = [e for e in events if e.severity == "critical"]
        assert len(critical_events) >= 2

    def test_best_case_all_healthy(self, engine: PredictiveEngine) -> None:
        """Everything is in healthy state."""
        reliability = engine.predict_failure("stable", 87600.0, 0.1)
        assert reliability.risk_level == "low"

        capacity = engine.forecast_capacity("cpu", 20.0, 0.5)
        assert "LOW" in capacity.recommendation or "OK" in capacity.recommendation

        sla = engine.forecast_sla(99.9, 99.99, 95.0, 0.0001)
        assert sla.trend == "improving"
        assert sla.monthly_sla_probability > 0.8

    def test_engine_without_graph_still_works_for_v2_api(self) -> None:
        """Ensure v2 API works without graph (graph=None)."""
        engine = PredictiveEngine()
        r = engine.predict_failure("test", 1000.0, 1.0)
        assert r.component_id == "test"

        fc = engine.forecast_capacity("cpu", 50.0, 5.0)
        assert fc.resource_type == "cpu"

        sla = engine.forecast_sla(99.9, 99.95, 50.0, 0.002)
        assert sla.slo_target == 99.9

    def test_engine_without_graph_predict_returns_empty(self) -> None:
        """Original predict() on engine without graph returns empty report."""
        engine = PredictiveEngine()
        report = engine.predict()
        assert report.summary == "No graph provided."
