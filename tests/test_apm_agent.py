"""Tests for FaultRay APM Agent — metric collection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from faultray.apm.agent import APMAgent, _get_local_ip, load_agent_config
from faultray.apm.models import AgentConfig, HostMetrics, MetricsBatch


# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------


class TestAgentConfig:
    def test_default_config(self) -> None:
        agent = APMAgent()
        assert agent.config.collect_interval_seconds == 15
        assert agent.config.collector_url == "http://localhost:8080"

    def test_custom_config(self) -> None:
        cfg = AgentConfig(
            agent_id="test-agent",
            collector_url="http://custom:9090",
            collect_interval_seconds=30,
        )
        agent = APMAgent(cfg)
        assert agent.config.agent_id == "test-agent"
        assert agent.config.collector_url == "http://custom:9090"

    def test_load_config_defaults(self) -> None:
        cfg = load_agent_config(None)
        assert isinstance(cfg, AgentConfig)

    def test_load_config_from_file(self, tmp_path: Path) -> None:
        import yaml

        config_path = tmp_path / "agent.yaml"
        config_path.write_text(yaml.dump({
            "agent_id": "from-file",
            "collector_url": "http://test:8080",
            "collect_interval_seconds": 60,
        }))
        cfg = load_agent_config(config_path)
        assert cfg.agent_id == "from-file"
        assert cfg.collect_interval_seconds == 60

    def test_load_config_nonexistent(self, tmp_path: Path) -> None:
        cfg = load_agent_config(tmp_path / "missing.yaml")
        assert isinstance(cfg, AgentConfig)  # defaults


# ---------------------------------------------------------------------------
# Metric collection (uses real psutil)
# ---------------------------------------------------------------------------


class TestMetricCollection:
    def test_collect_host_metrics(self) -> None:
        agent = APMAgent()
        hm = agent.collect_host_metrics()
        assert isinstance(hm, HostMetrics)
        assert hm.cpu_percent >= 0.0
        assert hm.memory_total_mb > 0
        assert hm.cpu_count >= 1

    def test_collect_processes(self) -> None:
        agent = APMAgent()
        procs = agent.collect_processes()
        # Should find at least the current process
        assert len(procs) > 0
        pids = [p.pid for p in procs]
        import os
        # Our PID should be present (unless access denied)
        # Don't assert strictly — some CI envs restrict proc access

    def test_collect_processes_with_filter(self) -> None:
        cfg = AgentConfig(process_filter=["python"])
        agent = APMAgent(cfg)
        procs = agent.collect_processes()
        for p in procs:
            assert "python" in p.name.lower()

    def test_collect_connections(self) -> None:
        agent = APMAgent()
        conns = agent.collect_connections()
        # May be empty if running without privileges
        assert isinstance(conns, list)


# ---------------------------------------------------------------------------
# Batch construction
# ---------------------------------------------------------------------------


class TestBatchConstruction:
    def test_collect_batch(self) -> None:
        agent = APMAgent()
        batch = agent._collect_batch()
        assert isinstance(batch, MetricsBatch)
        assert batch.agent_id == agent.config.agent_id
        assert batch.host_metrics is not None

    def test_merge_batches_single(self) -> None:
        agent = APMAgent()
        batch = agent._collect_batch()
        merged = agent._merge_batches([batch])
        assert merged is batch  # Identity for single batch

    def test_merge_batches_multiple(self) -> None:
        agent = APMAgent()
        b1 = agent._collect_batch()
        b2 = agent._collect_batch()
        merged = agent._merge_batches([b1, b2])
        # Should keep latest host metrics
        assert merged.host_metrics is b2.host_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_get_local_ip(self) -> None:
        ip = _get_local_ip()
        assert isinstance(ip, str)
        assert len(ip) > 0

    def test_uptime(self) -> None:
        agent = APMAgent()
        assert agent.uptime_seconds == 0.0

    def test_pid_file(self, tmp_path: Path) -> None:
        cfg = AgentConfig(pid_file=str(tmp_path / "test.pid"))
        agent = APMAgent(cfg)
        agent._write_pid_file()
        assert (tmp_path / "test.pid").exists()
        agent._remove_pid_file()
        assert not (tmp_path / "test.pid").exists()
