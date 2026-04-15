"""Scene-agnostic context builder for gazette generation."""

from __future__ import annotations

import json
from typing import Any

import yaml

from worldseed.paths import run_dir

# ── Data loading ────────────────────────────────────────────


def load_run_data(run_id: str) -> dict[str, Any]:
    """Load all data from a run directory."""
    _run_dir = run_dir(run_id)
    if not _run_dir.is_dir():
        msg = f"Run directory not found: {_run_dir}"
        raise FileNotFoundError(msg)

    meta = json.loads((_run_dir / "meta.json").read_text(encoding="utf-8"))
    config_text = (_run_dir / "config.yaml").read_text(encoding="utf-8")
    config = yaml.safe_load(config_text)

    records: list[dict[str, Any]] = []
    stream_path = _run_dir / "stream.jsonl"
    if stream_path.exists():
        for line in stream_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))

    state_final: list[dict[str, Any]] | None = None
    state_path = _run_dir / "state_final.json"
    if state_path.exists():
        state_final = json.loads(state_path.read_text(encoding="utf-8"))

    return {
        "meta": meta,
        "config": config,
        "records": records,
        "state_final": state_final,
    }


# ── Language detection ──────────────────────────────────────


def detect_language(config: dict[str, Any]) -> str:
    """Detect language from scene description (CJK heuristic). Returns ISO code."""
    desc = config.get("scene", {}).get("description", "")
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in desc)
    return "zh" if has_cjk else "en"


# ── Action param helpers ────────────────────────────────────


def _get_free_text_params(action_def: dict[str, Any]) -> set[str]:
    return {p["name"] for p in action_def.get("params", []) if p.get("type") == "free_text"}


def _get_target_params(action_def: dict[str, Any]) -> set[str]:
    return {p["name"] for p in action_def.get("params", []) if p.get("type") == "entity_ref"}


def _format_action_record(r: dict[str, Any], actions: dict[str, Any]) -> str:
    """Format an action record using action definitions, not hardcoded names."""
    agent = r["agent_id"]
    action_type = r["action_type"]
    params = r.get("params", {})
    success = r["success"]
    reason = r.get("reason", "")

    action_def = actions.get(action_type, {})
    free_text_params = _get_free_text_params(action_def)
    target_params = _get_target_params(action_def)

    free_texts = {k: v for k, v in params.items() if k in free_text_params and v}
    targets = {k: v for k, v in params.items() if k in target_params and v}
    other = {k: v for k, v in params.items() if k not in free_text_params and k not in target_params}

    parts = [f"[Tick {r['tick']}] {agent} → {action_type}"]

    if targets:
        target_str = ", ".join(f"{k}={v}" for k, v in targets.items())
        parts.append(f"({target_str})")

    if other:
        other_str = ", ".join(f"{k}={v}" for k, v in other.items())
        parts.append(f"[{other_str}]")

    if free_texts:
        text = next(iter(free_texts.values()))
        parts.append(f': "{text}"')

    if not success:
        parts.append(f" ✗ ({reason})")

    return " ".join(parts[:2]) + "".join(parts[2:])


# ── Context builder ─────────────────────────────────────────


def build_context(
    data: dict[str, Any],
    language: str,
    assets: dict[str, str] | None = None,
) -> str:
    """Build scene-agnostic LLM context from run data."""
    config = data["config"]
    records: list[dict[str, Any]] = data["records"]
    state_final = data["state_final"]

    scene = config.get("scene", {})
    agents = config.get("agents", [])
    actions = config.get("actions", {})

    # Compute actual tick/agent counts from stream
    actual_ticks = max((r["tick"] for r in records), default=0)
    actual_agents = len({r["agent_id"] for r in records if r["kind"] == "register"})

    parts: list[str] = []

    # Section 1: Scene briefing
    parts.append("=== SCENE ===")
    if scene.get("description"):
        parts.append(scene["description"])
    if scene.get("setting"):
        parts.append(scene["setting"])
    parts.append(f"Total ticks: {actual_ticks}")
    parts.append(f"Agents: {actual_agents}")
    parts.append("")

    # Section 2: Dramatis personae
    parts.append("=== DRAMATIS PERSONAE ===")
    for agent in agents:
        parts.append(f"\n{agent['id']}:")
        char = agent.get("character", {})
        for key, val in char.items():
            if isinstance(val, list):
                parts.append(f"  {key}:")
                for item in val:
                    parts.append(f"    - {item}")
            elif isinstance(val, dict):
                parts.append(f"  {key}:")
                for k2, v2 in val.items():
                    parts.append(f"    {k2}: {v2}")
            else:
                parts.append(f"  {key}: {val}")
    parts.append("")

    # Section 3: Action vocabulary
    parts.append("=== ACTION VOCABULARY ===")
    for name, adef in actions.items():
        desc = adef.get("description", "")
        param_strs = []
        for p in adef.get("params", []):
            param_strs.append(f"{p['name']} ({p['type']})")
        params_line = ", ".join(param_strs) if param_strs else "none"
        parts.append(f"  {name}: {desc}  [params: {params_line}]")
    parts.append("")

    # Section 4: Event timeline
    parts.append("=== EVENT TIMELINE ===")
    interesting = [r for r in records if r["kind"] not in ("wakeup", "perceive")]

    for r in interesting:
        kind = r["kind"]
        tick = r["tick"]

        if kind == "register":
            parts.append(f"[Tick {tick}] {r['agent_id']} joined the scene")

        elif kind == "action":
            parts.append(_format_action_record(r, actions))

        elif kind == "dm_call":
            if r.get("failed"):
                continue
            narrative = r.get("narrative", "")
            effects = r.get("effects", [])
            agent_id = r["agent_id"]
            action = r["action"]
            parts.append(f"[Tick {tick}] [DM] {agent_id} {action}: {narrative}")
            for eff in effects:
                if eff.get("operator") == "emit_event":
                    parts.append(f"  → event: {eff.get('detail', '')}")
                elif eff.get("operator") in ("set", "increment", "decrement"):
                    target = eff.get("target", "")
                    value = eff.get("value", eff.get("by", ""))
                    parts.append(f"  → {eff['operator']} {target} = {value}")

        elif kind == "consequence":
            name = r.get("name", "")
            detail = r.get("detail", "")
            parts.append(f"[Tick {tick}] [CONSEQUENCE] {name}: {detail}")

        elif kind == "whisper":
            agent_id = r.get("agent_id", "")
            msg = r.get("message", "")
            parts.append(f"[Tick {tick}] [whisper to {agent_id}]: {msg}")

    parts.append("")

    # Section 5: Final state
    if state_final:
        parts.append("=== FINAL WORLD STATE ===")
        for entity in state_final:
            eid = entity["id"]
            etype = entity["type"]
            props = {k: v for k, v in entity.items() if k not in ("id", "type")}
            parts.append(f"  {eid} ({etype}): {json.dumps(props, ensure_ascii=False)}")
    parts.append("")

    # Section 6: Available images (entities only — scene/agent images
    # are placed automatically by the renderer)
    entity_slots = sorted(s for s in (assets or {}) if s.startswith("entities/"))
    if entity_slots:
        parts.append("=== AVAILABLE IMAGES ===")
        parts.append(
            "Pick one image for EACH story from these entity slots."
            " Each slot is a location, item, or object in the scene."
        )
        for slot in entity_slots:
            parts.append(f"  {slot}")
        parts.append("")

    return "\n".join(parts)


# ── System prompt ───────────────────────────────────────────


def build_system_prompt(language: str) -> str:  # noqa: E501
    """Build the gazette system prompt with i18n support."""
    # Long lines are intentional — this is an LLM prompt, not code.
    # fmt: off
    return (
        "You are a journalist writing a newspaper edition"
        " summarizing the events of a simulated world.\n"
        "\n"
        f"IMPORTANT: Write ALL content in {language}.\n"
        "\n"
        "Writing style — strict journalism:\n"
        "- Inverted pyramid: most important facts first,"
        " details expand paragraph by paragraph.\n"
        "- Short paragraphs (2-3 sentences), short sentences."
        " No long lyrical passages.\n"
        '- Use quotes: "according to X", "witnesses say",'
        ' "records show".\n'
        "  You may reasonably infer what characters would say"
        " based on their actions and personality."
        " Use quotation marks.\n"
        "- Concrete facts: time (Tick N), location, action."
        " No vague descriptions.\n"
        "- Analysis and background: moderate reporter analysis"
        " — why this matters, what it means for others,"
        " how timing was critical.\n"
        '- NEVER mention "simulation"'
        " — for readers, these are real events.\n"
        "- Headlines must be strong, specific,"
        " like real news headlines.\n"
        "\n"
        "Section requirements:\n"
        "- edition_title: A newspaper name"
        " that fits the scene setting and language.\n"
        "- breaking_banner: One sentence,"
        " the single most dramatic/urgent fact.\n"
        "- lead_story: Core narrative arc."
        " 5-7 short paragraphs, inverted pyramid."
        " Use Tick N for time.\n"
        "- secondary_stories: 2-3 stories,"
        " each 3-4 paragraphs,"
        " different angles from the lead.\n"
        "- editorials: 1-2 first-person opinion pieces"
        " from the most dramatically affected agents.\n"
        "  Write in that agent's voice based on their"
        " personality, goals, and secrets.\n"
        '  Use natural time expressions ("that afternoon",'
        ' "moments later"), NOT "Tick 8".\n'
        "- ticker: 5-8 factual one-liners,"
        " reverse chronological. Use Tick N here.\n"
        "- pull_quote: The single most striking line"
        " — could be from an editorial,"
        " a piece of dialogue, or a DM narrative."
    )
    # fmt: on
