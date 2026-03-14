"""Tests for the plugin registry and plugin-engine integration."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from infrasim.plugins.registry import PluginRegistry
from infrasim.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure the registry is clean before and after each test."""
    PluginRegistry.clear()
    yield
    PluginRegistry.clear()


class _DummyScenarioPlugin:
    """A minimal scenario plugin for testing."""

    name = "dummy-scenario"
    description = "Generates a single dummy scenario."

    def generate_scenarios(self, graph, component_ids, components) -> list:
        if not component_ids:
            return []
        return [
            Scenario(
                id="plugin-dummy-1",
                name="Plugin Dummy",
                description="Injected by plugin",
                faults=[
                    Fault(
                        target_component_id=component_ids[0],
                        fault_type=FaultType.COMPONENT_DOWN,
                    )
                ],
            )
        ]


class _DummyAnalyzerPlugin:
    """A minimal analyzer plugin for testing."""

    name = "dummy-analyzer"

    def analyze(self, graph, report) -> dict:
        return {"plugin": self.name, "ok": True}


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestPluginRegistry:
    def test_register_scenario_plugin(self):
        plugin = _DummyScenarioPlugin()
        PluginRegistry.register_scenario(plugin)
        assert len(PluginRegistry.get_scenario_plugins()) == 1
        assert PluginRegistry.get_scenario_plugins()[0].name == "dummy-scenario"

    def test_register_analyzer_plugin(self):
        plugin = _DummyAnalyzerPlugin()
        PluginRegistry.register_analyzer(plugin)
        assert len(PluginRegistry.get_analyzer_plugins()) == 1
        assert PluginRegistry.get_analyzer_plugins()[0].name == "dummy-analyzer"

    def test_clear(self):
        PluginRegistry.register_scenario(_DummyScenarioPlugin())
        PluginRegistry.register_analyzer(_DummyAnalyzerPlugin())
        assert len(PluginRegistry.get_scenario_plugins()) == 1
        assert len(PluginRegistry.get_analyzer_plugins()) == 1

        PluginRegistry.clear()
        assert PluginRegistry.get_scenario_plugins() == []
        assert PluginRegistry.get_analyzer_plugins() == []

    def test_load_plugins_from_dir(self, tmp_path: Path):
        """Write a plugin .py file to a temp dir and load it."""
        plugin_file = tmp_path / "my_plugin.py"
        plugin_file.write_text(
            textwrap.dedent("""\
                from infrasim.simulator.scenarios import Fault, FaultType, Scenario

                class MyPlugin:
                    name = "my-plugin"
                    description = "test plugin"
                    def generate_scenarios(self, graph, component_ids, components):
                        return []

                def register(registry):
                    registry.register_scenario(MyPlugin())
            """)
        )

        PluginRegistry.load_plugins_from_dir(tmp_path)
        assert len(PluginRegistry.get_scenario_plugins()) == 1
        assert PluginRegistry.get_scenario_plugins()[0].name == "my-plugin"

    def test_load_plugins_skips_underscore_files(self, tmp_path: Path):
        """Files starting with _ should be skipped."""
        (tmp_path / "_internal.py").write_text("raise RuntimeError('should not load')")
        PluginRegistry.load_plugins_from_dir(tmp_path)
        assert PluginRegistry.get_scenario_plugins() == []

    def test_load_plugins_nonexistent_dir(self, tmp_path: Path):
        """Loading from a non-existent directory should be a no-op."""
        PluginRegistry.load_plugins_from_dir(tmp_path / "nonexistent")
        assert PluginRegistry.get_scenario_plugins() == []


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------

class TestPluginEngineIntegration:
    def test_plugin_scenarios_merged_into_simulation(self):
        """Plugin-generated scenarios should appear in simulation results."""
        from infrasim.model.demo import create_demo_graph
        from infrasim.simulator.engine import SimulationEngine

        graph = create_demo_graph()
        plugin = _DummyScenarioPlugin()
        PluginRegistry.register_scenario(plugin)

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=True)

        # The plugin adds one scenario with id "plugin-dummy-1"
        plugin_ids = [r.scenario.id for r in report.results if r.scenario.id == "plugin-dummy-1"]
        assert len(plugin_ids) == 1

    def test_simulation_without_plugins(self):
        """Simulation should work with no plugins registered."""
        from infrasim.model.demo import create_demo_graph
        from infrasim.simulator.engine import SimulationEngine

        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=True)

        # Should still have default scenarios
        assert len(report.results) > 0
