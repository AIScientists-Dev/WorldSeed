"""CLI subcommand: worldseed runs."""

from __future__ import annotations


def runs() -> None:
    """List past runs saved to ~/.worldseed/runs/."""
    from worldseed.persistence import list_runs

    results = list_runs()
    if not results:
        print("No runs found in ~/.worldseed/runs/")
        return

    for r in results:
        start = r["start_time"]
        if isinstance(start, str) and len(start) >= 16:
            start = start[:16].replace("T", " ")
        print(
            f"  {r['run_id']:<12s}"
            f"  {r['scene_id']:<20s}"
            f"  {start}"
            f"  {r['tick_count']:>4d} ticks"
            f"  {r['agent_count']:>2d} agents"
            f"  {r['dm_calls']:>4d} DM calls"
        )
