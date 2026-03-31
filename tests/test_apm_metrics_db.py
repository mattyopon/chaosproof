"""Tests for FaultRay APM MetricsDB — time-series storage."""

from __future__ import annotations

import datetime as _dt
import tempfile
from pathlib import Path

import pytest

from faultray.apm.metrics_db import MetricsDB


@pytest.fixture()
def db(tmp_path: Path) -> MetricsDB:
    """Create a fresh MetricsDB for each test."""
    mdb = MetricsDB(db_path=tmp_path / "test_apm.db", retention_hours=1)
    mdb.open()
    yield mdb
    mdb.close()


# ---------------------------------------------------------------------------
# Schema & lifecycle
# ---------------------------------------------------------------------------


class TestMetricsDBLifecycle:
    def test_open_creates_tables(self, db: MetricsDB) -> None:
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {t[0] for t in tables}
        assert "metric_points" in names
        assert "agent_registry" in names
        assert "alerts" in names
        assert "traces" in names

    def test_close_and_reopen(self, tmp_path: Path) -> None:
        mdb = MetricsDB(db_path=tmp_path / "reopen.db")
        mdb.open()
        mdb.insert_metrics("a1", [{"name": "cpu", "value": 50.0}])
        mdb.close()

        mdb2 = MetricsDB(db_path=tmp_path / "reopen.db")
        mdb2.open()
        result = mdb2.get_latest_metrics("a1")
        assert len(result) == 1
        assert result[0]["name"] == "cpu"
        mdb2.close()


# ---------------------------------------------------------------------------
# Metric insertion & query
# ---------------------------------------------------------------------------


class TestMetricInsertQuery:
    def test_insert_and_query(self, db: MetricsDB) -> None:
        ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
        count = db.insert_metrics("agent1", [
            {"name": "cpu_percent", "value": 42.5, "timestamp": ts},
            {"name": "memory_percent", "value": 60.0, "timestamp": ts},
        ])
        assert count == 2

        results = db.query_metrics(agent_id="agent1")
        assert len(results) >= 2
        names = {r["metric_name"] for r in results}
        assert "cpu_percent" in names
        assert "memory_percent" in names

    def test_get_latest_metrics(self, db: MetricsDB) -> None:
        ts1 = "2026-01-01T00:00:00+00:00"
        ts2 = "2026-01-01T00:01:00+00:00"
        db.insert_metrics("a1", [{"name": "cpu", "value": 10.0, "timestamp": ts1}])
        db.insert_metrics("a1", [{"name": "cpu", "value": 20.0, "timestamp": ts2}])

        latest = db.get_latest_metrics("a1")
        assert len(latest) == 1
        assert latest[0]["value"] == 20.0

    def test_query_by_metric_name(self, db: MetricsDB) -> None:
        ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
        db.insert_metrics("a1", [
            {"name": "cpu", "value": 10.0, "timestamp": ts},
            {"name": "mem", "value": 20.0, "timestamp": ts},
        ])
        results = db.query_metrics(agent_id="a1", metric_name="cpu")
        assert all(r["metric_name"] == "cpu" for r in results)

    def test_query_by_time_range(self, db: MetricsDB) -> None:
        db.insert_metrics("a1", [
            {"name": "cpu", "value": 10.0, "timestamp": "2026-01-01T00:00:00+00:00"},
            {"name": "cpu", "value": 20.0, "timestamp": "2026-01-02T00:00:00+00:00"},
        ])
        results = db.query_metrics(
            agent_id="a1",
            start_time="2026-01-01T12:00:00+00:00",
        )
        assert len(results) == 1

    def test_aggregation_avg(self, db: MetricsDB) -> None:
        ts = "2026-01-01T00:00:00+00:00"
        db.insert_metrics("a1", [
            {"name": "cpu", "value": 10.0, "timestamp": ts},
            {"name": "cpu", "value": 30.0, "timestamp": ts},
        ])
        results = db.query_metrics(agent_id="a1", aggregation="avg")
        assert len(results) == 1
        assert abs(results[0]["value"] - 20.0) < 0.01

    def test_empty_query(self, db: MetricsDB) -> None:
        results = db.query_metrics(agent_id="nonexistent")
        assert results == []


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------


class TestAgentRegistry:
    def test_register_and_list(self, db: MetricsDB) -> None:
        db.register_agent({
            "agent_id": "a1",
            "hostname": "web-01",
            "ip_address": "10.0.0.1",
            "os_info": "Linux 6.0",
            "agent_version": "1.0.0",
        })
        agents = db.list_agents()
        assert len(agents) == 1
        assert agents[0]["agent_id"] == "a1"
        assert agents[0]["hostname"] == "web-01"
        assert agents[0]["status"] == "running"

    def test_get_agent(self, db: MetricsDB) -> None:
        db.register_agent({"agent_id": "a1", "hostname": "h1"})
        agent = db.get_agent("a1")
        assert agent is not None
        assert agent["hostname"] == "h1"

    def test_get_agent_not_found(self, db: MetricsDB) -> None:
        assert db.get_agent("missing") is None

    def test_heartbeat_updates_status(self, db: MetricsDB) -> None:
        db.register_agent({"agent_id": "a1", "hostname": "h1"})
        db.update_agent_heartbeat("a1", "stopped")
        agent = db.get_agent("a1")
        assert agent is not None
        assert agent["status"] == "stopped"

    def test_register_upsert(self, db: MetricsDB) -> None:
        db.register_agent({"agent_id": "a1", "hostname": "old"})
        db.register_agent({"agent_id": "a1", "hostname": "new"})
        agents = db.list_agents()
        assert len(agents) == 1
        assert agents[0]["hostname"] == "new"


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class TestAlerts:
    def test_insert_and_list(self, db: MetricsDB) -> None:
        db.insert_alert({
            "alert_id": "alert1",
            "rule_name": "high_cpu",
            "agent_id": "a1",
            "metric_name": "cpu_percent",
            "metric_value": 95.0,
            "threshold": 90.0,
            "severity": "critical",
            "message": "CPU too high",
        })
        alerts = db.list_alerts()
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "critical"

    def test_list_by_agent(self, db: MetricsDB) -> None:
        db.insert_alert({"alert_id": "a1", "rule_name": "r1", "agent_id": "ag1"})
        db.insert_alert({"alert_id": "a2", "rule_name": "r2", "agent_id": "ag2"})
        alerts = db.list_alerts(agent_id="ag1")
        assert len(alerts) == 1

    def test_list_by_severity(self, db: MetricsDB) -> None:
        db.insert_alert({"alert_id": "a1", "rule_name": "r1", "severity": "critical"})
        db.insert_alert({"alert_id": "a2", "rule_name": "r2", "severity": "warning"})
        alerts = db.list_alerts(severity="critical")
        assert len(alerts) == 1


# ---------------------------------------------------------------------------
# Traces
# ---------------------------------------------------------------------------


class TestTraces:
    def test_insert_traces(self, db: MetricsDB) -> None:
        count = db.insert_traces([
            {"trace_id": "t1", "span_id": "s1", "operation": "GET /api", "duration_ms": 150.0},
            {"trace_id": "t1", "span_id": "s2", "operation": "DB query", "duration_ms": 50.0},
        ])
        assert count == 2


# ---------------------------------------------------------------------------
# Retention / purge
# ---------------------------------------------------------------------------


class TestRetention:
    def test_purge_removes_old_data(self, db: MetricsDB) -> None:
        old_ts = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=2)).isoformat()
        new_ts = _dt.datetime.now(_dt.timezone.utc).isoformat()

        db.insert_metrics("a1", [{"name": "cpu", "value": 10.0, "timestamp": old_ts}])
        db.insert_metrics("a1", [{"name": "cpu", "value": 20.0, "timestamp": new_ts}])

        deleted = db.purge_old_data()
        assert deleted == 1

        remaining = db.get_latest_metrics("a1")
        assert len(remaining) == 1
        assert remaining[0]["value"] == 20.0


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_get_stats(self, db: MetricsDB) -> None:
        db.insert_metrics("a1", [{"name": "cpu", "value": 10.0}])
        db.register_agent({"agent_id": "a1"})
        stats = db.get_stats()
        assert stats["metric_points"] == 1
        assert stats["agents"] == 1
        assert stats["alerts"] == 0
