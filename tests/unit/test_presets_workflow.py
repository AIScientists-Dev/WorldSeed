"""Tests for artifact_workflow and competitive presets."""

from __future__ import annotations

import pytest

from worldseed.scene.config import load_config
from worldseed.world import WorldEngine


@pytest.fixture()
def pitch_engine() -> WorldEngine:
    """Load the pitch_contest config and return a WorldEngine."""
    from worldseed.dm.providers.mock import MockDMProvider

    cfg = load_config("configs/pitch_contest.yaml")
    engine = WorldEngine(config=cfg, dm_provider=MockDMProvider())
    engine.register_from_config()
    return engine


class TestPresetLoading:
    """Verify presets are merged correctly."""

    def test_artifact_workflow_actions_loaded(self, pitch_engine: WorldEngine) -> None:
        actions = pitch_engine.config.actions
        assert "submit_work" in actions
        assert "review_work" in actions
        assert "revise_work" in actions

    def test_competitive_actions_loaded(self, pitch_engine: WorldEngine) -> None:
        actions = pitch_engine.config.actions
        assert "submit_entry" in actions
        assert "judge_entry" in actions

    def test_talk_and_attempt_loaded(self, pitch_engine: WorldEngine) -> None:
        actions = pitch_engine.config.actions
        assert "talk" in actions
        assert "attempt" in actions

    def test_timer_entity_loaded(self, pitch_engine: WorldEngine) -> None:
        timer = pitch_engine.state.get("timer")
        assert timer is not None
        assert timer.get("remaining") == 20

    def test_agents_registered(self, pitch_engine: WorldEngine) -> None:
        all_entities = pitch_engine.state.all_entities()
        agent_ids = {e.id for e in all_entities if e.type == "agent"}
        assert agent_ids == {"founder_a", "founder_b", "founder_c", "investor", "narrator"}


class TestSubmitWork:
    """Test the artifact_workflow submit_work action."""

    def test_submit_creates_artifact(self, pitch_engine: WorldEngine) -> None:
        result = pitch_engine.submit(
            agent_id="founder_a",
            action_type="submit_work",
            params={
                "title": "AI Code Review Tool",
                "content": "We use LLMs to review PRs automatically...",
            },
        )
        assert result is not None
        assert result.success

        # Find the created artifact
        artifacts = [e for e in pitch_engine.state.all_entities() if e.type == "artifact"]
        assert len(artifacts) == 1
        art = artifacts[0]
        assert art.get("title") == "AI Code Review Tool"
        assert art.get("author") == "founder_a"
        assert art.get("status") == "submitted"

    def test_review_nonexistent_artifact_fails_at_step(self, pitch_engine: WorldEngine) -> None:
        # DM action is queued even with bad entity ref. Fails at step time.
        pitch_engine.submit(
            agent_id="investor",
            action_type="review_work",
            params={"artifact": "nonexistent"},
        )
        # Step processes — precondition should fail (nonexistent entity)
        pitch_engine.step()
        # No artifacts should exist (nothing was reviewed)
        artifacts = [e for e in pitch_engine.state.all_entities() if e.type == "artifact"]
        assert len(artifacts) == 0

    def test_cannot_review_own_work(self, pitch_engine: WorldEngine) -> None:
        # Submit first
        pitch_engine.submit(
            agent_id="founder_a",
            action_type="submit_work",
            params={"title": "My Pitch", "content": "Great idea..."},
        )
        artifacts = [e for e in pitch_engine.state.all_entities() if e.type == "artifact"]
        art_id = artifacts[0].id

        # Author tries to review own work — DM action is queued
        pitch_engine.submit(
            agent_id="founder_a",
            action_type="review_work",
            params={"artifact": art_id},
        )
        # Step processes the queue — precondition should fail
        pitch_engine.step()
        # Artifact status should still be "submitted" (review didn't happen)
        art = pitch_engine.state.get(art_id)
        assert art.get("status") == "submitted"


class TestSubmitEntry:
    """Test the competitive submit_entry action."""

    def test_submit_creates_entry(self, pitch_engine: WorldEngine) -> None:
        result = pitch_engine.submit(
            agent_id="founder_b",
            action_type="submit_entry",
            params={
                "title": "VibeCheck — AI Mood Ring for Teams",
                "content": "A consumer app that reads team vibes...",
            },
        )
        assert result is not None
        assert result.success

        entries = [e for e in pitch_engine.state.all_entities() if e.type == "entry"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry.get("author") == "founder_b"
        assert entry.get("status") == "submitted"
        assert entry.get("score") == 0

    def test_cannot_judge_own_entry(self, pitch_engine: WorldEngine) -> None:
        pitch_engine.submit(
            agent_id="founder_b",
            action_type="submit_entry",
            params={"title": "My App", "content": "..."},
        )
        entries = [e for e in pitch_engine.state.all_entities() if e.type == "entry"]
        entry_id = entries[0].id

        # Judge own entry — DM action is queued
        pitch_engine.submit(
            agent_id="founder_b",
            action_type="judge_entry",
            params={"entry": entry_id},
        )
        # Step processes — precondition (author != agent) should fail
        pitch_engine.step()
        # Entry should still be "submitted" (not judged)
        entry = pitch_engine.state.get(entry_id)
        assert entry.get("status") == "submitted"


class TestReviseWork:
    """Test the revision cycle."""

    def test_revise_resubmits_artifact(self, pitch_engine: WorldEngine) -> None:
        # Submit
        pitch_engine.submit(
            agent_id="founder_c",
            action_type="submit_work",
            params={"title": "HR AI", "content": "First draft..."},
        )
        artifacts = [e for e in pitch_engine.state.all_entities() if e.type == "artifact"]
        art_id = artifacts[0].id

        # Manually set status to needs_revision (simulating DM review)
        pitch_engine.state.update_property(art_id, "status", "needs_revision")

        # Revise
        result = pitch_engine.submit(
            agent_id="founder_c",
            action_type="revise_work",
            params={
                "artifact": art_id,
                "content": "Revised draft with more data...",
            },
        )
        assert result is not None
        assert result.success

        art = pitch_engine.state.get(art_id)
        assert art.get("content") == "Revised draft with more data..."
        assert art.get("status") == "submitted"

    def test_cannot_revise_approved_artifact(self, pitch_engine: WorldEngine) -> None:
        pitch_engine.submit(
            agent_id="founder_a",
            action_type="submit_work",
            params={"title": "Pitch", "content": "..."},
        )
        artifacts = [e for e in pitch_engine.state.all_entities() if e.type == "artifact"]
        art_id = artifacts[0].id

        # Set to approved
        pitch_engine.state.update_property(art_id, "status", "approved")

        result = pitch_engine.submit(
            agent_id="founder_a",
            action_type="revise_work",
            params={"artifact": art_id, "content": "Trying to revise..."},
        )
        assert result is not None
        assert not result.success


class TestTimerIntegration:
    """Test timer countdown works with presets."""

    def test_timer_decrements(self, pitch_engine: WorldEngine) -> None:
        initial = pitch_engine.state.get("timer").get("remaining")
        pitch_engine.step()
        after = pitch_engine.state.get("timer").get("remaining")
        assert after == initial - 1
