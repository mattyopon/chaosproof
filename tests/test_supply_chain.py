"""Tests for the Supply Chain Risk Engine."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from infrasim.model.components import Component, ComponentType, Dependency
from infrasim.model.graph import InfraGraph
from infrasim.simulator.supply_chain_engine import (
    SupplyChainEngine,
    SupplyChainReport,
    VulnerabilityImpact,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph() -> InfraGraph:
    """Build a typical 3-tier infrastructure graph."""
    g = InfraGraph()
    g.add_component(
        Component(id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER)
    )
    g.add_component(
        Component(id="app", name="App Server", type=ComponentType.APP_SERVER)
    )
    g.add_component(
        Component(id="db", name="Database", type=ComponentType.DATABASE)
    )
    g.add_component(
        Component(id="cache", name="Cache", type=ComponentType.CACHE)
    )
    g.add_dependency(Dependency(source_id="lb", target_id="app"))
    g.add_dependency(Dependency(source_id="app", target_id="db"))
    g.add_dependency(Dependency(source_id="app", target_id="cache"))
    return g


def _write_vuln_file(data: list | dict, tmp_path: Path) -> Path:
    """Write vulnerability data to a JSON file."""
    p = tmp_path / "vulns.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# map_cve_to_impact tests
# ---------------------------------------------------------------------------


class TestMapCveToImpact:
    def test_critical_on_database(self):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        impact = engine.map_cve_to_impact(
            "CVE-2024-0001", "critical", ["db"], package="postgres"
        )
        assert impact.cve_id == "CVE-2024-0001"
        assert impact.severity == "critical"
        assert impact.infrastructure_impact == "data breach"
        assert impact.risk_score > 0

    def test_high_on_app_server(self):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        impact = engine.map_cve_to_impact(
            "CVE-2024-0002", "high", ["app"], package="express"
        )
        assert impact.severity == "high"
        assert impact.infrastructure_impact == "OOM"

    def test_medium_on_cache(self):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        impact = engine.map_cve_to_impact(
            "CVE-2024-0003", "medium", ["cache"], package="redis"
        )
        assert impact.severity == "medium"
        assert impact.infrastructure_impact == "degraded hit ratio"

    def test_blast_radius_calculation(self):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        # DB failure affects app (dependent) and lb (transitive)
        impact = engine.map_cve_to_impact(
            "CVE-2024-0004", "critical", ["db"]
        )
        assert impact.estimated_blast_radius >= 1


# ---------------------------------------------------------------------------
# analyze_from_file tests (various formats)
# ---------------------------------------------------------------------------


class TestAnalyzeFromFile:
    def test_snyk_format(self, tmp_path: Path):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        data = {
            "vulnerabilities": [
                {
                    "id": "CVE-2024-1111",
                    "severity": "critical",
                    "package": "pg",
                    "description": "SQL injection in postgres driver",
                },
                {
                    "id": "CVE-2024-2222",
                    "severity": "medium",
                    "package": "express",
                    "description": "XSS in web server",
                },
            ]
        }
        vuln_file = _write_vuln_file(data, tmp_path)
        report = engine.analyze_from_file(vuln_file)
        assert report.total_vulnerabilities == 2
        assert report.critical_count == 1
        assert report.infrastructure_risk_score > 0
        assert len(report.impacts) == 2
        assert len(report.recommendations) > 0

    def test_trivy_format(self, tmp_path: Path):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        data = {
            "Results": [
                {
                    "Target": "app",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2024-3333",
                            "PkgName": "django",
                            "Severity": "HIGH",
                            "Description": "RCE in Django",
                        }
                    ],
                }
            ]
        }
        vuln_file = _write_vuln_file(data, tmp_path)
        report = engine.analyze_from_file(vuln_file)
        assert report.total_vulnerabilities == 1
        assert report.impacts[0].cve_id == "CVE-2024-3333"

    def test_plain_array_format(self, tmp_path: Path):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        data = [
            {
                "cve_id": "CVE-2024-4444",
                "severity": "low",
                "package": "lodash",
                "description": "Prototype pollution",
            }
        ]
        vuln_file = _write_vuln_file(data, tmp_path)
        report = engine.analyze_from_file(vuln_file)
        assert report.total_vulnerabilities == 1
        assert report.critical_count == 0

    def test_dependabot_format(self, tmp_path: Path):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        data = {
            "results": [
                {
                    "advisory": {
                        "cve_id": "CVE-2024-5555",
                        "severity": "high",
                    },
                    "name": "requests",
                    "description": "SSRF vulnerability",
                }
            ]
        }
        vuln_file = _write_vuln_file(data, tmp_path)
        report = engine.analyze_from_file(vuln_file)
        assert report.total_vulnerabilities == 1
        assert report.impacts[0].cve_id == "CVE-2024-5555"


# ---------------------------------------------------------------------------
# Report and recommendations tests
# ---------------------------------------------------------------------------


class TestReportAndRecommendations:
    def test_no_vulns_clean_report(self, tmp_path: Path):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        vuln_file = _write_vuln_file([], tmp_path)
        report = engine.analyze_from_file(vuln_file)
        assert report.total_vulnerabilities == 0
        assert report.critical_count == 0
        assert report.infrastructure_risk_score == 0.0
        assert any("No vulnerabilities" in r for r in report.recommendations)

    def test_critical_recommendations(self):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        report = engine.analyze_from_data([
            {"cve_id": "CVE-CRIT-1", "severity": "critical", "package": "pg"},
            {"cve_id": "CVE-CRIT-2", "severity": "critical", "package": "express"},
        ])
        assert report.critical_count == 2
        assert any("URGENT" in r for r in report.recommendations)

    def test_mixed_severity_scoring(self):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        low_report = engine.analyze_from_data([
            {"cve_id": "CVE-LOW-1", "severity": "low", "package": "x"},
        ])
        crit_report = engine.analyze_from_data([
            {"cve_id": "CVE-CRIT-1", "severity": "critical", "package": "x"},
        ])
        assert crit_report.infrastructure_risk_score > low_report.infrastructure_risk_score

    def test_auto_map_components_by_package_name(self):
        graph = _make_graph()
        engine = SupplyChainEngine(graph)
        report = engine.analyze_from_data([
            {
                "cve_id": "CVE-DB-1",
                "severity": "high",
                "package": "postgres-driver",
                "description": "SQL injection in database driver",
            }
        ])
        # Should auto-map to the database component
        assert len(report.impacts) == 1
        assert "db" in report.impacts[0].affected_components
