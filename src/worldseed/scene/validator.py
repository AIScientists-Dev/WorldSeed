"""Scene Config validator — multi-level validation beyond Pydantic schema.

Level 1 (Schema):     Pydantic handles this in config.py.
Level 2 (References): Static checks — do IDs exist? Is the graph connected?
Level 3 (Physics):    Simulate N ticks with no agents — resource trajectories.
Level 4 (Smoke):      Try each action with each agent — can anything execute?
Level 5 (Sanity):     Run the config's own sanity_checks section.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Literal

from worldseed.models.config_schema import SceneConfig

# ============================================================
# Data structures
# ============================================================


@dataclass
class ValidationMessage:
    """A single validation finding."""

    level: Literal["error", "warning", "hint"]
    code: str
    summary: str
    location: str | None = None
    suggestion: str | None = None


@dataclass
class PhysicsReport:
    """Resource trajectories from N ticks with no agent actions."""

    ticks: int = 0
    trajectories: dict[str, list[float]] = field(default_factory=dict)
    # key = "entity_id.property", value = [val_tick0, val_tick1, ...]
    consequences_triggered: list[str] = field(default_factory=list)
    consequences_never_triggered: list[str] = field(default_factory=list)


@dataclass
class SmokeReport:
    """Per-action executability in initial state."""

    # action_name -> list of agent IDs that can execute it
    action_agents: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SanityResult:
    """Result of one sanity check."""

    name: str
    passed: bool
    failure_step: int | None = None
    failure_detail: str | None = None


@dataclass
class ValidationResult:
    """Complete validation output."""

    messages: list[ValidationMessage] = field(default_factory=list)
    physics: PhysicsReport | None = None
    smoke: SmokeReport | None = None
    sanity: list[SanityResult] = field(default_factory=list)
    # Config stats for summary
    entity_count: int = 0
    agent_count: int = 0
    space_count: int = 0
    action_count: int = 0

    @property
    def ok(self) -> bool:
        return not any(m.level == "error" for m in self.messages)

    @property
    def errors(self) -> list[ValidationMessage]:
        return [m for m in self.messages if m.level == "error"]

    @property
    def warnings(self) -> list[ValidationMessage]:
        return [m for m in self.messages if m.level == "warning"]

    @property
    def hints(self) -> list[ValidationMessage]:
        return [m for m in self.messages if m.level == "hint"]

    def add(self, msg: ValidationMessage) -> None:
        self.messages.append(msg)

    def summary(self, pedantic: bool = False) -> str:
        """Human-readable summary."""
        lines: list[str] = []
        scene_info = f"  Entities: {self.entity_count} ({self.agent_count} agents, {self.space_count} spaces)"
        lines.append(scene_info)
        lines.append(f"  Actions:  {self.action_count}")
        lines.append("")

        # Errors
        if self.errors:
            lines.append(f"  Level 2 — References: {len(self.errors)} error(s)")
            for m in self.errors:
                lines.append(f"    [{m.code}] {m.summary}")
                if m.location:
                    lines.append(f"           at {m.location}")
                if m.suggestion:
                    lines.append(f"           {m.suggestion}")
        else:
            lines.append("  Level 2 — References: OK")

        # Physics
        if self.physics:
            lines.append(f"  Level 3 — Physics ({self.physics.ticks} ticks, no agents):")
            for key, vals in self.physics.trajectories.items():
                if len(vals) >= 2 and vals[0] != vals[-1]:
                    lines.append(f"    {key}: {vals[0]} -> {vals[-1]:.1f}")
            if self.physics.consequences_triggered:
                lines.append(f"    Consequences triggered: {', '.join(self.physics.consequences_triggered)}")
            if self.physics.consequences_never_triggered:
                lines.append(f"    Never triggered: {', '.join(self.physics.consequences_never_triggered)}")

        # Smoke
        if self.smoke:
            lines.append("  Level 4 — Smoke:")
            for action, agents in self.smoke.action_agents.items():
                if agents:
                    lines.append(f"    {action}: {len(agents)} agent(s) can execute")
                else:
                    lines.append(f"    {action}: 0 agents (unreachable in initial state)")

        # Sanity
        if self.sanity:
            passed = sum(1 for s in self.sanity if s.passed)
            total = len(self.sanity)
            lines.append(f"  Level 5 — Sanity: {passed}/{total} checks passed")
            for s in self.sanity:
                mark = "pass" if s.passed else "FAIL"
                lines.append(f"    [{mark}] {s.name}")
                if not s.passed and s.failure_detail:
                    lines.append(f"           step {s.failure_step}: {s.failure_detail}")

        # Warnings & hints count
        if self.warnings:
            lines.append("")
            lines.append(f"  {len(self.warnings)} warning(s):")
            for m in self.warnings:
                lines.append(f"    [{m.code}] {m.summary}")
        if self.hints and pedantic:
            lines.append(f"  {len(self.hints)} hint(s):")
            for m in self.hints:
                lines.append(f"    [{m.code}] {m.summary}")
        elif self.hints:
            lines.append(f"  {len(self.hints)} hint(s) (use --pedantic to see)")

        return "\n".join(lines)


# ============================================================
# Helpers
# ============================================================


def _suggest_fix(bad_id: str, valid_ids: set[str]) -> str | None:
    """Fuzzy match a bad ID against valid ones."""
    matches = difflib.get_close_matches(bad_id, valid_ids, n=1, cutoff=0.6)
    if matches:
        return f"Did you mean '{matches[0]}'?"
    return None


# ============================================================
# Main entry point
# ============================================================


def validate(
    config: SceneConfig,
    physics_ticks: int = 50,
    run_sanity: bool = True,
) -> ValidationResult:
    """Run all validation levels."""
    from worldseed.scene.checks.physics import run_physics
    from worldseed.scene.checks.refs import (
        check_action_params,
        check_agent_locations,
        check_auto_tick_emit_event,
        check_duplicate_ids,
        check_effect_targets,
        check_enum_from,
        check_event_scopes,
        check_graph_connectivity,
        check_relationship_targets,
    )
    from worldseed.scene.checks.sanity import run_sanity_checks
    from worldseed.scene.checks.smoke import run_smoke
    from worldseed.scene.checks.ui_consistency import check_ui_consistency

    result = ValidationResult()

    # Stats
    result.entity_count = len(config.entities)
    result.agent_count = len(config.agents)
    result.space_count = sum(1 for e in config.entities if e.type == "space")
    result.action_count = len(config.actions)

    entity_ids = {e.id for e in config.entities} | {a.id for a in config.agents}

    # Level 2: Static reference checks
    check_duplicate_ids(config, result)
    check_relationship_targets(config, entity_ids, result)
    check_effect_targets(config, entity_ids, result)
    check_agent_locations(config, entity_ids, result)
    check_event_scopes(config, result)
    check_action_params(config, result)
    check_enum_from(config, result)
    check_graph_connectivity(config, result)
    check_auto_tick_emit_event(config, result)

    # UI consistency checks
    check_ui_consistency(config, result)

    # Level 3-5 only if no hard errors
    if result.ok:
        result.physics = run_physics(config, physics_ticks)
        result.smoke = run_smoke(config)
        if run_sanity and config.sanity_checks:
            result.sanity = run_sanity_checks(config)
            # Failed sanity checks become warnings (not errors)
            for s in result.sanity:
                if not s.passed:
                    result.add(
                        ValidationMessage(
                            level="warning",
                            code="W010",
                            summary=f"Sanity check failed: '{s.name}'",
                            location=f"sanity_checks[{s.name}] step {s.failure_step}",
                            suggestion=s.failure_detail,
                        )
                    )

    return result
