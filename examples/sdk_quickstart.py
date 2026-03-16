#!/usr/bin/env python3
"""FaultRay SDK Quick Start — Run your first chaos simulation in Python.

Usage:
    python sdk_quickstart.py
"""
from faultray.simulator.cost_impact import CostImpactEngine, CostProfile
from faultray.simulator.security_resilience import (
    SecurityResilienceEngine, SecurityProfile, SecurityControl,
)
from faultray.simulator.compliance_frameworks import (
    ComplianceFrameworksEngine, ComplianceFramework, InfrastructureEvidence,
)
from faultray.simulator.multi_region_dr import (
    MultiRegionDREngine, DRConfig, DRStrategy, Region, ReplicationMode,
)
from faultray.simulator.predictive_engine import PredictiveEngine


def main():
    print("=" * 60)
    print("FaultRay SDK Quick Start")
    print("=" * 60)

    # --- 1. Cost Impact Analysis ---
    print("\n--- Cost Impact Analysis ---")
    cost_engine = CostImpactEngine()
    cost_engine.set_component_profile("api", CostProfile(
        revenue_per_hour=50000,
        sla_penalty_per_violation=10000,
        affected_users=100000,
    ))
    cost_engine.set_component_profile("db", CostProfile(
        revenue_per_hour=50000,
        recovery_cost_per_incident=5000,
    ))

    breakdown = cost_engine.calculate_scenario_cost(
        scenario_name="Database failover",
        affected_components=["api", "db"],
        downtime_minutes=15,
        cascade_depth=2,
    )
    print(f"  Scenario: {breakdown.scenario_name}")
    print(f"  Total Cost: ${breakdown.total_cost:,.2f}")
    print(f"  Cost Tier: {breakdown.cost_tier.value}")

    # --- 2. Security Assessment ---
    print("\n--- Security Resilience ---")
    sec_engine = SecurityResilienceEngine()
    sec_engine.set_component_profile("api", SecurityProfile(
        controls=[
            SecurityControl.ENCRYPTION_IN_TRANSIT,
            SecurityControl.RATE_LIMITING,
            SecurityControl.WAF,
            SecurityControl.MFA,
            SecurityControl.AUDIT_LOGGING,
        ],
        public_facing=True,
    ))
    scorecard = sec_engine.generate_scorecard()
    print(f"  Security Score: {scorecard.overall_score}/100 (Grade: {scorecard.grade})")
    print(f"  Strengths: {len(scorecard.strengths)}, Weaknesses: {len(scorecard.weaknesses)}")

    # --- 3. Compliance Check ---
    print("\n--- Compliance Assessment (SOC 2) ---")
    evidence = InfrastructureEvidence(
        encryption_at_rest=True,
        encryption_in_transit=True,
        mfa_enabled=True,
        audit_logging=True,
        monitoring_enabled=True,
        backup_enabled=True,
    )
    comp_engine = ComplianceFrameworksEngine(evidence)
    report = comp_engine.assess(ComplianceFramework.SOC2)
    print(f"  SOC 2 Score: {report.overall_score}%")
    print(f"  Compliant: {report.compliant_count}, Non-compliant: {report.non_compliant_count}")

    # --- 4. DR Assessment ---
    print("\n--- Disaster Recovery ---")
    dr_config = DRConfig(
        strategy=DRStrategy.ACTIVE_PASSIVE,
        regions=[
            Region("us-east-1", is_primary=True),
            Region("us-west-2", is_primary=False, latency_ms=70),
        ],
        replication_mode=ReplicationMode.ASYNCHRONOUS,
        replication_lag_seconds=2.0,
        failover_automation=True,
    )
    dr_engine = MultiRegionDREngine(dr_config, target_rto=300, target_rpo=60)
    assessment = dr_engine.assess()
    print(f"  RTO: {assessment.rto_seconds}s (target: 300s) — {'MET' if assessment.rto_met else 'NOT MET'}")
    print(f"  RPO: {assessment.rpo_seconds}s (target: 60s) — {'MET' if assessment.rpo_met else 'NOT MET'}")
    print(f"  Data Loss Risk: {assessment.data_loss_risk}")

    # --- 5. Failure Prediction ---
    print("\n--- Failure Prediction ---")
    pred_engine = PredictiveEngine()
    reliability = pred_engine.predict_failure("db-primary", mtbf_hours=8760, mttr_hours=0.5)
    print(f"  Component: {reliability.component_id}")
    print(f"  30-day failure probability: {reliability.failure_probability_30d:.1%}")
    print(f"  Expected days to failure: {reliability.expected_days_to_failure:.0f}")
    print(f"  Risk Level: {reliability.risk_level}")

    # --- 6. Capacity Forecast ---
    print("\n--- Capacity Forecast ---")
    forecast = pred_engine.forecast_capacity("cpu", current_percent=65, growth_rate_per_month=3.0)
    print(f"  Resource: {forecast.resource_type}")
    print(f"  Current Usage: {forecast.current_usage_percent}%")
    if forecast.days_to_80_percent:
        print(f"  Days to 80%: {forecast.days_to_80_percent:.0f}")
    if forecast.days_to_100_percent:
        print(f"  Days to 100%: {forecast.days_to_100_percent:.0f}")
    print(f"  Recommendation: {forecast.recommendation}")

    print("\n" + "=" * 60)
    print("All analyses complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
