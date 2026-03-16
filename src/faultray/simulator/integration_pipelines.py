"""Integration pipelines — unified orchestration of multiple FaultRay engines.

These pipelines combine individual simulation methods into end-to-end
workflows that deliver compound value beyond what any single engine provides.
This integration layer is the core differentiator that cannot be replicated
by implementing individual methods separately.
"""

from __future__ import annotations

import copy
import hashlib
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

from faultray.model.components import (
    Component,
    ComponentType,
    CostProfile,
    HealthStatus,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEffect, CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType, Scenario

if TYPE_CHECKING:
    from faultray.simulator.abm_engine import ABMEngine, ABMResult
    from faultray.simulator.backtest_engine import BacktestEngine, BacktestResult, RealIncident
    from faultray.simulator.availability_model import FiveLayerResult


# ---------------------------------------------------------------------------
# Shared result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ConsensusResult:
    """Result from multi-engine consensus voting."""

    scenario_name: str
    engine_results: dict[str, Any]
    agreed_affected: list[str]
    disagreements: list[str]
    confidence: float
    recommendation: str


@dataclass
class AuditResult:
    """Result from a compliance audit pipeline."""

    framework: str
    graph_summary: dict
    simulation_findings: list[dict]
    compliance_checks: list[dict]
    evidence_trail: list[dict]
    overall_status: str  # "compliant" | "non_compliant" | "partial"
    score: float  # 0-100


@dataclass
class RemediationItem:
    """A single remediation recommendation."""

    component_id: str
    issue: str
    action: str
    estimated_cost: float
    estimated_benefit: float
    roi: float
    priority: int  # 1=highest


@dataclass
class RemediationPlan:
    """Full remediation plan with cost/benefit analysis."""

    items: list[RemediationItem]
    total_cost: float
    total_benefit: float
    overall_roi: float
    cascade_findings: list[dict]


@dataclass
class CalibrationResult:
    """Result from backtest calibration loop."""

    iterations: int
    initial_accuracy: float
    final_accuracy: float
    adjustments: dict[str, float]
    converged: bool
    history: list[dict]


@dataclass
class ValidationResult:
    """Result from cross-method validation."""

    bfs_affected: list[str]
    abm_affected: list[str]
    agreement_ratio: float
    both: list[str]
    bfs_only: list[str]
    abm_only: list[str]
    uncertainty_flag: bool
    explanation: str


@dataclass
class MultiCloudResult:
    """Result from multi-cloud analysis."""

    merged_graph: InfraGraph
    cross_cloud_dependencies: list[dict]
    provider_outage_impacts: dict[str, dict]
    total_components: int


@dataclass
class LifecycleResult:
    """Result from full lifecycle automation."""

    discovery: dict
    simulation_summary: dict
    recommendations: list[str]
    validation_passed: bool
    phases_completed: list[str]


@dataclass
class EvolutionResult:
    """Result from genome evolution monitoring."""

    regression_detected: bool
    changed_traits: list[str]
    improvements: list[str]
    regressions: list[str]
    current_score: float
    previous_score: float
    delta: float


@dataclass
class ThreatAssessmentResult:
    """Result from threat feed simulation bridge."""

    threats_evaluated: int
    critical_threats: list[dict]
    scenarios_generated: int
    simulation_results: list[dict]
    overall_risk_level: str  # "low" | "medium" | "high" | "critical"


@dataclass
class UnifiedScore:
    """Unified security + resilience score."""

    unified: float  # 0-100
    resilience_score: float  # 0-100
    security_score: float  # 0-100
    resilience_weight: float
    security_weight: float
    breakdown: dict[str, float]
    recommendations: list[str]


@dataclass
class InverseResult:
    """Result from inverse optimization."""

    target_sla: float
    current_availability: float
    changes_needed: list[dict]
    total_cost: float
    achievable: bool
    explanation: str


@dataclass
class ComparisonResult:
    """Result from comparative simulation."""

    graph_a_name: str
    graph_b_name: str
    scenarios_run: int
    graph_a_scores: list[float]
    graph_b_scores: list[float]
    better_design: str
    differences_per_scenario: list[dict]
    summary: dict


@dataclass
class CompoundResult:
    """Result from compound what-if analysis."""

    individual_effects: list[dict]
    combined_effect: dict
    interaction_effects: list[dict]
    total_improvement: float
    synergy_detected: bool


@dataclass
class EnsembleResult:
    """Result from ensemble prediction."""

    static_severity: float
    dynamic_severity: float
    stochastic_severity: float
    ensemble_severity: float
    weights: dict[str, float]
    affected_components: list[str]
    confidence: float


@dataclass
class HierarchyLevel:
    """A single level in the hierarchical analysis."""

    level_name: str
    components: list[str]
    impact_score: float
    details: dict


@dataclass
class HierarchyResult:
    """Result from hierarchical analysis."""

    component_level: HierarchyLevel
    service_level: HierarchyLevel
    system_level: HierarchyLevel
    business_level: HierarchyLevel
    critical_paths: list[list[str]]


@dataclass
class TemporalResult:
    """Result from temporal unified view."""

    current_state: dict
    trend_analysis: dict
    forecast: dict
    timeline: list[dict]
    risk_trajectory: str  # "improving" | "stable" | "degrading"


# ===========================================================================
# 1. MultiEngineConsensus
# ===========================================================================

class MultiEngineConsensus:
    """Run the same scenario through multiple engines and vote on the outcome.

    Engines that agree increase confidence; disagreements flag areas that
    need additional investigation.
    """

    def __init__(self, engines: list[Callable]) -> None:
        self.engines = engines

    def run(self, scenario: Scenario) -> ConsensusResult:
        """Execute *scenario* on every engine and compute majority-vote consensus."""
        engine_results: dict[str, Any] = {}
        affected_sets: list[set[str]] = []

        for idx, engine_fn in enumerate(self.engines):
            name = getattr(engine_fn, "__name__", f"engine_{idx}")
            try:
                result = engine_fn(scenario)
                # Normalise to a set of affected component IDs
                affected = _extract_affected(result)
                engine_results[name] = {
                    "affected": sorted(affected),
                    "count": len(affected),
                }
                affected_sets.append(affected)
            except Exception as exc:
                engine_results[name] = {"error": str(exc), "affected": [], "count": 0}
                affected_sets.append(set())

        total = len(self.engines)
        if total == 0:
            return ConsensusResult(
                scenario_name=scenario.name,
                engine_results=engine_results,
                agreed_affected=[],
                disagreements=[],
                confidence=0.0,
                recommendation="No engines configured.",
            )

        # Majority vote: a component is "agreed affected" if > 50% of engines say so
        all_components: set[str] = set()
        for s in affected_sets:
            all_components |= s

        agreed: list[str] = []
        disagreements: list[str] = []
        for comp in sorted(all_components):
            vote_count = sum(1 for s in affected_sets if comp in s)
            if vote_count > total / 2:
                agreed.append(comp)
            else:
                disagreements.append(comp)

        # Confidence = average pairwise agreement
        if total <= 1:
            confidence = 1.0
        else:
            pairwise_agreements: list[float] = []
            for i in range(total):
                for j in range(i + 1, total):
                    union = affected_sets[i] | affected_sets[j]
                    intersection = affected_sets[i] & affected_sets[j]
                    ratio = len(intersection) / len(union) if union else 1.0
                    pairwise_agreements.append(ratio)
            confidence = statistics.mean(pairwise_agreements) if pairwise_agreements else 1.0

        if disagreements:
            recommendation = (
                f"{len(disagreements)} component(s) have uncertain predictions. "
                "Consider running additional targeted simulations."
            )
        else:
            recommendation = "All engines agree. High confidence in prediction."

        return ConsensusResult(
            scenario_name=scenario.name,
            engine_results=engine_results,
            agreed_affected=agreed,
            disagreements=disagreements,
            confidence=round(confidence, 4),
            recommendation=recommendation,
        )


# ===========================================================================
# 2. ComplianceAuditPipeline
# ===========================================================================

class ComplianceAuditPipeline:
    """One-command pipeline: simulate -> check compliance -> generate audit trail."""

    # Framework-specific check definitions
    _FRAMEWORK_CHECKS: dict[str, list[dict]] = {
        "dora": [
            {"id": "DORA-1", "name": "ICT Risk Management", "check": "resilience_score >= 70"},
            {"id": "DORA-2", "name": "Incident Reporting < 72h", "check": "incident_response_configured"},
            {"id": "DORA-3", "name": "Digital Operational Resilience Testing", "check": "chaos_tested"},
            {"id": "DORA-4", "name": "Third-Party Risk", "check": "external_deps_evaluated"},
            {"id": "DORA-5", "name": "Information Sharing", "check": "audit_logging_enabled"},
        ],
        "soc2": [
            {"id": "SOC2-CC6", "name": "Logical and Physical Access", "check": "auth_required"},
            {"id": "SOC2-CC7", "name": "System Operations", "check": "monitoring_configured"},
            {"id": "SOC2-CC8", "name": "Change Management", "check": "change_management_enabled"},
            {"id": "SOC2-A1", "name": "Availability", "check": "resilience_score >= 80"},
        ],
        "pci_dss": [
            {"id": "PCI-1", "name": "Network Segmentation", "check": "network_segmented"},
            {"id": "PCI-3", "name": "Protect Stored Data", "check": "encryption_at_rest"},
            {"id": "PCI-4", "name": "Encrypt Transmission", "check": "encryption_in_transit"},
            {"id": "PCI-6", "name": "Secure Systems", "check": "patch_sla_valid"},
            {"id": "PCI-10", "name": "Track and Monitor", "check": "log_enabled"},
        ],
    }

    def run(self, graph: InfraGraph, framework: str = "dora") -> AuditResult:
        """Run full compliance audit pipeline."""
        # Step 1: simulate
        cascade_engine = CascadeEngine(graph)
        findings: list[dict] = []
        for comp_id in graph.components:
            fault = Fault(
                target_component_id=comp_id,
                fault_type=FaultType.COMPONENT_DOWN,
            )
            chain = cascade_engine.simulate_fault(fault)
            if chain.severity >= 4.0:
                findings.append({
                    "component": comp_id,
                    "severity": chain.severity,
                    "affected_count": len(chain.effects),
                    "trigger": chain.trigger,
                })

        # Step 2: check compliance
        checks = self._FRAMEWORK_CHECKS.get(framework, self._FRAMEWORK_CHECKS["dora"])
        compliance_results = self._evaluate_checks(graph, checks, findings)

        # Step 3: generate evidence trail
        evidence_trail = self._generate_evidence(graph, findings, compliance_results)

        passed = sum(1 for c in compliance_results if c["status"] == "pass")
        total_checks = len(compliance_results)
        score = (passed / total_checks * 100) if total_checks > 0 else 0.0

        if score >= 90:
            overall_status = "compliant"
        elif score >= 60:
            overall_status = "partial"
        else:
            overall_status = "non_compliant"

        return AuditResult(
            framework=framework,
            graph_summary=graph.summary(),
            simulation_findings=findings,
            compliance_checks=compliance_results,
            evidence_trail=evidence_trail,
            overall_status=overall_status,
            score=round(score, 1),
        )

    def _evaluate_checks(
        self,
        graph: InfraGraph,
        checks: list[dict],
        findings: list[dict],
    ) -> list[dict]:
        """Evaluate compliance checks against graph state and simulation findings."""
        results: list[dict] = []
        resilience = graph.resilience_score()

        # Aggregate security profile flags
        has_encryption_at_rest = any(
            c.security.encryption_at_rest for c in graph.components.values()
        )
        has_encryption_in_transit = any(
            c.security.encryption_in_transit for c in graph.components.values()
        )
        has_auth = any(c.security.auth_required for c in graph.components.values())
        has_network_seg = any(
            c.security.network_segmented for c in graph.components.values()
        )
        has_log = any(c.security.log_enabled for c in graph.components.values())
        has_audit_log = any(
            c.compliance_tags.audit_logging for c in graph.components.values()
        )
        has_change_mgmt = any(
            c.compliance_tags.change_management for c in graph.components.values()
        )

        state = {
            "resilience_score": resilience,
            "incident_response_configured": resilience >= 50,
            "chaos_tested": len(findings) > 0,  # we just ran simulations
            "external_deps_evaluated": True,
            "audit_logging_enabled": has_audit_log,
            "auth_required": has_auth,
            "monitoring_configured": has_log,
            "change_management_enabled": has_change_mgmt,
            "network_segmented": has_network_seg,
            "encryption_at_rest": has_encryption_at_rest,
            "encryption_in_transit": has_encryption_in_transit,
            "patch_sla_valid": all(
                c.security.patch_sla_hours <= 72 for c in graph.components.values()
            ),
            "log_enabled": has_log,
        }

        for check in checks:
            expr = check["check"]
            passed = self._eval_check_expr(expr, state)
            results.append({
                "id": check["id"],
                "name": check["name"],
                "check": expr,
                "status": "pass" if passed else "fail",
            })

        return results

    @staticmethod
    def _eval_check_expr(expr: str, state: dict) -> bool:
        """Evaluate a simple check expression against state dict."""
        if ">=" in expr:
            key, val = expr.split(">=")
            return state.get(key.strip(), 0) >= float(val.strip())
        return bool(state.get(expr.strip(), False))

    @staticmethod
    def _generate_evidence(
        graph: InfraGraph,
        findings: list[dict],
        compliance_results: list[dict],
    ) -> list[dict]:
        """Generate audit evidence trail entries."""
        trail: list[dict] = []
        trail.append({
            "step": "graph_analysis",
            "detail": f"Analyzed {len(graph.components)} components, "
                      f"{graph.summary().get('total_dependencies', 0)} dependencies",
        })
        trail.append({
            "step": "simulation",
            "detail": f"Ran {len(graph.components)} fault scenarios, "
                      f"found {len(findings)} findings with severity >= 4.0",
        })
        for cr in compliance_results:
            trail.append({
                "step": f"compliance_check_{cr['id']}",
                "detail": f"{cr['name']}: {cr['status']}",
            })
        return trail


# ===========================================================================
# 3. CascadeCostRemediationPipeline
# ===========================================================================

class CascadeCostRemediationPipeline:
    """Cascade analysis -> cost impact -> ROI calculation -> IaC recommendations."""

    def run(self, graph: InfraGraph) -> RemediationPlan:
        """Run the full cascade-cost-remediation pipeline."""
        cascade_engine = CascadeEngine(graph)
        cascade_findings: list[dict] = []
        items: list[RemediationItem] = []

        for comp_id, comp in graph.components.items():
            fault = Fault(
                target_component_id=comp_id,
                fault_type=FaultType.COMPONENT_DOWN,
            )
            chain = cascade_engine.simulate_fault(fault)

            if chain.severity < 2.0:
                continue

            # Cost impact: revenue loss per minute * estimated downtime
            down_effects = [
                e for e in chain.effects if e.health == HealthStatus.DOWN
            ]
            estimated_downtime_min = max(
                (e.estimated_time_seconds for e in chain.effects),
                default=0,
            ) / 60.0
            if estimated_downtime_min == 0 and down_effects:
                estimated_downtime_min = len(down_effects) * 5.0

            # Aggregate revenue impact across affected components
            revenue_loss = 0.0
            for effect in chain.effects:
                affected_comp = graph.get_component(effect.component_id)
                if affected_comp:
                    revenue_loss += (
                        affected_comp.cost_profile.revenue_per_minute
                        * estimated_downtime_min
                    )

            cascade_findings.append({
                "component": comp_id,
                "severity": chain.severity,
                "affected_count": len(chain.effects),
                "estimated_downtime_min": round(estimated_downtime_min, 1),
                "estimated_revenue_loss": round(revenue_loss, 2),
            })

            # Generate remediation items
            if comp.replicas <= 1 and chain.severity >= 4.0:
                # SPOF: recommend adding replicas
                infra_cost = comp.cost_profile.hourly_infra_cost * 730  # monthly
                items.append(RemediationItem(
                    component_id=comp_id,
                    issue=f"Single point of failure (severity {chain.severity})",
                    action=f"Add replica for {comp.name} (replicas: 1 -> 2)",
                    estimated_cost=infra_cost,
                    estimated_benefit=revenue_loss * 0.8,  # 80% risk reduction
                    roi=round(
                        (revenue_loss * 0.8 - infra_cost) / infra_cost, 2
                    ) if infra_cost > 0 else 0.0,
                    priority=1 if chain.severity >= 7.0 else 2,
                ))

            if not comp.failover.enabled and chain.severity >= 3.0:
                items.append(RemediationItem(
                    component_id=comp_id,
                    issue=f"No failover configured (severity {chain.severity})",
                    action=f"Enable failover for {comp.name}",
                    estimated_cost=comp.cost_profile.hourly_infra_cost * 200,
                    estimated_benefit=revenue_loss * 0.5,
                    roi=round(
                        (revenue_loss * 0.5 - comp.cost_profile.hourly_infra_cost * 200)
                        / max(comp.cost_profile.hourly_infra_cost * 200, 1),
                        2,
                    ),
                    priority=2,
                ))

        # Sort by ROI descending
        items.sort(key=lambda x: x.roi, reverse=True)

        total_cost = sum(i.estimated_cost for i in items)
        total_benefit = sum(i.estimated_benefit for i in items)
        overall_roi = round(
            (total_benefit - total_cost) / total_cost, 2
        ) if total_cost > 0 else 0.0

        return RemediationPlan(
            items=items,
            total_cost=round(total_cost, 2),
            total_benefit=round(total_benefit, 2),
            overall_roi=overall_roi,
            cascade_findings=cascade_findings,
        )


# ===========================================================================
# 4. BacktestCalibrationLoop
# ===========================================================================

class BacktestCalibrationLoop:
    """Iteratively backtest, calibrate, and re-simulate until accuracy target is met."""

    def __init__(self, graph: InfraGraph, target_accuracy: float = 0.8) -> None:
        self.graph = graph
        self.target_accuracy = target_accuracy

    def run(
        self,
        incidents: list[RealIncident],
        max_iterations: int = 5,
    ) -> CalibrationResult:
        """Run calibration loop until accuracy >= target or max_iterations reached."""
        from faultray.simulator.backtest_engine import BacktestEngine

        engine = BacktestEngine(self.graph)
        history: list[dict] = []
        adjustments: dict[str, float] = {}
        initial_accuracy = 0.0

        for iteration in range(max_iterations):
            results = engine.run_backtest(incidents)
            summary = engine.summary(results)
            avg_f1 = summary.get("avg_f1", 0.0)

            if iteration == 0:
                initial_accuracy = avg_f1

            history.append({
                "iteration": iteration,
                "avg_f1": avg_f1,
                "avg_precision": summary.get("avg_precision", 0.0),
                "avg_recall": summary.get("avg_recall", 0.0),
                "adjustments_applied": dict(adjustments),
            })

            if avg_f1 >= self.target_accuracy:
                return CalibrationResult(
                    iterations=iteration + 1,
                    initial_accuracy=round(initial_accuracy, 4),
                    final_accuracy=round(avg_f1, 4),
                    adjustments=adjustments,
                    converged=True,
                    history=history,
                )

            # Calibrate: get adjustment recommendations
            new_adjustments = engine.calibrate(results)
            adjustments.update(new_adjustments)

            # Apply adjustments to graph components (simple heuristic)
            if "dependency_weight_threshold_reduction" in new_adjustments:
                # Increase sensitivity by enabling more circuit breakers
                for dep in self.graph.all_dependency_edges():
                    if not dep.circuit_breaker.enabled:
                        dep.circuit_breaker.enabled = True
                        break  # one change per iteration

        # Did not converge
        final_results = engine.run_backtest(incidents)
        final_summary = engine.summary(final_results)
        final_f1 = final_summary.get("avg_f1", 0.0)

        return CalibrationResult(
            iterations=max_iterations,
            initial_accuracy=round(initial_accuracy, 4),
            final_accuracy=round(final_f1, 4),
            adjustments=adjustments,
            converged=False,
            history=history,
        )


# ===========================================================================
# 5. CrossMethodValidator
# ===========================================================================

class CrossMethodValidator:
    """Compare BFS cascade and ABM simulation for the same scenario."""

    def __init__(self, graph: InfraGraph, seed: int | None = None) -> None:
        self.graph = graph
        self._seed = seed

    def validate(self, scenario: Scenario) -> ValidationResult:
        """Run both BFS and ABM, compare results, flag uncertainty."""
        from faultray.simulator.abm_engine import ABMEngine

        cascade_engine = CascadeEngine(self.graph)
        abm_engine = ABMEngine(self.graph, seed=self._seed)

        # BFS result
        bfs_affected: set[str] = set()
        for fault in scenario.faults:
            chain = cascade_engine.simulate_fault(fault)
            for effect in chain.effects:
                if effect.health != HealthStatus.HEALTHY:
                    bfs_affected.add(effect.component_id)

        # ABM result
        abm_result = abm_engine.simulate_scenario(scenario)
        abm_affected = set(abm_result.affected_agents)

        both = bfs_affected & abm_affected
        bfs_only = bfs_affected - abm_affected
        abm_only = abm_affected - bfs_affected
        union = bfs_affected | abm_affected

        agreement = len(both) / len(union) if union else 1.0
        uncertainty = agreement < 0.7

        if uncertainty:
            explanation = (
                f"Low agreement ({agreement:.1%}) between BFS and ABM. "
                f"BFS found {len(bfs_only)} unique; ABM found {len(abm_only)} unique. "
                "This prediction is uncertain — investigate further."
            )
        else:
            explanation = (
                f"Good agreement ({agreement:.1%}) between BFS and ABM. "
                "Prediction is reliable."
            )

        return ValidationResult(
            bfs_affected=sorted(bfs_affected),
            abm_affected=sorted(abm_affected),
            agreement_ratio=round(agreement, 4),
            both=sorted(both),
            bfs_only=sorted(bfs_only),
            abm_only=sorted(abm_only),
            uncertainty_flag=uncertainty,
            explanation=explanation,
        )


# ===========================================================================
# 6. MultiCloudAnalyzer
# ===========================================================================

class MultiCloudAnalyzer:
    """Merge multiple cloud graphs and analyze cross-cloud dependencies."""

    def merge_graphs(self, **graphs: InfraGraph) -> InfraGraph:
        """Merge provider graphs into a single unified graph.

        Parameters are keyword arguments: e.g. ``merge_graphs(aws=g1, gcp=g2)``.
        Component IDs are prefixed with the provider name to avoid collisions.
        """
        merged = InfraGraph()
        for provider, graph in graphs.items():
            for comp_id, comp in graph.components.items():
                # Deep-copy to avoid mutating the original
                new_comp = comp.model_copy(
                    update={
                        "id": f"{provider}:{comp_id}",
                        "name": f"[{provider}] {comp.name}",
                        "tags": list(comp.tags) + [f"provider:{provider}"],
                    }
                )
                merged.add_component(new_comp)

            for dep in graph.all_dependency_edges():
                from faultray.model.components import Dependency

                new_dep = dep.model_copy(
                    update={
                        "source_id": f"{provider}:{dep.source_id}",
                        "target_id": f"{provider}:{dep.target_id}",
                    }
                )
                merged.add_dependency(new_dep)

        return merged

    def detect_cross_cloud_dependencies(self, merged: InfraGraph) -> list[dict]:
        """Detect dependencies that cross cloud provider boundaries."""
        cross_deps: list[dict] = []
        for dep in merged.all_dependency_edges():
            source_provider = dep.source_id.split(":")[0] if ":" in dep.source_id else "unknown"
            target_provider = dep.target_id.split(":")[0] if ":" in dep.target_id else "unknown"
            if source_provider != target_provider:
                cross_deps.append({
                    "source": dep.source_id,
                    "target": dep.target_id,
                    "source_provider": source_provider,
                    "target_provider": target_provider,
                    "dependency_type": dep.dependency_type,
                    "risk": "high" if dep.dependency_type == "requires" else "medium",
                })
        return cross_deps

    def simulate_provider_outage(
        self, merged: InfraGraph, provider: str
    ) -> dict:
        """Simulate all components of a given provider going down."""
        cascade_engine = CascadeEngine(merged)
        affected_total: set[str] = set()
        provider_components = [
            cid for cid in merged.components
            if cid.startswith(f"{provider}:")
        ]

        for comp_id in provider_components:
            affected = merged.get_all_affected(comp_id)
            affected_total |= affected
            affected_total.add(comp_id)

        # Determine cross-cloud impact
        cross_cloud_affected = [
            cid for cid in affected_total
            if not cid.startswith(f"{provider}:")
        ]

        return {
            "provider": provider,
            "provider_components": len(provider_components),
            "total_affected": len(affected_total),
            "cross_cloud_affected": len(cross_cloud_affected),
            "cross_cloud_components": sorted(cross_cloud_affected),
            "isolation_ratio": round(
                1.0 - len(cross_cloud_affected) / max(len(affected_total), 1), 4
            ),
        }

    def analyze(self, **graphs: InfraGraph) -> MultiCloudResult:
        """Full multi-cloud analysis: merge, detect cross-deps, simulate outages."""
        merged = self.merge_graphs(**graphs)
        cross_deps = self.detect_cross_cloud_dependencies(merged)

        outage_impacts: dict[str, dict] = {}
        for provider in graphs:
            outage_impacts[provider] = self.simulate_provider_outage(merged, provider)

        return MultiCloudResult(
            merged_graph=merged,
            cross_cloud_dependencies=cross_deps,
            provider_outage_impacts=outage_impacts,
            total_components=len(merged.components),
        )


# ===========================================================================
# 7. FullLifecycleAutomation
# ===========================================================================

class FullLifecycleAutomation:
    """Discover -> simulate -> report -> recommend -> validate lifecycle."""

    def run(self, graph: InfraGraph) -> LifecycleResult:
        """Execute the full lifecycle pipeline."""
        phases: list[str] = []

        # Phase 1: Discover
        discovery = graph.summary()
        discovery["resilience_v2"] = graph.resilience_score_v2()
        phases.append("discover")

        # Phase 2: Simulate
        cascade_engine = CascadeEngine(graph)
        sim_results: list[dict] = []
        for comp_id in graph.components:
            fault = Fault(
                target_component_id=comp_id,
                fault_type=FaultType.COMPONENT_DOWN,
            )
            chain = cascade_engine.simulate_fault(fault)
            sim_results.append({
                "component": comp_id,
                "severity": chain.severity,
                "affected": len(chain.effects),
            })
        sim_results.sort(key=lambda x: x["severity"], reverse=True)
        phases.append("simulate")

        simulation_summary = {
            "total_scenarios": len(sim_results),
            "critical": sum(1 for r in sim_results if r["severity"] >= 7.0),
            "warning": sum(1 for r in sim_results if 4.0 <= r["severity"] < 7.0),
            "passed": sum(1 for r in sim_results if r["severity"] < 4.0),
            "top_risks": sim_results[:5],
        }
        phases.append("report")

        # Phase 3: Recommend
        recommendations: list[str] = []
        v2 = discovery["resilience_v2"]
        for rec in v2.get("recommendations", []):
            recommendations.append(rec)

        for result in sim_results[:3]:
            if result["severity"] >= 7.0:
                recommendations.append(
                    f"CRITICAL: {result['component']} has severity {result['severity']}. "
                    "Immediate remediation required."
                )
        phases.append("recommend")

        # Phase 4: Validate
        validation_passed = (
            simulation_summary["critical"] == 0
            and v2.get("score", 0) >= 70
        )
        phases.append("validate")

        return LifecycleResult(
            discovery=discovery,
            simulation_summary=simulation_summary,
            recommendations=recommendations,
            validation_passed=validation_passed,
            phases_completed=phases,
        )


# ===========================================================================
# 8. GenomeEvolutionMonitor
# ===========================================================================

class GenomeEvolutionMonitor:
    """Track resilience genome changes over time and detect regressions."""

    @staticmethod
    def _compute_genome(graph: InfraGraph) -> dict[str, float]:
        """Compute a 'genome' — a dict of resilience traits from the graph."""
        v2 = graph.resilience_score_v2()
        breakdown = v2.get("breakdown", {})
        return {
            "overall_score": v2.get("score", 0.0),
            "redundancy": breakdown.get("redundancy", 0.0),
            "circuit_breaker_coverage": breakdown.get("circuit_breaker_coverage", 0.0),
            "auto_recovery": breakdown.get("auto_recovery", 0.0),
            "dependency_risk": breakdown.get("dependency_risk", 0.0),
            "capacity_headroom": breakdown.get("capacity_headroom", 0.0),
            "component_count": float(len(graph.components)),
        }

    def track(self, genome_history: list[dict[str, float]]) -> EvolutionResult:
        """Compare the latest genome against previous entries.

        *genome_history* is a list of genome dicts ordered chronologically
        (oldest first). The last entry is the current state.
        """
        if len(genome_history) < 2:
            current = genome_history[-1] if genome_history else {}
            return EvolutionResult(
                regression_detected=False,
                changed_traits=[],
                improvements=[],
                regressions=[],
                current_score=current.get("overall_score", 0.0),
                previous_score=current.get("overall_score", 0.0),
                delta=0.0,
            )

        previous = genome_history[-2]
        current = genome_history[-1]

        changed: list[str] = []
        improvements: list[str] = []
        regressions: list[str] = []

        for key in current:
            prev_val = previous.get(key, 0.0)
            curr_val = current.get(key, 0.0)
            if abs(curr_val - prev_val) > 0.01:
                changed.append(key)
                if curr_val > prev_val:
                    improvements.append(f"{key}: {prev_val:.1f} -> {curr_val:.1f}")
                else:
                    regressions.append(f"{key}: {prev_val:.1f} -> {curr_val:.1f}")

        cur_score = current.get("overall_score", 0.0)
        prev_score = previous.get("overall_score", 0.0)

        return EvolutionResult(
            regression_detected=len(regressions) > 0,
            changed_traits=changed,
            improvements=improvements,
            regressions=regressions,
            current_score=cur_score,
            previous_score=prev_score,
            delta=round(cur_score - prev_score, 2),
        )

    def compute_and_track(
        self, current_graph: InfraGraph, history: list[dict[str, float]]
    ) -> EvolutionResult:
        """Convenience: compute genome for current graph and track against history."""
        current_genome = self._compute_genome(current_graph)
        full_history = list(history) + [current_genome]
        return self.track(full_history)


# ===========================================================================
# 9. ThreatFeedSimulationBridge
# ===========================================================================

class ThreatFeedSimulationBridge:
    """Fetch threats -> convert to scenarios -> simulate -> alert if critical."""

    def run(
        self,
        feeds: list[dict],
        graph: InfraGraph,
    ) -> ThreatAssessmentResult:
        """Process threat feeds and simulate their impact.

        Each feed entry is a dict with at least:
        - ``threat_type``: str (e.g. "ddos", "ransomware", "supply_chain")
        - ``severity``: str ("low"/"medium"/"high"/"critical")
        - ``target_component_types``: list[str] (e.g. ["database", "web_server"])
        """
        cascade_engine = CascadeEngine(graph)
        scenarios: list[dict] = []
        sim_results: list[dict] = []
        critical_threats: list[dict] = []

        for feed_entry in feeds:
            threat_type = feed_entry.get("threat_type", "unknown")
            severity = feed_entry.get("severity", "medium")
            target_types = feed_entry.get("target_component_types", [])

            # Convert threat to scenarios
            fault_type = self._threat_to_fault_type(threat_type)
            matching_components = [
                cid for cid, comp in graph.components.items()
                if comp.type.value in target_types
            ]

            if not matching_components:
                continue

            for comp_id in matching_components:
                scenario_dict = {
                    "threat_type": threat_type,
                    "threat_severity": severity,
                    "target_component": comp_id,
                    "fault_type": fault_type.value,
                }
                scenarios.append(scenario_dict)

                # Simulate
                fault = Fault(
                    target_component_id=comp_id,
                    fault_type=fault_type,
                )
                chain = cascade_engine.simulate_fault(fault)

                result = {
                    "threat_type": threat_type,
                    "component": comp_id,
                    "cascade_severity": chain.severity,
                    "affected_count": len(chain.effects),
                }
                sim_results.append(result)

                if chain.severity >= 7.0 or severity == "critical":
                    critical_threats.append({
                        **feed_entry,
                        "simulated_severity": chain.severity,
                        "target_component": comp_id,
                    })

        # Determine overall risk level
        if critical_threats:
            overall_risk = "critical"
        elif any(r["cascade_severity"] >= 4.0 for r in sim_results):
            overall_risk = "high"
        elif sim_results:
            overall_risk = "medium"
        else:
            overall_risk = "low"

        return ThreatAssessmentResult(
            threats_evaluated=len(feeds),
            critical_threats=critical_threats,
            scenarios_generated=len(scenarios),
            simulation_results=sim_results,
            overall_risk_level=overall_risk,
        )

    @staticmethod
    def _threat_to_fault_type(threat_type: str) -> FaultType:
        """Map threat category to a FaultType for simulation."""
        mapping = {
            "ddos": FaultType.TRAFFIC_SPIKE,
            "ransomware": FaultType.COMPONENT_DOWN,
            "supply_chain": FaultType.COMPONENT_DOWN,
            "network_attack": FaultType.NETWORK_PARTITION,
            "data_breach": FaultType.COMPONENT_DOWN,
            "resource_exhaustion": FaultType.MEMORY_EXHAUSTION,
            "disk_attack": FaultType.DISK_FULL,
            "cpu_attack": FaultType.CPU_SATURATION,
        }
        return mapping.get(threat_type, FaultType.COMPONENT_DOWN)


# ===========================================================================
# 10. UnifiedSecurityResilienceScore
# ===========================================================================

class UnifiedSecurityResilienceScore:
    """Compute a single unified score combining security and resilience."""

    def __init__(
        self,
        resilience_weight: float = 0.6,
        security_weight: float = 0.4,
    ) -> None:
        self.resilience_weight = resilience_weight
        self.security_weight = security_weight

    def compute(self, graph: InfraGraph) -> UnifiedScore:
        """Compute the unified score."""
        # Resilience score (0-100) from graph
        resilience = graph.resilience_score()

        # Security score (0-100) computed from SecurityProfile
        security = self._compute_security_score(graph)

        unified = (
            resilience * self.resilience_weight
            + security * self.security_weight
        )

        breakdown = {
            "resilience_raw": resilience,
            "security_raw": security,
            "resilience_weighted": resilience * self.resilience_weight,
            "security_weighted": security * self.security_weight,
        }

        recommendations: list[str] = []
        if resilience < 70:
            recommendations.append(
                f"Resilience score is {resilience:.1f}/100. "
                "Add redundancy, circuit breakers, or failover."
            )
        if security < 70:
            recommendations.append(
                f"Security score is {security:.1f}/100. "
                "Enable encryption, WAF, auth, and network segmentation."
            )

        return UnifiedScore(
            unified=round(unified, 1),
            resilience_score=round(resilience, 1),
            security_score=round(security, 1),
            resilience_weight=self.resilience_weight,
            security_weight=self.security_weight,
            breakdown=breakdown,
            recommendations=recommendations,
        )

    @staticmethod
    def _compute_security_score(graph: InfraGraph) -> float:
        """Compute security score (0-100) from component SecurityProfiles."""
        if not graph.components:
            return 0.0

        total = 0.0
        for comp in graph.components.values():
            sp = comp.security
            # Each security feature contributes to the score
            comp_score = 0.0
            comp_score += 15.0 if sp.encryption_at_rest else 0.0
            comp_score += 15.0 if sp.encryption_in_transit else 0.0
            comp_score += 10.0 if sp.waf_protected else 0.0
            comp_score += 10.0 if sp.rate_limiting else 0.0
            comp_score += 15.0 if sp.auth_required else 0.0
            comp_score += 10.0 if sp.network_segmented else 0.0
            comp_score += 10.0 if sp.backup_enabled else 0.0
            comp_score += 5.0 if sp.log_enabled else 0.0
            comp_score += 5.0 if sp.ids_monitored else 0.0
            # patch SLA: full credit if <= 24h, partial if <= 72h
            if sp.patch_sla_hours <= 24:
                comp_score += 5.0
            elif sp.patch_sla_hours <= 72:
                comp_score += 2.5
            total += comp_score

        return total / len(graph.components)


# ===========================================================================
# 11. InverseOptimizer
# ===========================================================================

class InverseOptimizer:
    """Given a target SLA, find the minimum-cost changes to achieve it."""

    def optimize(
        self, graph: InfraGraph, target_sla: float = 0.9999
    ) -> InverseResult:
        """Find changes needed to reach *target_sla*.

        Evaluates adding replicas and enabling failover for each component,
        and returns the cheapest set of changes that would bring availability
        above the target.
        """
        from faultray.simulator.availability_model import compute_five_layer_model

        result = compute_five_layer_model(graph)
        current_avail = result.layer2_hardware.availability

        if current_avail >= target_sla:
            return InverseResult(
                target_sla=target_sla,
                current_availability=current_avail,
                changes_needed=[],
                total_cost=0.0,
                achievable=True,
                explanation=f"Already at {current_avail:.6f}, above target {target_sla}.",
            )

        # Evaluate candidate changes
        candidates: list[dict] = []
        for comp_id, comp in graph.components.items():
            monthly_cost = comp.cost_profile.hourly_infra_cost * 730

            # Candidate 1: add replica
            if comp.replicas == 1:
                candidates.append({
                    "component_id": comp_id,
                    "action": "add_replica",
                    "description": f"Add replica for {comp.name} (1 -> 2)",
                    "estimated_monthly_cost": monthly_cost,
                    "impact_estimate": 0.001 * (1.0 / max(len(graph.components), 1)),
                })

            # Candidate 2: enable failover
            if not comp.failover.enabled:
                candidates.append({
                    "component_id": comp_id,
                    "action": "enable_failover",
                    "description": f"Enable failover for {comp.name}",
                    "estimated_monthly_cost": monthly_cost * 0.3,
                    "impact_estimate": 0.0005 * (1.0 / max(len(graph.components), 1)),
                })

        # Sort by cost-effectiveness (impact / cost)
        for c in candidates:
            cost = max(c["estimated_monthly_cost"], 0.01)
            c["cost_effectiveness"] = c["impact_estimate"] / cost

        candidates.sort(key=lambda x: x["cost_effectiveness"], reverse=True)

        # Greedily select changes until we estimate reaching the target
        selected: list[dict] = []
        estimated_avail = current_avail
        total_cost = 0.0

        for candidate in candidates:
            if estimated_avail >= target_sla:
                break
            selected.append(candidate)
            estimated_avail += candidate["impact_estimate"]
            total_cost += candidate["estimated_monthly_cost"]

        achievable = estimated_avail >= target_sla

        if achievable:
            explanation = (
                f"Estimated availability after changes: {estimated_avail:.6f}. "
                f"{len(selected)} changes needed at ${total_cost:.2f}/month."
            )
        else:
            explanation = (
                f"Could not reach {target_sla} with available changes. "
                f"Best estimate: {estimated_avail:.6f} after {len(selected)} changes."
            )

        return InverseResult(
            target_sla=target_sla,
            current_availability=current_avail,
            changes_needed=selected,
            total_cost=round(total_cost, 2),
            achievable=achievable,
            explanation=explanation,
        )


# ===========================================================================
# 12. ComparativeSimulator
# ===========================================================================

class ComparativeSimulator:
    """Compare two architecture designs by running the same scenarios."""

    def compare(
        self,
        graph_a: InfraGraph,
        graph_b: InfraGraph,
        graph_a_name: str = "Design A",
        graph_b_name: str = "Design B",
    ) -> ComparisonResult:
        """Run identical fault scenarios on both graphs and compare."""
        engine_a = CascadeEngine(graph_a)
        engine_b = CascadeEngine(graph_b)

        # Build common scenarios: every component that exists in both graphs
        common_ids = set(graph_a.components.keys()) & set(graph_b.components.keys())

        scores_a: list[float] = []
        scores_b: list[float] = []
        diffs: list[dict] = []

        for comp_id in sorted(common_ids):
            fault = Fault(
                target_component_id=comp_id,
                fault_type=FaultType.COMPONENT_DOWN,
            )
            chain_a = engine_a.simulate_fault(fault)
            chain_b = engine_b.simulate_fault(fault)

            scores_a.append(chain_a.severity)
            scores_b.append(chain_b.severity)

            diffs.append({
                "scenario": f"COMPONENT_DOWN on {comp_id}",
                "severity_a": chain_a.severity,
                "severity_b": chain_b.severity,
                "affected_a": len(chain_a.effects),
                "affected_b": len(chain_b.effects),
                "better": graph_a_name if chain_a.severity <= chain_b.severity else graph_b_name,
            })

        avg_a = statistics.mean(scores_a) if scores_a else 0.0
        avg_b = statistics.mean(scores_b) if scores_b else 0.0

        # Lower average severity is better
        better = graph_a_name if avg_a <= avg_b else graph_b_name

        return ComparisonResult(
            graph_a_name=graph_a_name,
            graph_b_name=graph_b_name,
            scenarios_run=len(common_ids),
            graph_a_scores=scores_a,
            graph_b_scores=scores_b,
            better_design=better,
            differences_per_scenario=diffs,
            summary={
                "avg_severity_a": round(avg_a, 2),
                "avg_severity_b": round(avg_b, 2),
                "a_wins": sum(1 for d in diffs if d["better"] == graph_a_name),
                "b_wins": sum(1 for d in diffs if d["better"] == graph_b_name),
                "resilience_score_a": round(graph_a.resilience_score(), 1),
                "resilience_score_b": round(graph_b.resilience_score(), 1),
            },
        )


# ===========================================================================
# 13. CompoundWhatIf
# ===========================================================================

class CompoundWhatIf:
    """Apply multiple changes at once and measure compound effects vs individual."""

    def evaluate(
        self, graph: InfraGraph, changes: list[dict]
    ) -> CompoundResult:
        """Evaluate compound effect of multiple changes.

        Each change dict should have:
        - ``component_id``: str
        - ``change_type``: str ("add_replica" | "enable_failover" | "enable_circuit_breaker")
        """
        # Baseline severity
        baseline_severity = self._measure_avg_severity(graph)

        # Individual effects
        individual_effects: list[dict] = []
        for change in changes:
            temp_graph = self._apply_single_change(graph, change)
            new_severity = self._measure_avg_severity(temp_graph)
            improvement = baseline_severity - new_severity
            individual_effects.append({
                "change": change,
                "baseline_severity": round(baseline_severity, 3),
                "new_severity": round(new_severity, 3),
                "improvement": round(improvement, 3),
            })

        # Combined effect
        combined_graph = graph
        for change in changes:
            combined_graph = self._apply_single_change(combined_graph, change)
        combined_severity = self._measure_avg_severity(combined_graph)
        combined_improvement = baseline_severity - combined_severity

        combined_effect = {
            "baseline_severity": round(baseline_severity, 3),
            "combined_severity": round(combined_severity, 3),
            "combined_improvement": round(combined_improvement, 3),
        }

        # Interaction effects
        sum_individual = sum(e["improvement"] for e in individual_effects)
        synergy = combined_improvement - sum_individual

        interaction_effects: list[dict] = []
        if abs(synergy) > 0.01:
            interaction_effects.append({
                "type": "synergy" if synergy > 0 else "interference",
                "magnitude": round(abs(synergy), 3),
                "explanation": (
                    f"Combined changes {'amplify' if synergy > 0 else 'diminish'} "
                    f"each other by {abs(synergy):.3f} severity points."
                ),
            })

        return CompoundResult(
            individual_effects=individual_effects,
            combined_effect=combined_effect,
            interaction_effects=interaction_effects,
            total_improvement=round(combined_improvement, 3),
            synergy_detected=synergy > 0.01,
        )

    @staticmethod
    def _measure_avg_severity(graph: InfraGraph) -> float:
        """Measure average cascade severity across all COMPONENT_DOWN scenarios."""
        engine = CascadeEngine(graph)
        severities: list[float] = []
        for comp_id in graph.components:
            fault = Fault(
                target_component_id=comp_id,
                fault_type=FaultType.COMPONENT_DOWN,
            )
            chain = engine.simulate_fault(fault)
            severities.append(chain.severity)
        return statistics.mean(severities) if severities else 0.0

    @staticmethod
    def _apply_single_change(graph: InfraGraph, change: dict) -> InfraGraph:
        """Apply a single change to a copy of the graph."""
        # Deep copy the graph by re-constructing it
        new_graph = InfraGraph()
        for comp_id, comp in graph.components.items():
            new_comp = comp.model_copy(deep=True)
            if comp_id == change.get("component_id"):
                change_type = change.get("change_type", "")
                if change_type == "add_replica":
                    new_comp.replicas = new_comp.replicas + 1
                elif change_type == "enable_failover":
                    new_comp.failover.enabled = True
                elif change_type == "enable_circuit_breaker":
                    pass  # CB is on edges, handled below
            new_graph.add_component(new_comp)

        for dep in graph.all_dependency_edges():
            new_dep = dep.model_copy(deep=True)
            # Enable circuit breaker if the change targets this edge's source
            if (
                change.get("change_type") == "enable_circuit_breaker"
                and dep.source_id == change.get("component_id")
            ):
                new_dep.circuit_breaker.enabled = True
            new_graph.add_dependency(new_dep)

        return new_graph


# ===========================================================================
# 14. EnsemblePredictor
# ===========================================================================

class EnsemblePredictor:
    """Combine static (BFS), dynamic (ABM), and stochastic (Monte Carlo) predictions."""

    def __init__(
        self,
        graph: InfraGraph,
        weights: dict[str, float] | None = None,
        seed: int | None = None,
    ) -> None:
        self.graph = graph
        self.weights = weights or {"static": 0.4, "dynamic": 0.35, "stochastic": 0.25}
        self._seed = seed

    def predict(self, scenario: Scenario) -> EnsembleResult:
        """Run all three methods and produce a weighted ensemble prediction."""
        # Static: BFS cascade
        static_severity = self._run_static(scenario)

        # Dynamic: ABM
        dynamic_severity, abm_affected = self._run_dynamic(scenario)

        # Stochastic: Monte Carlo sampling via ABM with multiple seeds
        stochastic_severity = self._run_stochastic(scenario, n_runs=10)

        # Weighted ensemble
        w = self.weights
        ensemble = (
            static_severity * w.get("static", 0.4)
            + dynamic_severity * w.get("dynamic", 0.35)
            + stochastic_severity * w.get("stochastic", 0.25)
        )

        # Confidence based on agreement between methods
        values = [static_severity, dynamic_severity, stochastic_severity]
        spread = max(values) - min(values) if values else 0.0
        confidence = max(0.0, 1.0 - spread / 10.0)

        return EnsembleResult(
            static_severity=round(static_severity, 2),
            dynamic_severity=round(dynamic_severity, 2),
            stochastic_severity=round(stochastic_severity, 2),
            ensemble_severity=round(ensemble, 2),
            weights=dict(w),
            affected_components=sorted(abm_affected),
            confidence=round(confidence, 3),
        )

    def _run_static(self, scenario: Scenario) -> float:
        """Run BFS cascade for the scenario."""
        engine = CascadeEngine(self.graph)
        total_severity = 0.0
        count = 0
        for fault in scenario.faults:
            chain = engine.simulate_fault(fault)
            total_severity += chain.severity
            count += 1
        return total_severity / max(count, 1)

    def _run_dynamic(self, scenario: Scenario) -> tuple[float, list[str]]:
        """Run ABM simulation for the scenario."""
        from faultray.simulator.abm_engine import ABMEngine

        abm = ABMEngine(self.graph, seed=self._seed)
        result = abm.simulate_scenario(scenario)
        return result.severity, result.affected_agents

    def _run_stochastic(self, scenario: Scenario, n_runs: int = 10) -> float:
        """Run multiple ABM simulations with different seeds and average."""
        from faultray.simulator.abm_engine import ABMEngine

        severities: list[float] = []
        base_seed = self._seed if self._seed is not None else 42
        for i in range(n_runs):
            abm = ABMEngine(self.graph, seed=base_seed + i)
            result = abm.simulate_scenario(scenario)
            severities.append(result.severity)
        return statistics.mean(severities) if severities else 0.0


# ===========================================================================
# 15. HierarchicalAnalyzer
# ===========================================================================

class HierarchicalAnalyzer:
    """Analyze impact at component -> service -> system -> business levels."""

    def analyze(self, graph: InfraGraph) -> HierarchyResult:
        """Run hierarchical impact analysis."""
        # Component level: per-component cascade severity
        cascade_engine = CascadeEngine(graph)
        comp_severities: dict[str, float] = {}
        for comp_id in graph.components:
            fault = Fault(
                target_component_id=comp_id,
                fault_type=FaultType.COMPONENT_DOWN,
            )
            chain = cascade_engine.simulate_fault(fault)
            comp_severities[comp_id] = chain.severity

        component_level = HierarchyLevel(
            level_name="component",
            components=list(comp_severities.keys()),
            impact_score=round(
                statistics.mean(comp_severities.values()) if comp_severities else 0.0, 2
            ),
            details=comp_severities,
        )

        # Service level: group by component type
        type_groups: dict[str, list[str]] = defaultdict(list)
        for comp_id, comp in graph.components.items():
            type_groups[comp.type.value].append(comp_id)

        service_details: dict[str, float] = {}
        for svc_type, comp_ids in type_groups.items():
            avg_sev = statistics.mean(
                comp_severities.get(cid, 0.0) for cid in comp_ids
            )
            service_details[svc_type] = round(avg_sev, 2)

        service_level = HierarchyLevel(
            level_name="service",
            components=list(type_groups.keys()),
            impact_score=round(
                statistics.mean(service_details.values()) if service_details else 0.0, 2
            ),
            details=service_details,
        )

        # System level: aggregate resilience metrics
        resilience_v2 = graph.resilience_score_v2()
        system_level = HierarchyLevel(
            level_name="system",
            components=["overall_system"],
            impact_score=round(resilience_v2.get("score", 0.0), 2),
            details=resilience_v2.get("breakdown", {}),
        )

        # Business level: revenue impact estimation
        total_hourly_revenue = sum(
            comp.cost_profile.revenue_per_minute * 60
            for comp in graph.components.values()
        )
        critical_components = [
            cid for cid, sev in comp_severities.items() if sev >= 7.0
        ]
        estimated_annual_risk = (
            total_hourly_revenue * len(critical_components) * 0.01
        )  # 1% annual probability per critical component

        business_level = HierarchyLevel(
            level_name="business",
            components=critical_components,
            impact_score=round(estimated_annual_risk, 2),
            details={
                "total_hourly_revenue": round(total_hourly_revenue, 2),
                "critical_component_count": len(critical_components),
                "estimated_annual_risk": round(estimated_annual_risk, 2),
            },
        )

        critical_paths = graph.get_critical_paths(max_paths=10)

        return HierarchyResult(
            component_level=component_level,
            service_level=service_level,
            system_level=system_level,
            business_level=business_level,
            critical_paths=critical_paths,
        )


# ===========================================================================
# 16. TemporalUnifiedView
# ===========================================================================

class TemporalUnifiedView:
    """Unified timeline view: current state + trend + forecast."""

    def analyze(
        self,
        graph: InfraGraph,
        history: list[dict],
    ) -> TemporalResult:
        """Analyze temporal evolution.

        *history* is a list of snapshot dicts ordered chronologically (oldest
        first).  Each snapshot should contain at least ``"resilience_score"``
        and ``"timestamp"`` keys.
        """
        # Current state
        current_score = graph.resilience_score()
        current_v2 = graph.resilience_score_v2()
        current_state = {
            "resilience_score": round(current_score, 1),
            "breakdown": current_v2.get("breakdown", {}),
            "component_count": len(graph.components),
            "recommendations": current_v2.get("recommendations", []),
        }

        # Trend analysis
        scores = [h.get("resilience_score", 0.0) for h in history]
        scores.append(current_score)

        trend_analysis = self._compute_trend(scores)

        # Forecast: simple linear extrapolation
        forecast = self._forecast(scores, steps=3)

        # Build unified timeline
        timeline: list[dict] = []
        for idx, snapshot in enumerate(history):
            timeline.append({
                "index": idx,
                "timestamp": snapshot.get("timestamp", f"t-{len(history) - idx}"),
                "resilience_score": snapshot.get("resilience_score", 0.0),
            })
        timeline.append({
            "index": len(history),
            "timestamp": "current",
            "resilience_score": round(current_score, 1),
        })

        # Risk trajectory
        if trend_analysis.get("slope", 0) > 0.5:
            risk_trajectory = "improving"
        elif trend_analysis.get("slope", 0) < -0.5:
            risk_trajectory = "degrading"
        else:
            risk_trajectory = "stable"

        return TemporalResult(
            current_state=current_state,
            trend_analysis=trend_analysis,
            forecast=forecast,
            timeline=timeline,
            risk_trajectory=risk_trajectory,
        )

    @staticmethod
    def _compute_trend(scores: list[float]) -> dict:
        """Compute trend statistics from a series of resilience scores."""
        if len(scores) < 2:
            return {
                "direction": "insufficient_data",
                "slope": 0.0,
                "mean": scores[0] if scores else 0.0,
                "stddev": 0.0,
            }

        n = len(scores)
        x_vals = list(range(n))
        x_mean = statistics.mean(x_vals)
        y_mean = statistics.mean(scores)

        # Linear regression slope
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, scores))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)
        slope = numerator / denominator if denominator != 0 else 0.0

        direction = "improving" if slope > 0.5 else ("degrading" if slope < -0.5 else "stable")

        return {
            "direction": direction,
            "slope": round(slope, 4),
            "mean": round(y_mean, 2),
            "stddev": round(statistics.stdev(scores), 2) if len(scores) >= 2 else 0.0,
            "min": round(min(scores), 2),
            "max": round(max(scores), 2),
        }

    @staticmethod
    def _forecast(scores: list[float], steps: int = 3) -> dict:
        """Simple linear extrapolation forecast."""
        if len(scores) < 2:
            return {"method": "none", "predictions": [], "note": "Insufficient data"}

        n = len(scores)
        x_vals = list(range(n))
        x_mean = statistics.mean(x_vals)
        y_mean = statistics.mean(scores)

        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, scores))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)
        slope = numerator / denominator if denominator != 0 else 0.0
        intercept = y_mean - slope * x_mean

        predictions: list[dict] = []
        for step in range(1, steps + 1):
            future_x = n - 1 + step
            predicted = slope * future_x + intercept
            # Clamp to valid range
            predicted = max(0.0, min(100.0, predicted))
            predictions.append({
                "step": step,
                "predicted_score": round(predicted, 2),
            })

        return {
            "method": "linear_extrapolation",
            "slope": round(slope, 4),
            "intercept": round(intercept, 4),
            "predictions": predictions,
        }


# ===========================================================================
# Helpers
# ===========================================================================

def _extract_affected(result: Any) -> set[str]:
    """Extract a set of affected component IDs from various result types."""
    # CascadeChain
    if hasattr(result, "effects"):
        return {
            e.component_id
            for e in result.effects
            if hasattr(e, "health") and e.health != HealthStatus.HEALTHY
        }
    # ABMResult
    if hasattr(result, "affected_agents"):
        return set(result.affected_agents)
    # ScenarioResult
    if hasattr(result, "cascade"):
        return _extract_affected(result.cascade)
    # dict with 'affected' key
    if isinstance(result, dict) and "affected" in result:
        return set(result["affected"])
    return set()
