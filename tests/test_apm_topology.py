"""Tests for FaultRay APM topology auto-updater."""

from __future__ import annotations

import pytest

from faultray.apm.models import ConnectionInfo, MetricsBatch, ProcessInfo
from faultray.apm.topology_updater import (
    _extract_listeners,
    _extract_outbound,
    _infer_service_type,
    set_topology_graph,
    update_topology_from_batch,
)
from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


@pytest.fixture()
def graph() -> InfraGraph:
    g = InfraGraph()
    set_topology_graph(g)
    yield g
    set_topology_graph(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Port → service type inference
# ---------------------------------------------------------------------------


class TestServiceInference:
    def test_well_known_ports(self) -> None:
        assert _infer_service_type(80) == ComponentType.WEB_SERVER
        assert _infer_service_type(443) == ComponentType.WEB_SERVER
        assert _infer_service_type(5432) == ComponentType.DATABASE
        assert _infer_service_type(6379) == ComponentType.CACHE
        assert _infer_service_type(9092) == ComponentType.QUEUE

    def test_unknown_port(self) -> None:
        assert _infer_service_type(12345) == ComponentType.CUSTOM

    def test_privileged_port(self) -> None:
        assert _infer_service_type(22) == ComponentType.APP_SERVER


# ---------------------------------------------------------------------------
# Listener extraction
# ---------------------------------------------------------------------------


class TestListenerExtraction:
    def test_extract_listeners(self) -> None:
        procs = [
            ProcessInfo(
                pid=1, name="nginx",
                connections=[
                    ConnectionInfo(local_addr="0.0.0.0", local_port=80, status="LISTEN"),
                    ConnectionInfo(local_addr="0.0.0.0", local_port=443, status="LISTEN"),
                ],
            ),
            ProcessInfo(
                pid=2, name="postgres",
                connections=[
                    ConnectionInfo(local_addr="0.0.0.0", local_port=5432, status="LISTEN"),
                ],
            ),
        ]
        listeners = _extract_listeners(procs)
        assert 80 in listeners
        assert 443 in listeners
        assert 5432 in listeners
        assert listeners[80] == "nginx"

    def test_no_listeners(self) -> None:
        procs = [
            ProcessInfo(pid=1, name="curl", connections=[
                ConnectionInfo(local_addr="10.0.0.1", local_port=54321, status="ESTABLISHED"),
            ]),
        ]
        listeners = _extract_listeners(procs)
        assert len(listeners) == 0


# ---------------------------------------------------------------------------
# Outbound connection extraction
# ---------------------------------------------------------------------------


class TestOutboundExtraction:
    def test_extract_outbound(self) -> None:
        conns = [
            ConnectionInfo(
                local_addr="10.0.0.1", local_port=54321,
                remote_addr="10.0.0.2", remote_port=5432,
                status="ESTABLISHED",
            ),
        ]
        outbound = _extract_outbound(conns, {80: "nginx"})
        assert len(outbound) == 1
        assert outbound[0] == ("10.0.0.2", 5432, 54321)

    def test_skip_loopback_to_own_listener(self) -> None:
        conns = [
            ConnectionInfo(
                local_addr="127.0.0.1", local_port=54321,
                remote_addr="127.0.0.1", remote_port=80,
                status="ESTABLISHED",
            ),
        ]
        outbound = _extract_outbound(conns, {80: "nginx"})
        assert len(outbound) == 0

    def test_skip_non_established(self) -> None:
        conns = [
            ConnectionInfo(
                local_addr="10.0.0.1", local_port=54321,
                remote_addr="10.0.0.2", remote_port=5432,
                status="TIME_WAIT",
            ),
        ]
        outbound = _extract_outbound(conns, {})
        assert len(outbound) == 0

    def test_deduplication(self) -> None:
        conns = [
            ConnectionInfo(
                local_addr="10.0.0.1", local_port=54321,
                remote_addr="10.0.0.2", remote_port=5432,
                status="ESTABLISHED",
            ),
            ConnectionInfo(
                local_addr="10.0.0.1", local_port=54322,
                remote_addr="10.0.0.2", remote_port=5432,
                status="ESTABLISHED",
            ),
        ]
        outbound = _extract_outbound(conns, {})
        assert len(outbound) == 1


# ---------------------------------------------------------------------------
# Full topology update
# ---------------------------------------------------------------------------


class TestTopologyUpdate:
    def test_adds_host_component(self, graph: InfraGraph) -> None:
        batch = MetricsBatch(agent_id="agent1")
        changes = update_topology_from_batch(batch)
        assert any("added component" in c for c in changes)
        assert graph.get_component("host-agent1") is not None

    def test_discovers_services(self, graph: InfraGraph) -> None:
        batch = MetricsBatch(
            agent_id="agent1",
            processes=[
                ProcessInfo(pid=1, name="nginx", connections=[
                    ConnectionInfo(local_addr="0.0.0.0", local_port=80, status="LISTEN"),
                ]),
            ],
        )
        changes = update_topology_from_batch(batch)
        assert graph.get_component("svc-agent1-80") is not None

    def test_discovers_remote_dependencies(self, graph: InfraGraph) -> None:
        batch = MetricsBatch(
            agent_id="agent1",
            connections=[
                ConnectionInfo(
                    local_addr="10.0.0.1", local_port=54321,
                    remote_addr="10.0.0.2", remote_port=5432,
                    status="ESTABLISHED",
                ),
            ],
        )
        update_topology_from_batch(batch)
        assert graph.get_component("remote-10.0.0.2:5432") is not None

    def test_no_graph_returns_empty(self) -> None:
        set_topology_graph(None)  # type: ignore[arg-type]
        batch = MetricsBatch(agent_id="a1")
        changes = update_topology_from_batch(batch)
        assert changes == []

    def test_idempotent(self, graph: InfraGraph) -> None:
        batch = MetricsBatch(
            agent_id="agent1",
            processes=[
                ProcessInfo(pid=1, name="nginx", connections=[
                    ConnectionInfo(local_addr="0.0.0.0", local_port=80, status="LISTEN"),
                ]),
            ],
        )
        changes1 = update_topology_from_batch(batch)
        changes2 = update_topology_from_batch(batch)
        # Second call should produce no new changes
        assert len(changes2) == 0
        assert len(changes1) > 0
