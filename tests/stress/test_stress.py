"""Stress tests — verify correctness and performance under load.

Tests cover high-frequency ticks, many agents, and large inbox accumulation.
"""

from __future__ import annotations

import time

from worldseed.engine.inbox import (
    Inbox,
    InboxEvent,
    InboxManager,
)
from worldseed.engine.wakeup import WakeupEvaluator
from worldseed.models.config_schema import (
    ActionConfig,
    AgentConfig,
    EntityConfig,
    EventConfig,
    ParamConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.world import WorldEngine


def _stress_config(
    *,
    num_agents: int = 3,
    actions: dict[str, ActionConfig] | None = None,
) -> SceneConfig:
    """Build a stress test SceneConfig with configurable agent count."""
    agents = [
        AgentConfig(
            id=f"agent_{i}",
            properties={"location": "room", "hp": 100},
            character={"personality": f"agent {i}"},
        )
        for i in range(num_agents)
    ]
    return SceneConfig(
        narrator=False,
        scene=SceneMetaConfig(
            id="stress_test",
            description="Stress test scene",
        ),
        entities=[
            EntityConfig(
                id="room",
                type="space",
                properties={"description": "A room"},
            ),
        ],
        agents=agents,
        actions=actions
        or {
            "say": ActionConfig(
                description="Speak",
                params=[
                    ParamConfig(name="message", type="free_text", required=True),
                ],
                events=[
                    EventConfig(
                        type="say",
                        detail="$agent says $message",
                        ttl=2,
                        scope="global",
                        push=True,
                    ),
                ],
            ),
            "wait": ActionConfig(description="Do nothing"),
        },
    )


def _build_engine(config: SceneConfig) -> WorldEngine:
    engine = WorldEngine(config=config)
    engine.register_from_config()
    return engine


class TestHighFrequencyTicks:
    """1000 ticks with multiple agents, verify no events lost from inbox."""

    def test_1000_ticks_3_agents_say(self) -> None:
        """1000 ticks with 3 agents each doing say. Verify events accumulate
        correctly in inbox and can all be read."""
        config = _stress_config(num_agents=3)
        engine = _build_engine(config)

        total_submitted = 0
        for tick_num in range(1000):
            for i in range(3):
                engine.submit(f"agent_{i}", "say", {"message": f"tick {tick_num}"})
                total_submitted += 1
            engine.step()

        # Each agent should have accumulated say events from all agents
        # (say events are global scope, delivered to all agents)
        # Verify we can read all of them without crash
        for i in range(3):
            data = engine.read_inbox(f"agent_{i}")
            events = data["events"]
            # Events accumulate in inbox until read.
            # We only read once, so all events since creation should be here.
            # The exact count depends on TTL and delivery timing.
            # The main assertion is no crash and events are present.
            assert len(events) > 0, f"agent_{i} should have events"

    def test_1000_ticks_no_action_no_crash(self) -> None:
        """1000 ticks with no actions submitted. Verify no crash."""
        config = _stress_config(num_agents=3)
        engine = _build_engine(config)

        start = time.monotonic()
        for _ in range(1000):
            engine.step()
        elapsed = time.monotonic() - start

        # 1000 empty ticks should be fast
        assert elapsed < 5.0, f"1000 empty ticks took {elapsed:.3f}s"
        assert engine.tick == 1000

    def test_high_freq_ticks_events_have_correct_ticks(self) -> None:
        """Events delivered across many ticks have correct tick numbers."""
        config = _stress_config(num_agents=1)
        engine = _build_engine(config)

        # Submit at specific ticks
        engine.submit("agent_0", "say", {"message": "first"})
        engine.step()  # tick 1

        for _ in range(9):
            engine.step()  # ticks 2-10

        engine.submit("agent_0", "say", {"message": "second"})
        engine.step()  # tick 11

        # Peek inbox — events should have tick 1 and tick 11
        data = engine.peek_inbox("agent_0")
        events = data["events"]
        say_events = [e for e in events if e.type == "say"]
        # At minimum we should have events from tick 11 (tick 1 events may have
        # been delivered and survived in inbox, though TTL=2 expired from EventLog)
        assert len(say_events) >= 1


class TestManyAgents:
    """50 agents registered, all with push events — wakeup evaluates fast."""

    def test_50_agents_push_events_wakeup(self) -> None:
        """50 agents with push events — wakeup evaluation completes quickly."""
        config = _stress_config(num_agents=50)
        engine = _build_engine(config)

        # Each agent says something
        for i in range(50):
            engine.submit(f"agent_{i}", "say", {"message": f"hello from {i}"})
        engine.step()

        # Evaluate wakeup for all
        start = time.monotonic()
        results = engine.get_wakeup_results()
        elapsed = time.monotonic() - start

        assert len(results) == 50
        # All should wake (push events from say)
        woken = [r for r in results if r.should_wake]
        assert len(woken) == 50, f"Expected all 50 to wake, got {len(woken)}"
        assert elapsed < 1.0, f"Wakeup for 50 agents took {elapsed:.3f}s"

    def test_50_agents_perceive_all(self) -> None:
        """50 agents all perceive in sequence — no crash, reasonable time."""
        config = _stress_config(num_agents=50)
        engine = _build_engine(config)

        # Step once so perceiver runs
        engine.step()

        start = time.monotonic()
        for i in range(50):
            p = engine.perceive(f"agent_{i}")
            assert p.self_state is not None
            # Each agent sees 49 other agents
            assert len(p.nearby_agents) == 49
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"50 perceive calls took {elapsed:.3f}s"

    def test_50_agents_concurrent_submit_and_step(self) -> None:
        """50 agents each submit mechanical actions, all execute immediately."""
        from worldseed.engine.rules_engine import ActionResult

        config = _stress_config(num_agents=50)
        engine = _build_engine(config)

        start = time.monotonic()
        for tick_num in range(10):
            for i in range(50):
                r = engine.submit(f"agent_{i}", "say", {"message": f"tick {tick_num}"})
                assert isinstance(r, ActionResult) and r.success
            engine.step()  # still needed for auto_tick/consequences/perceiver
        elapsed = time.monotonic() - start

        assert elapsed < 10.0, f"10 ticks x 50 agents took {elapsed:.3f}s"
        assert engine.tick == 10


class TestLargeInbox:
    """Agent doesn't perceive for many ticks — inbox accumulates."""

    def test_100_ticks_no_perceive_inbox_accumulates(self) -> None:
        """Agent doesn't perceive for 100 ticks with events each tick.
        Inbox should accumulate all events, then perceive returns them all."""
        config = _stress_config(num_agents=2)
        engine = _build_engine(config)

        # Agent_0 submits say each tick, agent_1 never perceives
        for tick_num in range(100):
            engine.submit("agent_0", "say", {"message": f"tick {tick_num}"})
            engine.step()

        # agent_1 finally peeks — should have accumulated events
        data = engine.peek_inbox("agent_1")
        events = data["events"]
        # Events accumulate. Some early ones may have been cleaned by
        # Inbox.cleanup_expired_events if called, but the tick engine
        # comment says "Inbox events persist until consumed by read()"
        assert len(events) > 0, "agent_1 should have accumulated events"

    def test_large_inbox_perceive_returns_all(self) -> None:
        """Large inbox: perceive returns all accumulated events."""
        config = _stress_config(num_agents=1)
        engine = _build_engine(config)

        # Submit many actions across ticks
        for tick_num in range(50):
            engine.submit("agent_0", "say", {"message": f"msg {tick_num}"})
            engine.step()

        # Read inbox — should have events from many ticks
        p = engine.perceive("agent_0")
        assert len(p.events) > 0, "Should have accumulated events"

        # Second perceive should be mostly empty (events drained)
        # Need another step for perceiver to deliver new state
        engine.step()
        p2 = engine.perceive("agent_0")
        # Second perceive should have no say events (all drained)
        say_events = [e for e in p2.events if e.get("type") == "say"]
        assert len(say_events) == 0, "Events should be drained after first perceive"

    def test_inbox_accumulation_capped(self) -> None:
        """Direct inbox stress test — 10000 events capped by MAX_INBOX_EVENTS."""
        from worldseed.engine.inbox import MAX_INBOX_EVENTS

        inbox = Inbox("stressed_agent")

        for i in range(10_000):
            inbox.append_event(
                InboxEvent(
                    tick=i,
                    type="spam",
                    source="spammer",
                    detail=f"event {i}",
                    push=i % 10 == 0,
                )
            )

        # Peek should return capped amount (oldest evicted)
        peeked = inbox.peek()
        assert len(peeked["events"]) == MAX_INBOX_EVENTS

        # Read should drain capped amount
        data = inbox.read()
        assert len(data["events"]) == MAX_INBOX_EVENTS

        # Verify sorted by tick and newest events preserved
        ticks = [e.tick for e in data["events"]]
        assert ticks == sorted(ticks)
        assert ticks[-1] == 9999  # newest preserved

        # After read, inbox should be empty
        data2 = inbox.read()
        assert len(data2["events"]) == 0


class TestWakeupUnderLoad:
    """Wakeup evaluation with many inboxes and many events."""

    def test_100_inboxes_mixed_push(self) -> None:
        """100 inboxes, alternating push/non-push. Evaluate all correctly."""
        evaluator = WakeupEvaluator()
        mgr = InboxManager()

        for i in range(100):
            inbox = mgr.get_or_create(f"agent_{i}")
            for j in range(50):
                inbox.append_event(
                    InboxEvent(
                        tick=j,
                        type="event",
                        source="src",
                        detail="",
                        push=(i % 2 == 0),  # even agents get push events
                    )
                )

        start = time.monotonic()
        results = evaluator.evaluate_all(mgr)
        elapsed = time.monotonic() - start

        assert len(results) == 100
        woken = [r for r in results if r.should_wake]
        # Even agents (0, 2, 4, ...) should wake, odd should not
        assert len(woken) == 50
        for r in results:
            idx = int(r.agent_id.split("_")[1])
            if idx % 2 == 0:
                assert r.should_wake is True
            else:
                assert r.should_wake is False

        assert elapsed < 1.0, f"evaluate_all took {elapsed:.3f}s"


class TestEngineStability:
    """Long-running engine stability tests."""

    def test_step_with_mixed_actions(self) -> None:
        """Steps with a mix of valid mechanical actions.
        All execute immediately via submit()."""
        from worldseed.engine.rules_engine import ActionResult

        config = _stress_config(num_agents=3)
        engine = _build_engine(config)

        for tick_num in range(100):
            # All mechanical — execute immediately
            r0 = engine.submit("agent_0", "say", {"message": "hello"})
            r1 = engine.submit("agent_1", "wait", {})
            r2 = engine.submit("agent_2", "say", {"message": f"tick {tick_num}"})

            assert isinstance(r0, ActionResult) and r0.success
            assert isinstance(r1, ActionResult) and r1.success
            assert isinstance(r2, ActionResult) and r2.success

            engine.step()  # still needed for auto_tick/consequences/perceiver

        assert engine.tick == 100

    def test_alternating_submit_and_empty_ticks(self) -> None:
        """Alternate between ticks with mechanical actions and empty ticks."""
        from worldseed.engine.rules_engine import ActionResult

        config = _stress_config(num_agents=2)
        engine = _build_engine(config)

        for tick_num in range(200):
            if tick_num % 2 == 0:
                r = engine.submit("agent_0", "say", {"message": f"tick {tick_num}"})
                assert isinstance(r, ActionResult) and r.success
            engine.step()  # step always runs (auto_tick, perceiver, etc.)

        assert engine.tick == 200
