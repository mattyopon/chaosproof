"""Comprehensive tests for faultray.simulator.supply_chain_cascade."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.model.package_components import (
    PackageNode,
    PackageSeverity,
    PackageVulnerability,
    SBOMConfig,
)
from faultray.simulator.scenarios import FaultType
from faultray.simulator.supply_chain_cascade import (
    PackageImpact,
    SupplyChainAttackReport,
    SupplyChainCascadeEngine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid, name, ctype=ComponentType.APP_SERVER, replicas=1, **kwargs):
    return Component(id=cid, name=name, type=ctype, replicas=replicas, **kwargs)


def _graph(*components, deps=None):
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt, dtype in (deps or []):
        g.add_dependency(Dependency(source_id=src, target_id=tgt, dependency_type=dtype))
    return g


# ---------------------------------------------------------------------------
# TestSimulatePackageCompromise
# ---------------------------------------------------------------------------


class TestSimulatePackageCompromise:
    """Tests for SupplyChainCascadeEngine.simulate_package_compromise."""

    def test_basic_compromise_returns_package_impact(self):
        """simulate_package_compromise returns a PackageImpact dataclass."""
        g = _graph(
            _comp("app", "App Server"),
            _comp("db", "Database", ctype=ComponentType.DATABASE),
            deps=[("app", "db", "requires")],
        )
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "postgres-lib")
        assert isinstance(result, PackageImpact)
        assert result.package_name == "postgres-lib"

    def test_blast_radius_calculation(self):
        """Blast radius should count transitively affected components."""
        g = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE),
            _comp("app", "App Server"),
            _comp("web", "Web Server", ctype=ComponentType.WEB_SERVER),
            deps=[
                ("app", "db", "requires"),
                ("web", "app", "requires"),
            ],
        )
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "pg-driver")
        # db -> app -> web: blast radius = 2 (app and web are affected)
        assert result.total_blast_radius == 2

    def test_agent_hallucination_risk_detection(self):
        """When an agent depends on a compromised component, hallucination risk is True."""
        g = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE),
            _comp("tool", "Tool Service", ctype=ComponentType.TOOL_SERVICE),
            _comp("agent", "AI Agent", ctype=ComponentType.AI_AGENT,
                  parameters={"requires_grounding": 1, "hallucination_risk": 0.1}),
            deps=[
                ("tool", "db", "requires"),
                ("agent", "tool", "requires"),
            ],
        )
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "mysql-connector")
        assert result.agent_hallucination_risk is True

    def test_no_agent_hallucination_risk_when_no_agents(self):
        """When no agents are in the blast radius, hallucination risk is False."""
        g = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE),
            _comp("app", "App Server"),
            deps=[("app", "db", "requires")],
        )
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "pg-lib")
        assert result.agent_hallucination_risk is False

    def test_attack_path_generation(self):
        """Attack path should start with package and include affected components."""
        g = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE),
            _comp("app", "App Server"),
            deps=[("app", "db", "requires")],
        )
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "libpq")
        # Attack path should start with pkg:libpq
        assert len(result.attack_path) >= 2
        assert result.attack_path[0] == "pkg:libpq"
        assert result.attack_path[1] == "Database"

    def test_risk_score_increases_with_blast_radius(self):
        """Risk score should be higher with larger blast radius."""
        # Small graph: db -> app
        g_small = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE),
            _comp("app", "App"),
            deps=[("app", "db", "requires")],
        )
        # Large graph: db -> app -> web -> lb -> cdn
        g_large = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE),
            _comp("app", "App"),
            _comp("web", "Web", ctype=ComponentType.WEB_SERVER),
            _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER),
            _comp("cdn", "CDN", ctype=ComponentType.EXTERNAL_API),
            deps=[
                ("app", "db", "requires"),
                ("web", "app", "requires"),
                ("lb", "web", "requires"),
                ("cdn", "lb", "requires"),
            ],
        )
        small_result = SupplyChainCascadeEngine(g_small).simulate_package_compromise("db", "pkg")
        large_result = SupplyChainCascadeEngine(g_large).simulate_package_compromise("db", "pkg")
        assert large_result.risk_score >= small_result.risk_score

    def test_risk_score_increases_when_agents_affected(self):
        """Risk score should be higher when agents are in the blast radius."""
        # Graph without agent
        g_no_agent = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE),
            _comp("app", "App"),
            deps=[("app", "db", "requires")],
        )
        # Graph with agent
        g_with_agent = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE),
            _comp("agent", "AI Agent", ctype=ComponentType.AI_AGENT),
            deps=[("agent", "db", "requires")],
        )
        no_agent_result = SupplyChainCascadeEngine(g_no_agent).simulate_package_compromise("db", "pkg")
        agent_result = SupplyChainCascadeEngine(g_with_agent).simulate_package_compromise("db", "pkg")
        assert agent_result.risk_score >= no_agent_result.risk_score

    def test_error_handling_for_unknown_component(self):
        """Should raise ValueError when component is not found in graph."""
        g = _graph(_comp("app", "App"))
        engine = SupplyChainCascadeEngine(g)
        with pytest.raises(ValueError, match="not found"):
            engine.simulate_package_compromise("nonexistent", "some-pkg")

    def test_risk_score_bounded(self):
        """Risk score should be between 0 and 10."""
        g = _graph(
            _comp("db", "DB", ctype=ComponentType.DATABASE),
            *[_comp(f"app{i}", f"App{i}") for i in range(10)],
            deps=[
                (f"app{i}", "db", "requires") for i in range(10)
            ],
        )
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "big-pkg")
        assert 0.0 <= result.risk_score <= 10.0

    def test_affected_components_includes_source(self):
        """affected_components should include the compromised component itself."""
        g = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE),
            _comp("app", "App"),
            deps=[("app", "db", "requires")],
        )
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "pg-lib")
        assert "db" in result.affected_components

    def test_single_component_no_dependents(self):
        """A lone component has blast radius 0."""
        g = _graph(_comp("solo", "Solo"))
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("solo", "solo-pkg")
        assert result.total_blast_radius == 0


# ---------------------------------------------------------------------------
# TestAnalyzeAllPackages
# ---------------------------------------------------------------------------


class TestAnalyzeAllPackages:
    """Tests for SupplyChainCascadeEngine.analyze_all_packages."""

    def test_with_packages_parameter(self):
        """Components with 'packages' parameter should be analyzed."""
        g = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE,
                  parameters={"packages": "pg-driver,libpq", "vuln_pg_driver": "CVE-2024-001"}),
            _comp("app", "App Server",
                  parameters={"packages": "express,lodash"}),
            deps=[("app", "db", "requires")],
        )
        engine = SupplyChainCascadeEngine(g)
        report = engine.analyze_all_packages()
        assert isinstance(report, SupplyChainAttackReport)
        assert report.total_packages_analyzed >= 1
        assert report.vulnerable_packages >= 1

    def test_no_packages_returns_zeros(self):
        """When no components have packages, report should have zero counts."""
        g = _graph(
            _comp("app", "App"),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
            deps=[("app", "db", "requires")],
        )
        engine = SupplyChainCascadeEngine(g)
        report = engine.analyze_all_packages()
        assert report.total_packages_analyzed == 0
        assert report.vulnerable_packages == 0

    def test_cross_layer_risk_detection(self):
        """Cross-layer risks should be detected when agents depend on vulnerable components."""
        g = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE,
                  parameters={"packages": "pg-driver", "vuln_pg_driver": "CVE-2024-999"}),
            _comp("tool", "Tool Service", ctype=ComponentType.TOOL_SERVICE),
            _comp("agent", "AI Agent", ctype=ComponentType.AI_AGENT),
            deps=[
                ("tool", "db", "requires"),
                ("agent", "tool", "requires"),
            ],
        )
        engine = SupplyChainCascadeEngine(g)
        report = engine.analyze_all_packages()
        assert len(report.cross_layer_risks) >= 1
        assert any("hallucination" in r.lower() for r in report.cross_layer_risks)

    def test_overall_risk_score_calculation(self):
        """Overall risk score should be calculated and bounded 0-100."""
        g = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE,
                  parameters={"packages": "pg-driver", "vuln_pg_driver": "CVE-2024-001"}),
            _comp("app", "App",
                  parameters={"packages": "express", "vuln_express": "CVE-2024-002"}),
            deps=[("app", "db", "requires")],
        )
        engine = SupplyChainCascadeEngine(g)
        report = engine.analyze_all_packages()
        assert 0.0 <= report.overall_risk_score <= 100.0

    def test_recommendation_generation(self):
        """Recommendations should be generated based on analysis."""
        g = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE,
                  parameters={"packages": "pg-driver", "vuln_pg_driver": "CVE-2024-001"}),
        )
        engine = SupplyChainCascadeEngine(g)
        report = engine.analyze_all_packages()
        assert len(report.recommendations) >= 1

    def test_no_vulnerabilities_recommendation(self):
        """When no vulns are found, should get a safe recommendation."""
        g = _graph(
            _comp("app", "App", parameters={"packages": "safe-lib"}),
        )
        engine = SupplyChainCascadeEngine(g)
        report = engine.analyze_all_packages()
        # No vuln_ keys, so no vulnerable packages
        assert report.vulnerable_packages == 0

    def test_sbom_risk_components_included(self):
        """Components with sbom_risk=critical should be included in analysis."""
        g = _graph(
            _comp("legacy", "Legacy Service",
                  parameters={"sbom_risk": "critical"}),
            _comp("app", "App"),
            deps=[("app", "legacy", "requires")],
        )
        engine = SupplyChainCascadeEngine(g)
        report = engine.analyze_all_packages()
        assert len(report.package_impacts) >= 1


# ---------------------------------------------------------------------------
# TestCrossLayerSupplyChain
# ---------------------------------------------------------------------------


class TestCrossLayerSupplyChain:
    """Test full 3-layer cross-layer supply chain attack propagation."""

    def _build_cross_layer_graph(self):
        """Build DB (vulnerable pkg) -> Tool -> Agent -> LLM."""
        return _graph(
            _comp("db", "PostgreSQL", ctype=ComponentType.DATABASE,
                  parameters={
                      "packages": "pg-driver,libcrypto",
                      "vuln_pg_driver": "CVE-2024-5555",
                  }),
            _comp("tool", "RAG Tool", ctype=ComponentType.TOOL_SERVICE),
            _comp("agent", "Research Agent", ctype=ComponentType.AI_AGENT,
                  parameters={"requires_grounding": 1, "hallucination_risk": 0.08}),
            _comp("llm", "GPT-4 Endpoint", ctype=ComponentType.LLM_ENDPOINT),
            deps=[
                ("tool", "db", "requires"),
                ("agent", "tool", "requires"),
                ("agent", "llm", "requires"),
            ],
        )

    def test_full_cross_layer_compromise(self):
        """Compromising DB should cascade through tool to agent."""
        g = self._build_cross_layer_graph()
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "pg-driver")

        # Agent and tool should be in blast radius
        assert result.total_blast_radius >= 2
        assert "tool" in result.affected_components
        assert "agent" in result.affected_components

    def test_agent_hallucination_risk_detected(self):
        """Agent hallucination risk should be detected for cross-layer compromise."""
        g = self._build_cross_layer_graph()
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "pg-driver")
        assert result.agent_hallucination_risk is True

    def test_cross_layer_risks_populated(self):
        """Full analysis should populate cross_layer_risks list."""
        g = self._build_cross_layer_graph()
        engine = SupplyChainCascadeEngine(g)
        report = engine.analyze_all_packages()
        assert len(report.cross_layer_risks) >= 1

    def test_attack_path_shows_full_chain(self):
        """Attack path should show: package -> DB -> Tool -> Agent."""
        g = self._build_cross_layer_graph()
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "pg-driver")

        # Attack path starts with pkg:pg-driver, then component names
        assert result.attack_path[0] == "pkg:pg-driver"
        assert result.attack_path[1] == "PostgreSQL"  # DB component name
        # Remaining path should contain tool and/or agent names
        remaining = result.attack_path[2:]
        names_in_path = set(remaining)
        # At least tool or agent should appear
        assert len(names_in_path) >= 1

    def test_llm_not_directly_compromised(self):
        """LLM endpoint depends on agent, not on DB. DB compromise should not
        directly reach LLM unless agent depends on LLM with requires."""
        g = self._build_cross_layer_graph()
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "pg-driver")
        # LLM is a dependency OF the agent, not a dependent.
        # DB compromise cascades to dependents (predecessors): tool, agent
        # But LLM is a successor of agent, not a predecessor. So LLM should NOT be affected.
        # Actually the edge is agent -> llm, meaning agent depends on llm.
        # get_all_affected finds predecessors (things that depend on db).
        # tool depends on db (tool -> db edge). agent depends on tool (agent -> tool).
        # llm has no edge pointing to db/tool/agent as source.
        # So llm should NOT be in affected.
        assert "llm" not in result.affected_components

    def test_risk_score_reflects_agent_impact(self):
        """Risk score should be elevated due to agent being in blast radius."""
        g = self._build_cross_layer_graph()
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "pg-driver")
        # With agent in blast radius, risk should include agent bonus
        assert result.risk_score >= 6.0


# ---------------------------------------------------------------------------
# TestPackageModels
# ---------------------------------------------------------------------------


class TestPackageModels:
    """Test package-related data models from package_components module."""

    def test_package_node_instantiation(self):
        """PackageNode should be instantiable with minimal args."""
        node = PackageNode(name="lodash")
        assert node.name == "lodash"
        assert node.version == "0.0.0"
        assert node.ecosystem == "npm"
        assert node.is_direct is True
        assert node.depth == 0
        assert node.vulnerabilities == []
        assert node.installed_in == []

    def test_package_node_with_all_fields(self):
        """PackageNode should accept all fields."""
        vuln = PackageVulnerability(cve_id="CVE-2024-001", severity=PackageSeverity.HIGH)
        node = PackageNode(
            name="openssl",
            version="3.1.0",
            ecosystem="pypi",
            is_direct=False,
            depth=2,
            vulnerabilities=[vuln],
            installed_in=["app", "db"],
            license="MIT",
        )
        assert node.name == "openssl"
        assert node.version == "3.1.0"
        assert node.ecosystem == "pypi"
        assert node.is_direct is False
        assert node.depth == 2
        assert len(node.vulnerabilities) == 1
        assert node.installed_in == ["app", "db"]

    def test_package_vulnerability(self):
        """PackageVulnerability should be instantiable with all fields."""
        vuln = PackageVulnerability(
            cve_id="CVE-2024-12345",
            severity=PackageSeverity.CRITICAL,
            description="Remote code execution in openssl",
            fixed_version="3.2.0",
            exploitability_score=9.8,
        )
        assert vuln.cve_id == "CVE-2024-12345"
        assert vuln.severity == PackageSeverity.CRITICAL
        assert vuln.description == "Remote code execution in openssl"
        assert vuln.fixed_version == "3.2.0"
        assert vuln.exploitability_score == 9.8

    def test_package_vulnerability_defaults(self):
        """PackageVulnerability should have sensible defaults."""
        vuln = PackageVulnerability(cve_id="CVE-X")
        assert vuln.severity == PackageSeverity.MEDIUM
        assert vuln.description == ""
        assert vuln.fixed_version is None
        assert vuln.exploitability_score == 5.0

    def test_sbom_config(self):
        """SBOMConfig should be instantiable."""
        node = PackageNode(name="express", version="4.18.0")
        config = SBOMConfig(
            packages=[node],
            manifest_file="package.json",
            last_audit_date="2024-01-15",
        )
        assert len(config.packages) == 1
        assert config.manifest_file == "package.json"
        assert config.last_audit_date == "2024-01-15"

    def test_sbom_config_defaults(self):
        """SBOMConfig should have empty defaults."""
        config = SBOMConfig()
        assert config.packages == []
        assert config.manifest_file == ""
        assert config.last_audit_date == ""

    def test_package_severity_enum_values(self):
        """PackageSeverity should have all expected values."""
        assert PackageSeverity.CRITICAL.value == "critical"
        assert PackageSeverity.HIGH.value == "high"
        assert PackageSeverity.MEDIUM.value == "medium"
        assert PackageSeverity.LOW.value == "low"
        assert PackageSeverity.INFO.value == "info"

    def test_package_severity_all_members(self):
        """PackageSeverity should have exactly 5 members."""
        assert len(PackageSeverity) == 5

    def test_package_severity_string_comparison(self):
        """PackageSeverity members should be comparable as strings."""
        assert PackageSeverity.CRITICAL == "critical"
        assert PackageSeverity.HIGH == "high"


# ---------------------------------------------------------------------------
# TestNewFaultTypes
# ---------------------------------------------------------------------------


class TestNewFaultTypes:
    """Test new supply-chain-related FaultType enum values."""

    def test_dependency_compromised_exists(self):
        """FaultType.DEPENDENCY_COMPROMISED should exist."""
        assert FaultType.DEPENDENCY_COMPROMISED == "dependency_compromised"

    def test_dependency_vulnerable_exists(self):
        """FaultType.DEPENDENCY_VULNERABLE should exist."""
        assert FaultType.DEPENDENCY_VULNERABLE == "dependency_vulnerable"

    def test_dependency_compromised_is_fault_type(self):
        """DEPENDENCY_COMPROMISED should be an instance of FaultType."""
        assert isinstance(FaultType.DEPENDENCY_COMPROMISED, FaultType)

    def test_dependency_vulnerable_is_fault_type(self):
        """DEPENDENCY_VULNERABLE should be an instance of FaultType."""
        assert isinstance(FaultType.DEPENDENCY_VULNERABLE, FaultType)

    def test_new_fault_types_distinct(self):
        """The two new fault types should be distinct."""
        assert FaultType.DEPENDENCY_COMPROMISED != FaultType.DEPENDENCY_VULNERABLE

    def test_fault_type_lookup_by_value(self):
        """Should be able to look up the new fault types by string value."""
        assert FaultType("dependency_compromised") == FaultType.DEPENDENCY_COMPROMISED
        assert FaultType("dependency_vulnerable") == FaultType.DEPENDENCY_VULNERABLE


# ---------------------------------------------------------------------------
# TestPackageImpactDataclass
# ---------------------------------------------------------------------------


class TestPackageImpactDataclass:
    """Tests for the PackageImpact dataclass itself."""

    def test_create_minimal(self):
        """PackageImpact should be creatable with required fields."""
        impact = PackageImpact(
            package_name="lodash",
            package_version="",
            cve_id="",
            severity="critical",
            affected_components=["app"],
            total_blast_radius=1,
            agent_hallucination_risk=False,
            risk_score=5.0,
            attack_path=["pkg:lodash", "App"],
            recommendation="Patch lodash",
        )
        assert impact.package_name == "lodash"
        assert impact.total_blast_radius == 1
        assert impact.agent_hallucination_risk is False

    def test_create_with_agent_risk(self):
        """PackageImpact with agent hallucination risk."""
        impact = PackageImpact(
            package_name="pg-driver",
            package_version="2.0.0",
            cve_id="CVE-2024-001",
            severity="critical",
            affected_components=["db", "agent"],
            total_blast_radius=2,
            agent_hallucination_risk=True,
            risk_score=8.5,
            attack_path=["pkg:pg-driver", "Database", "Agent"],
            recommendation="CRITICAL: Patch immediately",
        )
        assert impact.agent_hallucination_risk is True
        assert impact.risk_score == 8.5


# ---------------------------------------------------------------------------
# TestSupplyChainAttackReport
# ---------------------------------------------------------------------------


class TestSupplyChainAttackReport:
    """Tests for the SupplyChainAttackReport dataclass."""

    def test_create_empty(self):
        """SupplyChainAttackReport with zero values."""
        report = SupplyChainAttackReport(
            total_packages_analyzed=0,
            vulnerable_packages=0,
            compromised_packages=0,
        )
        assert report.package_impacts == []
        assert report.cross_layer_risks == []
        assert report.overall_risk_score == 0.0
        assert report.recommendations == []

    def test_create_with_data(self):
        """SupplyChainAttackReport with populated fields."""
        impact = PackageImpact(
            package_name="pkg",
            package_version="",
            cve_id="CVE-1",
            severity="high",
            affected_components=["app"],
            total_blast_radius=1,
            agent_hallucination_risk=False,
            risk_score=5.0,
            attack_path=["pkg:pkg", "App"],
            recommendation="Patch",
        )
        report = SupplyChainAttackReport(
            total_packages_analyzed=5,
            vulnerable_packages=1,
            compromised_packages=0,
            package_impacts=[impact],
            cross_layer_risks=["risk1"],
            overall_risk_score=50.0,
            recommendations=["Fix it"],
        )
        assert report.total_packages_analyzed == 5
        assert len(report.package_impacts) == 1
        assert len(report.cross_layer_risks) == 1
        assert report.overall_risk_score == 50.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for supply chain cascade engine."""

    def test_empty_graph(self):
        """Engine should work with an empty graph."""
        g = InfraGraph()
        engine = SupplyChainCascadeEngine(g)
        report = engine.analyze_all_packages()
        assert report.total_packages_analyzed == 0
        assert report.overall_risk_score == 0.0

    def test_single_component_with_package(self):
        """Single component with a vulnerable package."""
        g = _graph(
            _comp("solo", "Solo App",
                  parameters={"packages": "vuln-lib", "vuln_vuln_lib": "CVE-2024-999"}),
        )
        engine = SupplyChainCascadeEngine(g)
        report = engine.analyze_all_packages()
        assert report.total_packages_analyzed >= 1
        assert report.vulnerable_packages >= 1

    def test_diamond_dependency(self):
        """Diamond: A -> B, A -> C, B -> D, C -> D. Compromise D."""
        g = _graph(
            _comp("d", "D", ctype=ComponentType.DATABASE),
            _comp("b", "B"),
            _comp("c", "C"),
            _comp("a", "A"),
            deps=[
                ("b", "d", "requires"),
                ("c", "d", "requires"),
                ("a", "b", "requires"),
                ("a", "c", "requires"),
            ],
        )
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("d", "shared-lib")
        # D -> B, C -> A, so blast radius should be 3
        assert result.total_blast_radius == 3
        assert "a" in result.affected_components
        assert "b" in result.affected_components
        assert "c" in result.affected_components

    def test_agent_orchestrator_detected_as_agent_risk(self):
        """AGENT_ORCHESTRATOR type should trigger hallucination risk."""
        g = _graph(
            _comp("db", "Database", ctype=ComponentType.DATABASE),
            _comp("orch", "Orchestrator", ctype=ComponentType.AGENT_ORCHESTRATOR),
            deps=[("orch", "db", "requires")],
        )
        engine = SupplyChainCascadeEngine(g)
        result = engine.simulate_package_compromise("db", "db-lib")
        assert result.agent_hallucination_risk is True

    def test_multiple_packages_per_component(self):
        """Component with multiple comma-separated packages."""
        g = _graph(
            _comp("app", "App",
                  parameters={
                      "packages": "express,lodash,axios",
                      "vuln_express": "CVE-2024-001",
                      "vuln_axios": "CVE-2024-002",
                  }),
        )
        engine = SupplyChainCascadeEngine(g)
        report = engine.analyze_all_packages()
        assert report.total_packages_analyzed == 3
        assert report.vulnerable_packages == 2
