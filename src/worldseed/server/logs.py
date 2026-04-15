"""OpenClaw session log reader — finds and reads agent session JSONL files."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$", re.IGNORECASE)


def _slugify_agent_id(agent_id: str) -> str:
    """Slugify agent ID for OpenClaw session routing.

    ASCII IDs pass through lowercase. Non-ASCII IDs get a stable md5-based slug.
    Must match slugifyAgentId() in TypeScript (openclaw-plugin/src/gateway.ts).
    """
    if _SAFE_ID_RE.match(agent_id):
        return agent_id.lower()
    return "ws-" + hashlib.md5(agent_id.encode("utf-8")).hexdigest()[:8]


def _resolve_openclaw_dir(openclaw_dir: str = "") -> Path:
    """Resolve OpenClaw data directory.

    Priority: explicit arg > OPENCLAW_DIR env var > ~/.openclaw
    """
    if openclaw_dir:
        return Path(openclaw_dir).expanduser()
    return Path(os.environ.get("OPENCLAW_DIR", "~/.openclaw")).expanduser()


def find_all_sessions(agent_id: str, openclaw_dir: str = "") -> list[dict[str, Any]]:
    """Find all OpenClaw sessions for a WorldSeed agent.

    Returns list of {run_id, session_key, file, updated_at} sorted newest first.
    """
    agents_dir = _resolve_openclaw_dir(openclaw_dir) / "agents"
    if not agents_dir.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for oc_agent_dir in agents_dir.iterdir():
        sessions_json = oc_agent_dir / "sessions" / "sessions.json"
        if not sessions_json.is_file():
            continue
        try:
            sessions = json.loads(sessions_json.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for skey, sdata in sessions.items():
            slug_prefix = f"agent:{_slugify_agent_id(agent_id)}:worldseed:"
            raw_prefix = f"agent:{agent_id}:worldseed:"
            if not (skey.startswith(slug_prefix) or skey.startswith(raw_prefix)):
                continue
            sf = sdata.get("sessionFile")
            if not sf or not Path(sf).is_file():
                continue
            parts = skey.split(":")
            run_id = parts[3] if len(parts) >= 4 else "unknown"
            results.append(
                {
                    "run_id": run_id,
                    "session_key": skey,
                    "file": sf,
                    "updated_at": sdata.get("updatedAt", 0),
                }
            )

    results.sort(key=lambda r: r["updated_at"], reverse=True)
    return results


def resolve_session_file(
    agent_id: str,
    run_id: str,
    openclaw_dir: str = "",
) -> Path | None:
    """Resolve the JSONL file path for an agent's session in a specific run."""
    all_sessions = find_all_sessions(agent_id, openclaw_dir=openclaw_dir)
    match = [s for s in all_sessions if s["run_id"] == run_id]
    if not match:
        return None
    p = Path(match[0]["file"])
    return p if p.is_file() else None


def read_session_logs(
    agent_id: str,
    run_id: str | None = None,
    limit: int = 0,
    openclaw_dir: str = "",
) -> list[dict[str, Any]]:
    """Read OpenClaw session JSONL for an agent, optionally for a specific run."""
    all_sessions = find_all_sessions(agent_id, openclaw_dir=openclaw_dir)
    if not all_sessions:
        return []

    if not run_id:
        return []
    match = [s for s in all_sessions if s["run_id"] == run_id]

    if not match:
        return []

    messages: list[dict[str, Any]] = []
    for line in Path(match[0]["file"]).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        obj_type = obj.get("type", "")
        if obj_type == "message":
            messages.append(obj.get("message", obj))
        elif obj_type == "toolResult":
            messages.append({"role": "tool", "content": obj.get("content", "")})

    return messages[-limit:] if limit > 0 else messages


def _build_slug_reverse_map(run_id: str) -> dict[str, str]:
    """Build slug -> original agent_id map from a run's config."""
    from worldseed.paths import run_dir

    config_path = run_dir(run_id) / "config.yaml"
    if not config_path.is_file():
        return {}
    try:
        import yaml

        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    result: dict[str, str] = {}
    for agent in cfg.get("agents", []):
        aid = agent.get("id", "")
        if aid:
            result[_slugify_agent_id(aid)] = aid
    return result


def read_agent_texts(
    run_id: str,
    openclaw_dir: str = "",
) -> list[dict[str, Any]]:
    """Extract all agents' text responses for a run.

    Scans all OpenClaw agent session files for the given run_id.
    Returns list of {agent_id, text, ts, tool_calls} sorted by timestamp.
    tool_calls is a summary of worldseed_act calls made in this turn.
    """
    agents_dir = _resolve_openclaw_dir(openclaw_dir) / "agents"
    if not agents_dir.is_dir():
        return []

    # Build slug -> original id reverse map for this run
    slug_map = _build_slug_reverse_map(run_id)

    # Collect session files: agent_id -> file path
    agent_files: dict[str, str] = {}
    for oc_agent_dir in agents_dir.iterdir():
        sessions_json = oc_agent_dir / "sessions" / "sessions.json"
        if not sessions_json.is_file():
            continue
        try:
            sessions = json.loads(sessions_json.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for skey, sdata in sessions.items():
            # Session key: agent:{slug_or_id}:worldseed:{run_id}
            parts = skey.split(":")
            if len(parts) < 4 or parts[2] != "worldseed" or parts[3] != run_id:
                continue
            sf = sdata.get("sessionFile")
            if sf and Path(sf).is_file():
                # Reverse-map slug to original agent_id
                raw_id = parts[1]
                agent_files[slug_map.get(raw_id, raw_id)] = sf

    results: list[dict[str, Any]] = []
    for agent_id, fpath in agent_files.items():
        # Parse session JSONL: collect text responses and preceding tool calls
        pending_tool_calls: list[dict[str, Any]] = []
        raw = Path(fpath).read_text(encoding="utf-8", errors="replace")
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "message":
                continue
            msg = obj.get("message", {})
            role = msg.get("role", "")
            if role != "assistant":
                if role == "user":
                    # New wake turn — reset pending tool calls
                    pending_tool_calls = []
                continue

            content = msg.get("content", [])
            stop = msg.get("stopReason", "")

            # Collect tool calls from toolUse messages
            if stop == "toolUse":
                for block in content:
                    if block.get("type") in ("toolCall", "tool_use"):
                        name = block.get("name", "")
                        args = block.get("arguments") or block.get("input") or {}
                        if "act" in name:
                            pending_tool_calls.append(
                                {
                                    "action": args.get("action", ""),
                                    "params": {
                                        k: v
                                        for k, v in args.items()
                                        if k
                                        not in (
                                            "agent_id",
                                            "action",
                                            "think_interval",
                                        )
                                    },
                                }
                            )

            # Extract text from stop messages
            if stop == "stop":
                for block in content:
                    if block.get("type") == "text" and block.get("text"):
                        text = block["text"].replace("[[reply_to_current]]", "").strip()
                        if text:
                            results.append(
                                {
                                    "agent_id": agent_id,
                                    "text": text,
                                    "ts": obj.get("timestamp", ""),
                                    "tool_calls": pending_tool_calls,
                                }
                            )
                pending_tool_calls = []

    results.sort(key=lambda r: r["ts"])
    return results
