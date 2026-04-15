"""CLI subcommand: worldseed validate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def validate_cmd(args: argparse.Namespace) -> None:
    """Validate a scene config."""
    from worldseed.scene.config import load_config
    from worldseed.scene.validator import validate

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"File not found: {config_path}")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"{config_path.name}: schema error\n\n  {e}")
        sys.exit(1)

    result = validate(config, physics_ticks=args.ticks)

    if args.json_output:
        output = {
            "file": str(config_path),
            "valid": result.ok,
            "stats": {
                "entities": result.entity_count,
                "agents": result.agent_count,
                "spaces": result.space_count,
                "actions": result.action_count,
            },
            "messages": [
                {
                    "level": m.level,
                    "code": m.code,
                    "summary": m.summary,
                    "location": m.location,
                    "suggestion": m.suggestion,
                }
                for m in result.messages
                if args.pedantic or m.level != "hint"
            ],
            "sanity": [{"name": s.name, "passed": s.passed, "detail": s.failure_detail} for s in result.sanity],
        }
        print(json.dumps(output, indent=2))
    else:
        status = "valid" if result.ok else "INVALID"
        print(f"{config_path.name}: {status}\n")
        print(result.summary(pedantic=args.pedantic))

    sys.exit(0 if result.ok else 1)
