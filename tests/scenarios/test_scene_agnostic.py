"""Prove the engine is scene-agnostic: diverse configs, zero hardcoded names."""

from __future__ import annotations

from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import InboxManager
from worldseed.engine.perceiver import Perceiver
from worldseed.engine.rules_engine import RulesEngine
from worldseed.engine.state_store import StateStore
from worldseed.models import ActionSubmission, Entity
from worldseed.models.config_schema import (
    ActionConfig,
    EffectConfig,
    EventConfig,
    ParamConfig,
    PerceptionConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)

# ============================================================
# Scenario 1: Forum — NO spatial concept, all global
# ============================================================


class TestForumScene:
    """Internet forum: no location, no space, no connects_to."""

    def test_upvote_changes_state(self) -> None:
        config = SceneConfig(
            scene=SceneMetaConfig(id="forum", description="Forum"),
            entities=[],
            actions={
                "upvote": ActionConfig(
                    description="Upvote a thread",
                    params=[ParamConfig(name="thread", type="entity_ref")],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="$thread.votes",
                            by=1,
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="upvote",
                            detail="$agent upvoted $thread",
                            ttl=1,
                            scope="global",
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="poster", type="agent", _data={"karma": 10}))
        store.add(Entity(id="thread_1", type="thread", _data={"votes": 0}))

        event_log = EventLog()
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(agent_id="poster", action_type="upvote", params={"thread": "thread_1"}),
            tick=1,
        )
        assert result.success
        assert store.get("thread_1")["votes"] == 1  # type: ignore[union-attr]
        assert event_log.get_events()[0].type == "upvote"
        assert event_log.get_events()[0].scope == "global"

    def test_global_perception_sees_everything(self) -> None:
        """With empty visibility rules, all agents see all entities."""
        store = StateStore()
        store.add(Entity(id="user_a", type="agent", _data={"karma": 10}))
        store.add(Entity(id="user_b", type="agent", _data={"karma": 50}))
        store.add(Entity(id="thread_x", type="thread", _data={"votes": 3}))
        store.add(Entity(id="board", type="board", _data={"topic": "general"}))

        mgr = InboxManager()
        perception = PerceptionConfig()  # empty = all visible
        p = Perceiver(store, EventLog(), mgr, perception)
        p.deliver(1)

        data = mgr.get_or_create("user_a").read()
        snapshot = data["current_state"]
        # user_a sees user_b, thread_x, and board
        assert "user_b" in snapshot.visible_agents
        assert "thread_x" in snapshot.visible_entities
        assert "board" in snapshot.visible_entities


# ============================================================
# Scenario 2: Starship — renamed spatial properties
# ============================================================


class TestStarshipScene:
    """Starship: sector (not location), warp_gate (not connects_to)."""

    def test_navigate_changes_sector(self) -> None:
        config = SceneConfig(
            scene=SceneMetaConfig(id="starship", description="Starship"),
            entities=[],
            actions={
                "navigate": ActionConfig(
                    description="Warp to connected deck",
                    params=[ParamConfig(name="destination", type="entity_ref")],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$destination",
                            op="in",
                            right=("relationships_of($agent.sector, type=warp_gate)"),
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$agent.sector",
                            value="$destination",
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="navigate",
                            detail="$agent warped to $destination",
                            ttl=1,
                            scope="global",
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(
            Entity(
                id="bridge",
                type="deck",
                _data={
                    "designation": "Bridge",
                    "warp_gate": ["engineering"],
                },
            )
        )
        store.add(
            Entity(
                id="engineering",
                type="deck",
                _data={
                    "designation": "Engineering",
                    "warp_gate": ["bridge"],
                },
            )
        )
        store.add(Entity(id="captain", type="agent", _data={"sector": "bridge"}))

        engine = RulesEngine(config, store, EventLog())

        result = engine.process_action(
            ActionSubmission(
                agent_id="captain",
                action_type="navigate",
                params={"destination": "engineering"},
            ),
            tick=1,
        )
        assert result.success
        assert store.get("captain")["sector"] == "engineering"  # type: ignore[union-attr]

    def test_navigate_rejected_no_warp_gate(self) -> None:
        config = SceneConfig(
            scene=SceneMetaConfig(id="starship", description="Starship"),
            entities=[],
            actions={
                "navigate": ActionConfig(
                    description="Warp to connected deck",
                    params=[ParamConfig(name="destination", type="entity_ref")],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$destination",
                            op="in",
                            right=("relationships_of($agent.sector, type=warp_gate)"),
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$agent.sector",
                            value="$destination",
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(
            Entity(
                id="bridge",
                type="deck",
                _data={"warp_gate": ["engineering"]},
            )
        )
        store.add(Entity(id="cargo", type="deck", _data={}))
        store.add(Entity(id="captain", type="agent", _data={"sector": "bridge"}))

        engine = RulesEngine(config, store, EventLog())

        result = engine.process_action(
            ActionSubmission(
                agent_id="captain",
                action_type="navigate",
                params={"destination": "cargo"},
            ),
            tick=1,
        )
        assert not result.success  # cargo not reachable via warp_gate

    def test_sector_based_perception(self) -> None:
        """Visibility rule uses 'sector', not 'location'."""
        store = StateStore()
        store.add(Entity(id="captain", type="agent", _data={"sector": "bridge"}))
        store.add(Entity(id="engineer", type="agent", _data={"sector": "engineering"}))
        store.add(Entity(id="reactor", type="equipment", _data={"sector": "engineering"}))
        store.add(Entity(id="console", type="equipment", _data={"sector": "bridge"}))

        mgr = InboxManager()
        perception = PerceptionConfig(
            visibility=[
                PreconditionConfig(
                    operator="check",
                    left="$observer.sector",
                    op="==",
                    right="$entity.sector",
                )
            ],
        )
        p = Perceiver(store, EventLog(), mgr, perception)
        p.deliver(1)

        captain_data = mgr.get_or_create("captain").read()
        snap = captain_data["current_state"]
        # Captain on bridge sees console, not reactor or engineer
        assert "console" in snap.visible_entities
        assert "reactor" not in snap.visible_entities
        assert "engineer" not in snap.visible_agents


# ============================================================
# Scenario 3: Single Room — no exits, no movement
# ============================================================


class TestSingleRoomScene:
    """Escape room: one room, everyone sees everything in it."""

    def test_examine_works(self) -> None:
        config = SceneConfig(
            scene=SceneMetaConfig(id="escape", description="Escape room"),
            entities=[],
            actions={
                "examine": ActionConfig(
                    description="Examine a puzzle",
                    params=[ParamConfig(name="target", type="entity_ref")],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="$agent.clues_found",
                            by=1,
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="examine",
                            detail="$agent examined $target",
                            ttl=2,
                            scope="global",
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(
            Entity(
                id="detective",
                type="agent",
                _data={"in_chamber": "room", "clues_found": 0},
            )
        )
        store.add(
            Entity(
                id="safe",
                type="puzzle",
                _data={"state": "locked", "in_chamber": "room"},
            )
        )

        engine = RulesEngine(config, store, EventLog())
        result = engine.process_action(
            ActionSubmission(agent_id="detective", action_type="examine", params={"target": "safe"}),
            tick=1,
        )
        assert result.success
        assert store.get("detective")["clues_found"] == 1  # type: ignore[union-attr]


# ============================================================
# Scenario 4: Terrarium — zero agents, pure auto_tick
# ============================================================


class TestTerrariumScene:
    """Sealed ecosystem: no agents, world evolves through auto_tick."""

    def test_auto_tick_evolves_world(self) -> None:
        from worldseed.engine.action_queue import ActionQueue
        from worldseed.engine.tick import TickEngine
        from worldseed.models.config_schema import AutoTickConfig

        config = SceneConfig(
            scene=SceneMetaConfig(id="terrarium", description="Terrarium"),
            entities=[],
            actions={},
            auto_tick=[
                AutoTickConfig(
                    description="Moss grows",
                    effects=[EffectConfig(operator="increment", target="moss.biomass", by=2)],
                ),
                AutoTickConfig(
                    description="Snails eat moss",
                    effects=[EffectConfig(operator="decrement", target="moss.biomass", by=1)],
                ),
            ],
        )
        store = StateStore()
        store.add(Entity(id="moss", type="organism", _data={"biomass": 50}))
        store.add(Entity(id="snail", type="organism", _data={"population": 12}))

        tick_engine = TickEngine(config, store, EventLog(), ActionQueue())

        # Run 5 ticks — no agents, no actions, just auto_tick
        for _ in range(5):
            tick_engine.step()

        # moss grows +2, snails eat -1 = net +1 per tick × 5 = 55
        assert store.get("moss")["biomass"] == 55  # type: ignore[union-attr]


# ============================================================
# Scenario 5: Social Network — relationship-based visibility
# ============================================================


class TestSocialScene:
    """Social network: visibility based on 'follows' relationship."""

    def test_follow_creates_relationship(self) -> None:
        config = SceneConfig(
            scene=SceneMetaConfig(id="social", description="Social"),
            entities=[],
            actions={
                "follow": ActionConfig(
                    description="Follow a user",
                    params=[ParamConfig(name="target", type="entity_ref")],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="add_relationship",
                            from_entity="agent",
                            type="follows",
                            to="$target",
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="follow",
                            detail="$agent followed $target",
                            ttl=1,
                            scope="global",
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="alice", type="agent", _data={"handle": "@alice"}))
        store.add(Entity(id="bob", type="agent", _data={"handle": "@bob"}))

        engine = RulesEngine(config, store, EventLog())
        result = engine.process_action(
            ActionSubmission(agent_id="alice", action_type="follow", params={"target": "bob"}),
            tick=1,
        )
        assert result.success
        alice = store.get("alice")
        assert alice is not None
        assert "bob" in alice.get("follows", [])


# ============================================================
# Scenario 6: Hybrid — some entities have location, some don't
# ============================================================


class TestHybridScene:
    """Mixed world: physical + non-physical entities coexist."""

    def test_physical_agent_sees_co_located(self) -> None:
        store = StateStore()
        store.add(Entity(id="merchant", type="agent", _data={"district": "market"}))
        store.add(
            Entity(
                id="stall",
                type="object",
                _data={"district": "market", "goods": "fruit"},
            )
        )
        store.add(Entity(id="temple_ruin", type="object", _data={"district": "ruins"}))

        mgr = InboxManager()
        perception = PerceptionConfig(
            visibility=[
                PreconditionConfig(
                    operator="check",
                    left="$observer.district",
                    op="==",
                    right="$entity.district",
                )
            ],
        )
        p = Perceiver(store, EventLog(), mgr, perception)
        p.deliver(1)

        data = mgr.get_or_create("merchant").read()
        snap = data["current_state"]
        assert "stall" in snap.visible_entities
        assert "temple_ruin" not in snap.visible_entities

    def test_ghost_sees_everything_with_any_rule(self) -> None:
        """Ghost has no 'district' — uses 'any' visibility with fallback."""
        store = StateStore()
        store.add(Entity(id="ghost", type="agent", _data={"essence": 40}))
        store.add(Entity(id="merchant", type="agent", _data={"district": "market"}))
        store.add(Entity(id="artifact", type="object", _data={"district": "ruins"}))

        mgr = InboxManager()
        # Ghost sees everything (empty rules = all visible)
        perception = PerceptionConfig()
        p = Perceiver(store, EventLog(), mgr, perception)
        p.deliver(1)

        data = mgr.get_or_create("ghost").read()
        snap = data["current_state"]
        assert "merchant" in snap.visible_agents
        assert "artifact" in snap.visible_entities

    def test_hybrid_any_visibility(self) -> None:
        """'any' operator: ghost sees all, merchant co-located.

        Tests compound visibility with multiple branches.
        """
        store = StateStore()
        store.add(Entity(id="ghost", type="agent", _data={"essence": 40}))
        store.add(Entity(id="merchant", type="agent", _data={"district": "market"}))
        store.add(Entity(id="stall", type="object", _data={"district": "market"}))
        store.add(Entity(id="ruin", type="object", _data={"district": "ruins"}))
        store.add(Entity(id="curse", type="concept", _data={"potency": 50}))

        mgr = InboxManager()
        # any: ghost sees all (district is null), OR same district, OR concept
        perception = PerceptionConfig(
            visibility=[
                PreconditionConfig(
                    operator="any",
                    conditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$observer.district",
                            op="==",
                            right=None,
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="$observer.district",
                            op="==",
                            right="$entity.district",
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="$entity.type",
                            op="==",
                            right="concept",
                        ),
                    ],
                )
            ],
        )
        p = Perceiver(store, EventLog(), mgr, perception)
        p.deliver(1)

        # Ghost sees everything (first any branch: no district)
        ghost_snap = mgr.get_or_create("ghost").read()["current_state"]
        assert "merchant" in ghost_snap.visible_agents
        assert "stall" in ghost_snap.visible_entities
        assert "ruin" in ghost_snap.visible_entities
        assert "curse" in ghost_snap.visible_entities

        # Merchant sees stall (same district) and curse (concept), not ruin
        merchant_snap = mgr.get_or_create("merchant").read()["current_state"]
        assert "stall" in merchant_snap.visible_entities
        assert "curse" in merchant_snap.visible_entities
        assert "ruin" not in merchant_snap.visible_entities
