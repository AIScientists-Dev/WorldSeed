"""Live poker test — run ticks, submit actions, track real data in jsonl."""

import asyncio
import json
from pathlib import Path

from worldseed.dm.providers.llm import LiteLLMDMProvider
from worldseed.engine.action_queue import ActionQueue
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.engine.tick import TickEngine
from worldseed.models.action import ActionSubmission
from worldseed.models.entity import Entity
from worldseed.persistence import RunRecorder
from worldseed.scene.config import load_config


def print_state(store: StateStore, event_log: EventLog, tick: int) -> None:
    """Print current world state."""
    table = store.get("table")
    deck = store.get("deck")
    print(f"\n{'=' * 60}")
    print(f"TICK {tick} | Phase: {table['phase']} | Pot: {table['pot']} | Bet: {table['current_bet']}")
    print(f"Community: {table['community_cards']}")
    print(f"Deck remaining: {len(deck['cards'])}")
    print("-" * 60)
    for pid in ["shark", "rookie", "hustler", "analyst"]:
        p = store.get(pid)
        if p is None:
            continue
        status = "FOLDED" if p["folded"] else ("ACTED" if p["acted"] else "waiting")
        print(f"  {pid:10s} | chips={p['chips']:4} | bet={p['bet_this_round']:3} | hand={p['hand']} | {status}")
    print(f"{'=' * 60}")


async def main() -> None:
    config_path = Path("configs/poker_test.yaml")
    config = load_config(config_path)

    store = StateStore()
    for e in config.entities:
        store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))

    # Register agents
    from worldseed.agent_registry import AgentRegistry

    registry = AgentRegistry(config, store)
    registry.register_from_config()

    event_log = EventLog()
    action_queue = ActionQueue()
    dm = LiteLLMDMProvider(model="gpt-4o-mini")
    import secrets

    recorder = RunRecorder(
        run_id=secrets.token_hex(4),
        scene_id="poker_test",
        dm_model="gpt-4o-mini",
        config_path=config_path,
    )

    engine = TickEngine(
        config=config,
        store=store,
        event_log=event_log,
        action_queue=action_queue,
        dm_provider=dm,
        recorder=recorder,
    )

    # === TICK 1: Deal cards (consequence fires automatically) ===
    print("\n>>> TICK 1: Deal hands")
    await engine.step_async()
    print_state(store, event_log, 1)

    # Verify deal happened
    for pid in ["shark", "rookie", "hustler", "analyst"]:
        hand = store.get(pid)["hand"]
        assert len(hand) == 2, f"{pid} should have 2 cards, got {len(hand)}: {hand}"
    print("✓ All players dealt 2 cards")

    # === TICK 2: Pre-flop betting ===
    print("\n>>> TICK 2: Pre-flop betting")
    # shark raises to 50
    action_queue.submit(ActionSubmission(agent_id="shark", action_type="raise_bet", params={"amount": 50}))
    await engine.step_async()
    print_state(store, event_log, 2)

    # === TICK 3: More betting ===
    print("\n>>> TICK 3: Responses")
    action_queue.submit(ActionSubmission(agent_id="rookie", action_type="call", params={}))
    action_queue.submit(
        ActionSubmission(
            agent_id="hustler",
            action_type="talk",
            params={"message": "Nice raise, shark. You sure about that?"},
        )
    )
    await engine.step_async()
    print_state(store, event_log, 3)

    # === TICK 4: More betting ===
    print("\n>>> TICK 4: Hustler and analyst act")
    action_queue.submit(ActionSubmission(agent_id="hustler", action_type="raise_bet", params={"amount": 100}))
    action_queue.submit(ActionSubmission(agent_id="analyst", action_type="fold", params={}))
    await engine.step_async()
    print_state(store, event_log, 4)

    # === TICK 5: Shark and rookie respond to hustler's raise ===
    print("\n>>> TICK 5: Respond to hustler raise")
    action_queue.submit(ActionSubmission(agent_id="shark", action_type="call", params={}))
    action_queue.submit(ActionSubmission(agent_id="rookie", action_type="fold", params={}))
    await engine.step_async()
    print_state(store, event_log, 5)

    # === Manual phase advance to flop ===
    print("\n>>> Advancing to flop_deal")
    store.update_property("table", "phase", "flop_deal")
    # Reset acted flags
    for pid in ["shark", "rookie", "hustler", "analyst"]:
        store.update_property(pid, "acted", False)
        store.update_property(pid, "bet_this_round", 0)

    # === TICK 6: Flop deal (consequence fires) ===
    print("\n>>> TICK 6: Flop")
    await engine.step_async()
    print_state(store, event_log, 6)
    community = store.get("table")["community_cards"]
    assert len(community) == 3, f"Flop should deal 3 cards, got {len(community)}"
    print(f"✓ Flop dealt: {community}")

    # === TICK 7: Post-flop betting ===
    print("\n>>> TICK 7: Post-flop")
    action_queue.submit(ActionSubmission(agent_id="shark", action_type="check", params={}))
    action_queue.submit(ActionSubmission(agent_id="hustler", action_type="raise_bet", params={"amount": 150}))
    await engine.step_async()
    print_state(store, event_log, 7)

    # === TICK 8: Shark responds ===
    print("\n>>> TICK 8: Shark responds")
    action_queue.submit(ActionSubmission(agent_id="shark", action_type="call", params={}))
    await engine.step_async()
    print_state(store, event_log, 8)

    # === Advance to showdown ===
    print("\n>>> Advancing to showdown")
    store.update_property("table", "phase", "showdown")

    # === TICK 9: Showdown — DM judges ===
    print("\n>>> TICK 9: SHOWDOWN (DM judges)")
    await engine.step_async()
    print_state(store, event_log, 9)

    # Print all events
    print("\n>>> ALL EVENTS:")
    for e in event_log.get_events():
        print(f"  [tick {e.tick}] {e.type}: {e.detail}")

    # Save and print stream
    recorder.finalize(
        store=[e.to_full_dict() for e in store.all_entities()],
        tick=engine.tick,
    )
    stream_path = recorder.run_dir / "stream.jsonl"
    print(f"\n>>> STREAM saved to: {stream_path}")
    print(f">>> Run dir: {recorder.run_dir}")

    # Read and summarize stream
    lines = stream_path.read_text().strip().splitlines()
    events = [json.loads(line) for line in lines]
    print(f"\nStream: {len(events)} entries")
    for evt in events:
        kind = evt.get("kind", "?")
        tick = evt.get("tick", "?")
        detail = ""
        if kind == "action":
            success = evt.get("success")
            status = "✓" if success else "✗ " + str(evt.get("reason", ""))
            detail = f"{evt.get('agent_id')}: {evt.get('action_type')} {status}"
        elif kind == "consequence":
            detail = evt.get("name", "")
        elif kind == "dm_call":
            detail = f"{evt.get('action', '')} — {evt.get('narrative', '')[:60]}"
        elif kind == "event":
            detail = evt.get("detail", "")[:80]
        print(f"  [{tick:>2}] {kind:>12}: {detail}")


if __name__ == "__main__":
    asyncio.run(main())
