"""Tests for FaultRay APM Collector API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from faultray.apm.collector import apm_router, set_metrics_db, get_metrics_db
from faultray.apm.metrics_db import MetricsDB


@pytest.fixture()
def _apm_db(tmp_path: Path):
    """Set up a temporary MetricsDB for collector tests."""
    db = MetricsDB(db_path=tmp_path / "test_collector.db")
    db.open()
    set_metrics_db(db)
    yield db
    db.close()
    set_metrics_db(None)  # type: ignore[arg-type]


@pytest.fixture()
def client(_apm_db: MetricsDB):
    """Create a test client using the main app with APM router."""
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(apm_router)
    return TestClient(test_app)


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------


class TestAgentRegistration:
    def test_register_agent(self, client: TestClient) -> None:
        resp = client.post("/api/apm/agents/register", json={
            "agent_id": "test-agent",
            "hostname": "web-01",
            "ip_address": "10.0.0.1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "registered"
        assert data["agent_id"] == "test-agent"

    def test_list_agents(self, client: TestClient) -> None:
        client.post("/api/apm/agents/register", json={
            "agent_id": "a1", "hostname": "h1",
        })
        resp = client.get("/api/apm/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) == 1
        assert agents[0]["agent_id"] == "a1"

    def test_get_agent(self, client: TestClient) -> None:
        client.post("/api/apm/agents/register", json={
            "agent_id": "a1", "hostname": "h1",
        })
        resp = client.get("/api/apm/agents/a1")
        assert resp.status_code == 200
        assert resp.json()["hostname"] == "h1"

    def test_get_agent_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/apm/agents/missing")
        assert resp.status_code == 404

    def test_heartbeat(self, client: TestClient) -> None:
        client.post("/api/apm/agents/register", json={
            "agent_id": "a1", "hostname": "h1",
        })
        resp = client.post("/api/apm/agents/a1/heartbeat", json={
            "agent_id": "a1", "status": "running",
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Metrics ingestion
# ---------------------------------------------------------------------------


class TestMetricsIngestion:
    def test_ingest_host_metrics(self, client: TestClient) -> None:
        client.post("/api/apm/agents/register", json={
            "agent_id": "a1", "hostname": "h1",
        })
        resp = client.post("/api/apm/metrics", json={
            "agent_id": "a1",
            "host_metrics": {
                "cpu_percent": 42.5,
                "memory_percent": 60.0,
                "disk_percent": 30.0,
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["metrics_stored"] > 0

    def test_ingest_custom_metrics(self, client: TestClient) -> None:
        resp = client.post("/api/apm/metrics", json={
            "agent_id": "a1",
            "custom_metrics": [
                {"name": "requests_total", "value": 1234.0, "metric_type": "counter"},
            ],
        })
        assert resp.status_code == 200
        assert resp.json()["metrics_stored"] == 1

    def test_ingest_traces(self, client: TestClient) -> None:
        resp = client.post("/api/apm/metrics", json={
            "agent_id": "a1",
            "traces": [
                {"trace_id": "t1", "span_id": "s1", "operation": "GET /api", "duration_ms": 50.0},
            ],
        })
        assert resp.status_code == 200
        assert resp.json()["traces_stored"] == 1

    def test_ingest_empty_batch(self, client: TestClient) -> None:
        resp = client.post("/api/apm/metrics", json={"agent_id": "a1"})
        assert resp.status_code == 200
        assert resp.json()["metrics_stored"] == 0


# ---------------------------------------------------------------------------
# Query endpoints
# ---------------------------------------------------------------------------


class TestMetricsQuery:
    def test_query_agent_metrics(self, client: TestClient) -> None:
        # Ingest data first
        client.post("/api/apm/agents/register", json={"agent_id": "a1", "hostname": "h1"})
        client.post("/api/apm/metrics", json={
            "agent_id": "a1",
            "host_metrics": {"cpu_percent": 50.0},
        })
        resp = client.get("/api/apm/agents/a1/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0

    def test_query_with_metric_name(self, client: TestClient) -> None:
        client.post("/api/apm/metrics", json={
            "agent_id": "a1",
            "host_metrics": {"cpu_percent": 50.0, "memory_percent": 60.0},
        })
        resp = client.get("/api/apm/agents/a1/metrics", params={"metric_name": "cpu_percent"})
        assert resp.status_code == 200
        data = resp.json()
        for d in data:
            assert d["metric_name"] == "cpu_percent"

    def test_advanced_query(self, client: TestClient) -> None:
        client.post("/api/apm/metrics", json={
            "agent_id": "a1",
            "host_metrics": {"cpu_percent": 50.0},
        })
        resp = client.post("/api/apm/metrics/query", json={
            "agent_id": "a1",
            "metric_names": ["cpu_percent"],
            "aggregation": "max",
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class TestAlertsEndpoint:
    def test_list_alerts_empty(self, client: TestClient) -> None:
        resp = client.get("/api/apm/alerts")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Stats & maintenance
# ---------------------------------------------------------------------------


class TestStatsAndMaintenance:
    def test_stats(self, client: TestClient) -> None:
        resp = client.get("/api/apm/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "metric_points" in data
        assert "agents" in data

    def test_purge(self, client: TestClient) -> None:
        resp = client.post("/api/apm/purge")
        assert resp.status_code == 200
        assert "deleted" in resp.json()
