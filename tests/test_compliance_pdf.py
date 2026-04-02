# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Tests for compliance evidence HTML report generator (Feature C)."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.reporter.compliance_pdf import _pct_class, _run_framework, generate_compliance_html


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_graph() -> InfraGraph:
    """Minimal graph: one app server + one database, no security features."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="app-server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db",
        name="database",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def secure_graph() -> InfraGraph:
    """Well-configured graph: should have reasonable compliance rates."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        security=SecurityProfile(
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
        ),
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        port=8443,
        replicas=2,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=6),
    ))
    graph.add_component(Component(
        id="db",
        name="Primary DB",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=30.0),
        security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            auth_required=True,
            backup_enabled=True,
        ),
        region=RegionConfig(dr_target_region="us-west-2"),
    ))
    graph.add_dependency(
        Dependency(
            source_id="lb",
            target_id="app",
            dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        )
    )
    graph.add_dependency(
        Dependency(
            source_id="app",
            target_id="db",
            dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        )
    )
    return graph


@pytest.fixture
def empty_graph() -> InfraGraph:
    return InfraGraph()


# ---------------------------------------------------------------------------
# Unit tests: _pct_class
# ---------------------------------------------------------------------------


def test_pct_class_green() -> None:
    assert _pct_class(80.0) == "pct-green"
    assert _pct_class(100.0) == "pct-green"


def test_pct_class_yellow() -> None:
    assert _pct_class(50.0) == "pct-yellow"
    assert _pct_class(79.9) == "pct-yellow"


def test_pct_class_red() -> None:
    assert _pct_class(0.0) == "pct-red"
    assert _pct_class(49.9) == "pct-red"


# ---------------------------------------------------------------------------
# Unit tests: _run_framework
# ---------------------------------------------------------------------------


def test_run_framework_soc2_returns_report(minimal_graph: InfraGraph) -> None:
    report = _run_framework(minimal_graph, "soc2")
    assert report is not None
    assert report.framework == "soc2"
    assert report.total_checks > 0


def test_run_framework_iso27001_returns_report(minimal_graph: InfraGraph) -> None:
    report = _run_framework(minimal_graph, "iso27001")
    assert report is not None
    assert report.total_checks > 0


def test_run_framework_pci_dss_returns_report(minimal_graph: InfraGraph) -> None:
    report = _run_framework(minimal_graph, "pci_dss")
    assert report is not None
    assert report.total_checks > 0


def test_run_framework_nist_csf_returns_report(minimal_graph: InfraGraph) -> None:
    report = _run_framework(minimal_graph, "nist_csf")
    assert report is not None
    assert report.total_checks > 0


def test_run_framework_unknown_returns_none(minimal_graph: InfraGraph) -> None:
    result = _run_framework(minimal_graph, "unknown_fw_xyz")
    assert result is None


# ---------------------------------------------------------------------------
# Integration tests: generate_compliance_html
# ---------------------------------------------------------------------------


def test_generate_html_creates_file(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_generate_html_contains_doctype(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content


def test_generate_html_contains_org_name(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out, org_name="AcmeCorp")
    content = out.read_text(encoding="utf-8")
    assert "AcmeCorp" in content


def test_generate_html_contains_framework_name(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["iso27001"], out)
    content = out.read_text(encoding="utf-8")
    assert "iso27001" in content.lower()


def test_generate_html_multiple_frameworks(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2", "iso27001", "pci_dss"], out)
    content = out.read_text(encoding="utf-8")
    assert "soc2" in content.lower()
    assert "iso27001" in content.lower()
    assert "pci_dss" in content.lower()


def test_generate_html_contains_component_names(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    assert "app-server" in content
    assert "database" in content


def test_generate_html_contains_media_print(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    """HTML must contain @media print styles for PDF export."""
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    assert "@media print" in content


def test_generate_html_contains_executive_summary(minimal_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    generate_compliance_html(minimal_graph, ["soc2"], out)
    content = out.read_text(encoding="utf-8")
    assert "Executive Summary" in content


def test_generate_html_secure_graph_higher_compliance(
    minimal_graph: InfraGraph,
    secure_graph: InfraGraph,
) -> None:
    """Secure graph should produce a higher compliance percentage than minimal graph."""
    from faultray.reporter.compliance_pdf import _run_framework as _rf

    report_min = _rf(minimal_graph, "soc2")
    report_sec = _rf(secure_graph, "soc2")
    assert report_sec.compliance_percent >= report_min.compliance_percent


def test_generate_html_empty_graph_does_not_crash(empty_graph: InfraGraph, tmp_path: Path) -> None:
    out = tmp_path / "empty.html"
    generate_compliance_html(empty_graph, ["soc2"], out)
    assert out.exists()
