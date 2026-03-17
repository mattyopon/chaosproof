"""Tests for agent_config / llm_config / tool_config / orchestrator_config
flattening in the YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.model.loader import load_yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path: Path, content: str) -> Path:
    """Write *content* to a temporary YAML file and return its path."""
    p = tmp_path / "test.yaml"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. agent_config is flattened into parameters
# ---------------------------------------------------------------------------

def test_agent_config_flattened_into_parameters(tmp_path: Path) -> None:
    yaml_content = """\
components:
  - id: my-agent
    name: My Agent
    type: ai_agent
    agent_config:
      framework: langchain
      model_id: claude-sonnet-4-20250514
      hallucination_risk: 0.03
      temperature: 0.3
dependencies: []
"""
    graph = load_yaml(_write_yaml(tmp_path, yaml_content))
    comp = graph.components["my-agent"]
    assert comp.parameters["framework"] == "langchain"
    assert comp.parameters["model_id"] == "claude-sonnet-4-20250514"
    assert comp.parameters["hallucination_risk"] == 0.03
    assert comp.parameters["temperature"] == 0.3


# ---------------------------------------------------------------------------
# 2. llm_config is flattened into parameters
# ---------------------------------------------------------------------------

def test_llm_config_flattened_into_parameters(tmp_path: Path) -> None:
    yaml_content = """\
components:
  - id: claude-api
    name: Claude API
    type: llm_endpoint
    llm_config:
      provider: anthropic
      model_id: claude-sonnet-4-20250514
      rate_limit_rpm: 1000
      availability_sla: 99.9
dependencies: []
"""
    graph = load_yaml(_write_yaml(tmp_path, yaml_content))
    comp = graph.components["claude-api"]
    assert comp.parameters["provider"] == "anthropic"
    assert comp.parameters["model_id"] == "claude-sonnet-4-20250514"
    assert comp.parameters["rate_limit_rpm"] == 1000
    assert comp.parameters["availability_sla"] == 99.9


# ---------------------------------------------------------------------------
# 3. tool_config is flattened into parameters
# ---------------------------------------------------------------------------

def test_tool_config_flattened_into_parameters(tmp_path: Path) -> None:
    yaml_content = """\
components:
  - id: search-tool
    name: Search Tool
    type: tool_service
    tool_config:
      tool_type: web_search
      failure_rate: 0.02
dependencies: []
"""
    graph = load_yaml(_write_yaml(tmp_path, yaml_content))
    comp = graph.components["search-tool"]
    assert comp.parameters["tool_type"] == "web_search"
    assert comp.parameters["failure_rate"] == 0.02


# ---------------------------------------------------------------------------
# 4. orchestrator_config is flattened into parameters
# ---------------------------------------------------------------------------

def test_orchestrator_config_flattened_into_parameters(tmp_path: Path) -> None:
    yaml_content = """\
components:
  - id: router
    name: Router
    type: agent_orchestrator
    orchestrator_config:
      pattern: hierarchical
      max_agents: 5
      max_iterations: 30
dependencies: []
"""
    graph = load_yaml(_write_yaml(tmp_path, yaml_content))
    comp = graph.components["router"]
    assert comp.parameters["pattern"] == "hierarchical"
    assert comp.parameters["max_agents"] == 5
    assert comp.parameters["max_iterations"] == 30


# ---------------------------------------------------------------------------
# 5. Boolean conversion (true -> 1, false -> 0)
# ---------------------------------------------------------------------------

def test_boolean_conversion_true_to_1(tmp_path: Path) -> None:
    yaml_content = """\
components:
  - id: agent1
    name: Agent 1
    type: ai_agent
    agent_config:
      requires_grounding: true
      has_memory: false
dependencies: []
"""
    graph = load_yaml(_write_yaml(tmp_path, yaml_content))
    comp = graph.components["agent1"]
    assert comp.parameters["requires_grounding"] == 1
    assert comp.parameters["has_memory"] == 0


def test_boolean_conversion_in_tool_config(tmp_path: Path) -> None:
    yaml_content = """\
components:
  - id: tool1
    name: Tool 1
    type: tool_service
    tool_config:
      idempotent: true
      side_effects: false
dependencies: []
"""
    graph = load_yaml(_write_yaml(tmp_path, yaml_content))
    comp = graph.components["tool1"]
    assert comp.parameters["idempotent"] == 1
    assert comp.parameters["side_effects"] == 0


def test_boolean_conversion_in_orchestrator_config(tmp_path: Path) -> None:
    yaml_content = """\
components:
  - id: orch1
    name: Orchestrator 1
    type: agent_orchestrator
    orchestrator_config:
      circuit_breaker_on_hallucination: true
dependencies: []
"""
    graph = load_yaml(_write_yaml(tmp_path, yaml_content))
    comp = graph.components["orch1"]
    assert comp.parameters["circuit_breaker_on_hallucination"] == 1


# ---------------------------------------------------------------------------
# 6. Regular parameters still work (no agent_config key)
# ---------------------------------------------------------------------------

def test_regular_parameters_still_work(tmp_path: Path) -> None:
    yaml_content = """\
components:
  - id: legacy-agent
    name: Legacy Agent
    type: ai_agent
    parameters:
      framework: langchain
      model_id: claude-sonnet-4-20250514
      requires_grounding: 1
dependencies: []
"""
    graph = load_yaml(_write_yaml(tmp_path, yaml_content))
    comp = graph.components["legacy-agent"]
    assert comp.parameters["framework"] == "langchain"
    assert comp.parameters["model_id"] == "claude-sonnet-4-20250514"
    # No boolean conversion for raw parameters — value stays as-is
    assert comp.parameters["requires_grounding"] == 1


# ---------------------------------------------------------------------------
# 7. Loading the actual examples/ai-agent-workflow.yaml works without errors
# ---------------------------------------------------------------------------

def test_load_example_ai_agent_workflow() -> None:
    example_path = Path(__file__).resolve().parent.parent / "examples" / "ai-agent-workflow.yaml"
    if not example_path.exists():
        pytest.skip(f"Example file not found: {example_path}")

    graph = load_yaml(example_path)

    # Verify key components exist
    assert "claude-api" in graph.components
    assert "research-agent" in graph.components
    assert "writer-agent" in graph.components
    assert "router-agent" in graph.components
    assert "web-search" in graph.components
    assert "db-query-tool" in graph.components

    # Verify agent_config was flattened
    research = graph.components["research-agent"]
    assert research.parameters["framework"] == "langchain"
    assert research.parameters["requires_grounding"] == 1  # true -> 1

    # Verify llm_config was flattened
    claude = graph.components["claude-api"]
    assert claude.parameters["provider"] == "anthropic"

    # Verify tool_config was flattened
    search = graph.components["web-search"]
    assert search.parameters["tool_type"] == "web_search"
    assert search.parameters["idempotent"] == 1  # true -> 1
    assert search.parameters["side_effects"] == 0  # false -> 0

    # Verify orchestrator_config was flattened
    router = graph.components["router-agent"]
    assert router.parameters["pattern"] == "hierarchical"
    assert router.parameters["circuit_breaker_on_hallucination"] == 1  # true -> 1

    # Verify writer agent
    writer = graph.components["writer-agent"]
    assert writer.parameters["requires_grounding"] == 0  # false -> 0
