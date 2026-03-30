"""Tests for Sensitivity Ratchet simulation.

Covers:
- Ratchet narrows permissions correctly
- Ratchet is irreversible
- Damage comparison with/without ratchet
- Integration with multi-agent scenarios (agent A -> agent B)
- Built-in scenario helpers
"""

from __future__ import annotations

import pytest

from faultray.simulator.ratchet_models import (
    AgentAction,
    AgentSimProfile,
    LeakEvent,
    RatchetSimulationResult,
    RatchetState,
    SensitivityLevel,
)
from faultray.simulator.ratchet_simulator import (
    build_cross_agent_leak_scenario,
    build_data_exfiltration_scenario,
    build_gradual_escalation_scenario,
    run_ratchet_simulation,
    simulate_agent_with_ratchet,
    simulate_multi_agent_with_ratchet,
)


# ──────────────────────────────────────────────────────────────────────
# RatchetState unit tests
# ──────────────────────────────────────────────────────────────────────


class TestRatchetState:
    """Tests for the RatchetState model."""

    def test_initial_state_has_all_permissions(self) -> None:
        state = RatchetState()
        assert "send:external_api" in state.remaining_permissions
        assert "write:external" in state.remaining_permissions
        assert "execute:tool" in state.remaining_permissions
        assert state.high_water_mark == SensitivityLevel.PUBLIC

    def test_public_access_does_not_narrow(self) -> None:
        state = RatchetState()
        original = set(state.remaining_permissions)
        state.apply_ratchet(SensitivityLevel.PUBLIC)
        assert state.remaining_permissions == original
        assert state.high_water_mark == SensitivityLevel.PUBLIC

    def test_internal_access_does_not_narrow(self) -> None:
        state = RatchetState()
        original = set(state.remaining_permissions)
        state.apply_ratchet(SensitivityLevel.INTERNAL)
        assert state.remaining_permissions == original
        assert state.high_water_mark == SensitivityLevel.INTERNAL

    def test_confidential_removes_execute_and_send(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        assert "execute:tool" not in state.remaining_permissions
        assert "send:external_api" not in state.remaining_permissions
        # Read/write should remain
        assert "read:internal" in state.remaining_permissions
        assert "write:internal" in state.remaining_permissions

    def test_restricted_removes_all_writes(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.RESTRICTED)
        assert "write:external" not in state.remaining_permissions
        assert "write:internal" not in state.remaining_permissions
        assert "send:external_api" not in state.remaining_permissions
        assert "execute:tool" not in state.remaining_permissions
        # Read should remain
        assert "read:internal" in state.remaining_permissions
        assert "read:external" in state.remaining_permissions

    def test_top_secret_removes_external_read(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.TOP_SECRET)
        assert "read:external" not in state.remaining_permissions
        # Only internal read should remain
        assert "read:internal" in state.remaining_permissions
        assert len(state.remaining_permissions) == 1

    def test_ratchet_is_irreversible(self) -> None:
        """Once permissions are removed, accessing lower-sensitivity data
        does NOT restore them."""
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.RESTRICTED)
        perms_after_restricted = set(state.remaining_permissions)

        # Access public data — permissions should NOT expand
        state.apply_ratchet(SensitivityLevel.PUBLIC)
        assert state.remaining_permissions == perms_after_restricted
        assert state.high_water_mark == SensitivityLevel.RESTRICTED

    def test_ratchet_monotonic_high_water(self) -> None:
        """High-water mark only increases, never decreases."""
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        assert state.high_water_mark == SensitivityLevel.CONFIDENTIAL

        state.apply_ratchet(SensitivityLevel.PUBLIC)
        assert state.high_water_mark == SensitivityLevel.CONFIDENTIAL

        state.apply_ratchet(SensitivityLevel.TOP_SECRET)
        assert state.high_water_mark == SensitivityLevel.TOP_SECRET

    def test_access_history_recorded(self) -> None:
        state = RatchetState()
        state.apply_ratchet(SensitivityLevel.INTERNAL)
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        assert len(state.access_history) == 2
        assert "accessed:INTERNAL" in state.access_history[0]
        assert "accessed:CONFIDENTIAL" in state.access_history[1]


# ──────────────────────────────────────────────────────────────────────
# Single-agent simulation tests
# ──────────────────────────────────────────────────────────────────────


class TestSingleAgentSimulation:
    """Tests for simulate_agent_with_ratchet."""

    def test_no_leak_without_external_send(self) -> None:
        """Agent reads sensitive data but never sends externally -> no leaks."""
        profile = AgentSimProfile(
            agent_id="safe-agent",
            actions=[
                AgentAction(
                    action_type="access_data",
                    target="secret-db",
                    sensitivity=SensitivityLevel.TOP_SECRET,
                ),
            ],
        )
        events, state = simulate_agent_with_ratchet(profile, ratchet_enabled=True)
        assert len(events) == 0

    def test_leak_without_ratchet(self) -> None:
        """Without ratchet, agent can send after reading restricted data."""
        profile = AgentSimProfile(
            agent_id="leaky-agent",
            actions=[
                AgentAction(
                    action_type="access_data",
                    target="classified-db",
                    sensitivity=SensitivityLevel.RESTRICTED,
                ),
                AgentAction(
                    action_type="send_external",
                    target="evil-api",
                    required_permission="send:external_api",
                ),
            ],
        )
        events, state = simulate_agent_with_ratchet(profile, ratchet_enabled=False)
        assert len(events) == 1
        assert events[0].leaked is True
        assert events[0].data_sensitivity == SensitivityLevel.RESTRICTED

    def test_blocked_with_ratchet(self) -> None:
        """With ratchet, agent cannot send after reading restricted data."""
        profile = AgentSimProfile(
            agent_id="blocked-agent",
            actions=[
                AgentAction(
                    action_type="access_data",
                    target="classified-db",
                    sensitivity=SensitivityLevel.RESTRICTED,
                ),
                AgentAction(
                    action_type="send_external",
                    target="evil-api",
                    required_permission="send:external_api",
                ),
            ],
        )
        events, state = simulate_agent_with_ratchet(profile, ratchet_enabled=True)
        assert len(events) == 1
        assert events[0].leaked is False
        assert events[0].prevented_by_ratchet is True

    def test_public_data_send_is_not_counted_as_leak(self) -> None:
        """Sending externally when only public data accessed -> no leak event."""
        profile = AgentSimProfile(
            agent_id="public-agent",
            actions=[
                AgentAction(
                    action_type="access_data",
                    target="public-page",
                    sensitivity=SensitivityLevel.PUBLIC,
                ),
                AgentAction(
                    action_type="send_external",
                    target="analytics",
                    required_permission="send:external_api",
                ),
            ],
        )
        events, _ = simulate_agent_with_ratchet(profile, ratchet_enabled=True)
        assert len(events) == 0

    def test_confidential_blocks_send(self) -> None:
        """CONFIDENTIAL access should also block external sends."""
        profile = AgentSimProfile(
            agent_id="conf-agent",
            actions=[
                AgentAction(
                    action_type="access_data",
                    target="pii-db",
                    sensitivity=SensitivityLevel.CONFIDENTIAL,
                ),
                AgentAction(
                    action_type="send_external",
                    target="third-party",
                    required_permission="send:external_api",
                ),
            ],
        )
        events, _ = simulate_agent_with_ratchet(profile, ratchet_enabled=True)
        assert len(events) == 1
        assert events[0].leaked is False
        assert events[0].prevented_by_ratchet is True


# ──────────────────────────────────────────────────────────────────────
# Multi-agent simulation tests
# ──────────────────────────────────────────────────────────────────────


class TestMultiAgentSimulation:
    """Tests for simulate_multi_agent_with_ratchet."""

    def test_cross_agent_leak_without_ratchet(self) -> None:
        """Agent A accesses classified data, passes to B, B sends externally
        -> LEAK without ratchet."""
        agent_a = AgentSimProfile(
            agent_id="agent-a",
            actions=[
                AgentAction(
                    action_type="access_data",
                    target="secret",
                    sensitivity=SensitivityLevel.RESTRICTED,
                ),
                AgentAction(
                    action_type="pass_to_agent",
                    target="agent-b",
                    sensitivity=SensitivityLevel.RESTRICTED,
                ),
            ],
        )
        agent_b = AgentSimProfile(
            agent_id="agent-b",
            actions=[
                AgentAction(
                    action_type="send_external",
                    target="external",
                    required_permission="send:external_api",
                ),
            ],
        )
        events, states = simulate_multi_agent_with_ratchet(
            [agent_a, agent_b], ratchet_enabled=False,
        )
        leaked = [e for e in events if e.leaked]
        assert len(leaked) == 1
        assert leaked[0].agent_id == "agent-b"

    def test_cross_agent_blocked_with_ratchet(self) -> None:
        """Agent A accesses classified data, passes to B, B's send is blocked
        by ratchet."""
        agent_a = AgentSimProfile(
            agent_id="agent-a",
            actions=[
                AgentAction(
                    action_type="access_data",
                    target="secret",
                    sensitivity=SensitivityLevel.RESTRICTED,
                ),
                AgentAction(
                    action_type="pass_to_agent",
                    target="agent-b",
                    sensitivity=SensitivityLevel.RESTRICTED,
                ),
            ],
        )
        agent_b = AgentSimProfile(
            agent_id="agent-b",
            actions=[
                AgentAction(
                    action_type="send_external",
                    target="external",
                    required_permission="send:external_api",
                ),
            ],
        )
        events, states = simulate_multi_agent_with_ratchet(
            [agent_a, agent_b], ratchet_enabled=True,
        )
        assert len(events) == 1
        assert events[0].leaked is False
        assert events[0].prevented_by_ratchet is True
        # Agent B's state should reflect inherited sensitivity
        assert states["agent-b"].high_water_mark == SensitivityLevel.RESTRICTED

    def test_independent_agents_no_cross_contamination(self) -> None:
        """Two agents acting independently: one reads classified data,
        the other should NOT be affected."""
        agent_a = AgentSimProfile(
            agent_id="agent-a",
            actions=[
                AgentAction(
                    action_type="access_data",
                    target="secret",
                    sensitivity=SensitivityLevel.TOP_SECRET,
                ),
            ],
        )
        agent_b = AgentSimProfile(
            agent_id="agent-b",
            actions=[
                AgentAction(
                    action_type="access_data",
                    target="public-doc",
                    sensitivity=SensitivityLevel.PUBLIC,
                ),
                AgentAction(
                    action_type="send_external",
                    target="analytics",
                    required_permission="send:external_api",
                ),
            ],
        )
        events, states = simulate_multi_agent_with_ratchet(
            [agent_a, agent_b], ratchet_enabled=True,
        )
        # Agent B only accessed public data -> no leak events at all
        assert len(events) == 0
        assert states["agent-b"].high_water_mark == SensitivityLevel.PUBLIC
        assert "send:external_api" in states["agent-b"].remaining_permissions


# ──────────────────────────────────────────────────────────────────────
# Damage comparison tests
# ──────────────────────────────────────────────────────────────────────


class TestDamageComparison:
    """Tests for run_ratchet_simulation and effectiveness scoring."""

    def test_full_effectiveness_when_all_leaks_prevented(self) -> None:
        """Effectiveness = 1.0 when ratchet prevents all leaks."""
        profile = AgentSimProfile(
            agent_id="agent",
            actions=[
                AgentAction(
                    action_type="access_data",
                    target="secret",
                    sensitivity=SensitivityLevel.RESTRICTED,
                ),
                AgentAction(
                    action_type="send_external",
                    target="ext",
                    required_permission="send:external_api",
                ),
            ],
        )
        result = run_ratchet_simulation("test", [profile])
        assert result.effectiveness_score == 1.0
        assert result.without_ratchet_leaks == 1
        assert result.with_ratchet_leaks == 0
        assert result.prevented_leaks == 1
        assert result.prevented_damage > 0

    def test_zero_effectiveness_when_no_sensitive_data(self) -> None:
        """No sensitive data accessed -> effectiveness defaults to 1.0
        (nothing to prevent)."""
        profile = AgentSimProfile(
            agent_id="agent",
            actions=[
                AgentAction(
                    action_type="access_data",
                    target="public",
                    sensitivity=SensitivityLevel.PUBLIC,
                ),
                AgentAction(
                    action_type="send_external",
                    target="ext",
                    required_permission="send:external_api",
                ),
            ],
        )
        result = run_ratchet_simulation("test", [profile])
        assert result.effectiveness_score == 1.0
        assert result.without_ratchet_leaks == 0
        assert result.with_ratchet_leaks == 0

    def test_damage_weighted_by_sensitivity(self) -> None:
        """Higher-sensitivity leaks should produce higher damage scores."""
        profile_conf = AgentSimProfile(
            agent_id="agent-conf",
            actions=[
                AgentAction(
                    action_type="access_data", target="a",
                    sensitivity=SensitivityLevel.CONFIDENTIAL,
                ),
                AgentAction(
                    action_type="send_external", target="ext",
                    required_permission="send:external_api",
                ),
            ],
        )
        profile_ts = AgentSimProfile(
            agent_id="agent-ts",
            actions=[
                AgentAction(
                    action_type="access_data", target="b",
                    sensitivity=SensitivityLevel.TOP_SECRET,
                ),
                AgentAction(
                    action_type="send_external", target="ext",
                    required_permission="send:external_api",
                ),
            ],
        )
        result_conf = run_ratchet_simulation("conf", [profile_conf])
        result_ts = run_ratchet_simulation("ts", [profile_ts])

        # Without ratchet, TOP_SECRET leak damage > CONFIDENTIAL leak damage
        assert result_ts.without_ratchet_damage > result_conf.without_ratchet_damage

    def test_result_model_fields(self) -> None:
        """Verify all expected fields are populated."""
        profile = AgentSimProfile(
            agent_id="x",
            actions=[
                AgentAction(
                    action_type="access_data", target="a",
                    sensitivity=SensitivityLevel.RESTRICTED,
                ),
                AgentAction(
                    action_type="send_external", target="b",
                    required_permission="send:external_api",
                ),
            ],
        )
        result = run_ratchet_simulation("test-fields", [profile])
        assert result.scenario_name == "test-fields"
        assert result.agents == ["x"]
        assert result.total_actions == 2
        assert isinstance(result.leak_events, list)
        assert isinstance(result.ratchet_final_states, dict)


# ──────────────────────────────────────────────────────────────────────
# Built-in scenario tests
# ──────────────────────────────────────────────────────────────────────


class TestBuiltInScenarios:
    """Tests for the built-in scenario helper functions."""

    def test_data_exfiltration_scenario(self) -> None:
        name, profiles = build_data_exfiltration_scenario()
        result = run_ratchet_simulation(name, profiles)
        assert result.effectiveness_score == 1.0
        assert result.without_ratchet_leaks >= 1
        assert result.with_ratchet_leaks == 0

    def test_cross_agent_leak_scenario(self) -> None:
        name, profiles = build_cross_agent_leak_scenario()
        result = run_ratchet_simulation(name, profiles)
        assert result.effectiveness_score == 1.0
        assert result.without_ratchet_leaks >= 1
        assert result.with_ratchet_leaks == 0

    def test_gradual_escalation_scenario(self) -> None:
        name, profiles = build_gradual_escalation_scenario()
        result = run_ratchet_simulation(name, profiles)
        # After CONFIDENTIAL access, ratchet should block subsequent sends
        assert result.effectiveness_score > 0.0
        # Without ratchet, all sends after sensitive access should leak
        assert result.without_ratchet_leaks > result.with_ratchet_leaks


# ──────────────────────────────────────────────────────────────────────
# SensitivityLevel enum tests
# ──────────────────────────────────────────────────────────────────────


class TestSensitivityLevel:
    """Tests for the SensitivityLevel enum ordering."""

    def test_ordering(self) -> None:
        assert SensitivityLevel.PUBLIC < SensitivityLevel.INTERNAL
        assert SensitivityLevel.INTERNAL < SensitivityLevel.CONFIDENTIAL
        assert SensitivityLevel.CONFIDENTIAL < SensitivityLevel.RESTRICTED
        assert SensitivityLevel.RESTRICTED < SensitivityLevel.TOP_SECRET

    def test_int_values(self) -> None:
        assert int(SensitivityLevel.PUBLIC) == 0
        assert int(SensitivityLevel.TOP_SECRET) == 4
