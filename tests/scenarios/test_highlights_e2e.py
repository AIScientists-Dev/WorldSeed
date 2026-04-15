"""End-to-end scenario test for the highlights system.

Exercises all three layers through the full engine pipeline:
  Layer 1 — config-defined highlight trigger (food <= 2)
  Layer 2 — engine event annotations (action rejected, entity created)
  Layer 3 — omniscient agent perceives all highlights
"""

from __future__ import annotations

import json
from pathlib import Path

from worldseed.persistence import RunRecorder
from worldseed.world import WorldEngine


def _build_config() -> dict:
    """Inline config that exercises all highlight layers."""
    return {
        "scene": {
            "id": "highlight_test",
            "description": ("A small outpost with dwindling food. Two agents compete for resources."),
        },
        "entities": [
            {
                "id": "food",
                "type": "resource",
                "properties": {"quantity": 5},
            },
        ],
        "templates": {
            "person": {
                "properties": {"alive": True},
            },
        },
        "agents": [
            {
                "id": "alice",
                "template": "person",
                "character": {"personality": "cautious"},
            },
            {
                "id": "bob",
                "template": "person",
                "character": {"personality": "aggressive"},
            },
            {
                "id": "narrator",
                "template": "person",
                "omniscient": True,
                "character": {"role": "narrator"},
            },
        ],
        "actions": {
            "eat": {
                "description": "Consume food from the supply.",
                "params": [
                    {
                        "name": "amount",
                        "type": "number",
                        "description": "How much to eat",
                    },
                ],
                "preconditions": [
                    {
                        "operator": "check",
                        "left": "food.quantity",
                        "op": ">=",
                        "right": "$amount",
                    },
                ],
                "effects": [
                    {
                        "operator": "decrement",
                        "target": "food.quantity",
                        "by": "$amount",
                        "min": 0,
                    },
                ],
                "events": [
                    {
                        "type": "ate",
                        "detail": "$agent ate $amount food",
                        "ttl": 3,
                        "scope": "global",
                    },
                ],
            },
            "build_shelter": {
                "description": "Build a shelter entity.",
                "params": [],
                "preconditions": [],
                "effects": [
                    {
                        "operator": "create_entity",
                        "id": "shelter",
                        "type": "structure",
                        "properties": {"durability": 10},
                    },
                ],
                "events": [
                    {
                        "type": "built",
                        "detail": "$agent built a shelter",
                        "ttl": 3,
                        "scope": "global",
                    },
                ],
            },
        },
        "consequences": {},
        "highlights": {
            "food_crisis": {
                "trigger": [
                    {
                        "operator": "check",
                        "left": "food.quantity",
                        "op": "<=",
                        "right": 2,
                    },
                ],
                "label": "Food supply critically low!",
            },
        },
        "auto_tick": [],
        "perception": {
            "visibility": [],
            "hidden_properties": [],
            "event_scopes": {},
        },
    }


class TestHighlightsE2E:
    """Full engine pipeline test for highlights."""

    def _make_engine(self) -> WorldEngine:
        from worldseed.models.config_schema import SceneConfig

        config = SceneConfig.model_validate(_build_config())
        engine = WorldEngine(config=config)
        engine.register_from_config()
        return engine

    def test_layer1_config_highlight_fires(self) -> None:
        """Config-defined highlight triggers when food <= 2."""
        engine = self._make_engine()

        # Eat food down to 2: 5 - 3 = 2
        result = engine.submit("alice", "eat", {"amount": 3})
        assert result.success
        assert engine.state.get("food")["quantity"] == 2

        # Step to run highlight scanner
        engine.step()

        # Check highlight event exists in event log
        highlights = [e for e in engine.event_log.get_events() if e.highlight and e.type == "highlight"]
        assert len(highlights) == 1
        assert highlights[0].detail == "Food supply critically low!"
        assert highlights[0].scope == "admin"

    def test_layer1_no_retrigger(self) -> None:
        """on_change highlight should not fire again while still true."""
        engine = self._make_engine()

        engine.submit("alice", "eat", {"amount": 3})  # food = 2
        engine.step()  # fires highlight

        engine.submit("alice", "eat", {"amount": 1})  # food = 1
        engine.step()  # should NOT re-fire

        highlights = [e for e in engine.event_log.get_events() if e.highlight and e.type == "highlight"]
        assert len(highlights) == 1  # still just one

    def test_layer2_action_rejected_highlight(self) -> None:
        """Rejected action emits a highlight event."""
        engine = self._make_engine()

        # Try to eat more than available
        result = engine.submit("bob", "eat", {"amount": 999})
        assert not result.success

        # Step to deliver events
        engine.step()

        rejected = [e for e in engine.event_log.get_events() if e.highlight and e.type == "action_rejected"]
        assert len(rejected) == 1
        assert "bob" in rejected[0].detail
        assert "eat" in rejected[0].detail

    def test_layer2_entity_created_highlight(self) -> None:
        """Creating an entity emits a highlight event."""
        engine = self._make_engine()

        result = engine.submit("alice", "build_shelter", {})
        assert result.success

        # Verify entity was created
        shelter = engine.state.get("shelter")
        assert shelter is not None
        assert shelter["durability"] == 10

        # Check highlight
        created = [e for e in engine.event_log.get_events() if e.highlight and e.type == "entity_created"]
        assert len(created) == 1
        assert "shelter" in created[0].detail

    def test_layer3_omniscient_does_not_see_admin_highlights(self) -> None:
        """Admin-scoped events are dashboard-only — no agent receives them."""
        engine = self._make_engine()

        engine.submit("bob", "eat", {"amount": 999})
        engine.submit("alice", "build_shelter", {})
        engine.submit("alice", "eat", {"amount": 4})
        engine.step()

        narrator_data = engine.read_inbox("narrator")
        events = narrator_data.get("events", [])
        event_types = [e.type for e in events]

        assert "highlight" not in event_types
        assert "action_rejected" not in event_types
        assert "entity_created" not in event_types

    def test_layer3_normal_agent_no_admin_events(self) -> None:
        """Normal agents should NOT see admin-scoped highlights."""
        engine = self._make_engine()

        # Trigger some highlights
        engine.submit("bob", "eat", {"amount": 999})
        engine.submit("alice", "build_shelter", {})
        engine.step()

        # Alice (normal agent) should not see admin events
        alice_data = engine.read_inbox("alice")
        events = alice_data.get("events", [])
        event_types = [e.type for e in events]

        assert "action_rejected" not in event_types
        assert "highlight" not in event_types

        # But she should see normal global events
        assert "built" in event_types

    def test_full_pipeline_all_layers(self) -> None:
        """Integration: all three layers fire in the same run."""
        engine = self._make_engine()

        # Turn 1: build + eat most food
        engine.submit("alice", "build_shelter", {})
        engine.submit("alice", "eat", {"amount": 4})  # food = 1
        engine.step()

        # Turn 2: bob tries to eat but fails
        result = engine.submit("bob", "eat", {"amount": 5})
        assert not result.success
        engine.step()

        # Collect all highlights
        all_highlights = [e for e in engine.event_log.get_events() if e.highlight]
        highlight_types = {e.type for e in all_highlights}

        # All three layers produced highlights
        assert "highlight" in highlight_types  # Layer 1
        assert "entity_created" in highlight_types  # Layer 2
        assert "action_rejected" in highlight_types  # Layer 2

        # Narrator does NOT see admin-scoped highlights (dashboard-only)
        narrator_data = engine.read_inbox("narrator")
        narrator_event_types = {e.type for e in narrator_data.get("events", [])}
        assert "highlight" not in narrator_event_types
        assert "entity_created" not in narrator_event_types
        assert "action_rejected" not in narrator_event_types

    def test_highlights_recorded_to_stream(self) -> None:
        """Highlights are persisted to stream.jsonl for API/frontend."""
        from worldseed.models.config_schema import SceneConfig

        run_id = "test-highlights-stream"
        recorder = RunRecorder(
            run_id=run_id,
            config_path=None,
            scene_id="test",
            dm_model="mock",
        )
        try:
            config = SceneConfig.model_validate(_build_config())
            engine = WorldEngine(
                config=config,
                recorder=recorder,
            )
            engine.register_from_config()

            # Layer 2: action rejected
            engine.submit("bob", "eat", {"amount": 999})

            # Layer 2: entity created
            engine.submit("alice", "build_shelter", {})

            # Layer 1: food crisis (5 - 4 = 1)
            engine.submit("alice", "eat", {"amount": 4})
            engine.step()

            # Read stream.jsonl
            run_dir = Path.home() / ".worldseed" / "runs" / run_id
            stream_path = run_dir / "stream.jsonl"
            records = [json.loads(line) for line in stream_path.read_text().splitlines()]
            highlight_records = [r for r in records if r.get("kind") == "highlight"]

            # All three layers should have recorded
            sources = {r.get("source") for r in highlight_records}
            assert "action_rejected" in sources  # Layer 2
            assert "entity_created" in sources  # Layer 2
            assert "config" in sources  # Layer 1

            # Each has a label
            for r in highlight_records:
                assert "label" in r
                assert r["label"]  # non-empty
        finally:
            # Cleanup test run
            import shutil

            run_dir = Path.home() / ".worldseed" / "runs" / run_id
            if run_dir.exists():
                shutil.rmtree(run_dir)
