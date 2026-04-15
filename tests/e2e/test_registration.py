"""Stress tests for the registration system.

Tests /register (claim + create modes), /characters, /perceive, /act
with agent_id mode, and edge cases around agent_id validation.

Builds a minimal SceneConfig in Python (no YAML) with templates + presets.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from worldseed.models.config_schema import (
    ActionConfig,
    AgentConfig,
    EffectConfig,
    EventConfig,
    ParamConfig,
    PerceptionConfig,
    SceneConfig,
    SceneMetaConfig,
    TemplateConfig,
)
from worldseed.server.app import create_app
from worldseed.world import WorldEngine

# ---------------------------------------------------------------------------
# Minimal SceneConfig built in Python — no YAML required
# ---------------------------------------------------------------------------


def _make_config() -> SceneConfig:
    """Build a self-contained scene config with templates and presets."""
    return SceneConfig(
        scene=SceneMetaConfig(
            id="test_scene",
            description="Minimal test scene for registration stress tests",
            tick_interval=1.0,
            default_spawn={"location": "lobby", "hp": 100},
        ),
        entities=[],  # no world entities needed
        templates={
            "soldier": TemplateConfig(
                properties={"location": "barracks", "hp": 120, "role": "fighter"},
            ),
            "medic": TemplateConfig(
                properties={"location": "infirmary", "hp": 80, "role": "healer"},
            ),
        },
        agents=[
            AgentConfig(
                id="alice",
                template="soldier",
                properties={"hp": 150},  # overrides template hp
                character={"name": "Alice", "personality": "brave"},
            ),
            AgentConfig(
                id="bob",
                template="medic",
                character={"name": "Bob", "personality": "kind"},
            ),
            AgentConfig(
                id="charlie",
                # no template
                properties={"location": "gate", "hp": 90},
                character={"name": "Charlie", "personality": "cautious"},
            ),
        ],
        actions={
            "say": ActionConfig(
                description="Say something",
                params=[
                    ParamConfig(name="message", type="free_text"),
                ],
                effects=[],
                events=[
                    EventConfig(
                        type="speech",
                        detail="$agent says: $message",
                        ttl=3,
                        scope="global",
                    ),
                ],
            ),
            "move": ActionConfig(
                description="Move to a location",
                params=[
                    ParamConfig(name="to", type="string"),
                ],
                effects=[
                    EffectConfig(
                        operator="set",
                        target="$agent.location",
                        value="$to",
                    ),
                ],
                events=[],
            ),
        },
        perception=PerceptionConfig(),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine() -> WorldEngine:
    """WorldEngine with the minimal config, no agents pre-registered."""
    return WorldEngine(config=_make_config())


@pytest.fixture()
def client(engine: WorldEngine) -> TestClient:
    """TestClient with no agents pre-registered."""
    app = create_app(engine, tick_interval=1.0)
    return TestClient(app)


@pytest.fixture()
def registered_client() -> TestClient:
    """TestClient with all preset agents pre-registered."""
    eng = WorldEngine(config=_make_config())
    eng.register_from_config()
    app = create_app(eng, tick_interval=1.0)
    return TestClient(app)


# ===================================================================
# CLAIM MODE
# ===================================================================


class TestClaimMode:
    """POST /register with mode=claim."""

    def test_claim_preset_returns_200_and_character_card(self, client: TestClient) -> None:
        resp = client.post("/register", json={"mode": "claim", "agent_id": "alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "alice"
        assert data["scene"] == "test_scene"
        assert "token" in data
        assert data["character"]["name"] == "Alice"
        assert data["character"]["personality"] == "brave"

    def test_claim_nonexistent_preset_returns_404(self, client: TestClient) -> None:
        resp = client.post("/register", json={"mode": "claim", "agent_id": "ghost"})
        assert resp.status_code == 404
        assert "ghost" in resp.json()["detail"]

    def test_claim_same_preset_twice_reconnect_returns_200(self, client: TestClient) -> None:
        r1 = client.post("/register", json={"mode": "claim", "agent_id": "alice"})
        assert r1.status_code == 200
        token1 = r1.json()["token"]
        char1 = r1.json()["character"]

        # Reconnect — should succeed with a NEW token but same character
        r2 = client.post("/register", json={"mode": "claim", "agent_id": "alice"})
        assert r2.status_code == 200
        token2 = r2.json()["token"]
        char2 = r2.json()["character"]

        assert char1 == char2, "Character card should be identical on reconnect"
        assert token1 != token2, "New token should be issued on reconnect"

    def test_claim_reconnect_old_token_revoked(self, client: TestClient) -> None:
        r1 = client.post("/register", json={"mode": "claim", "agent_id": "alice"})
        token1 = r1.json()["token"]

        # Reconnect — old token should be revoked
        r2 = client.post("/register", json={"mode": "claim", "agent_id": "alice"})
        token2 = r2.json()["token"]

        # Old token should fail
        resp = client.get("/perceive", params={"token": token1})
        assert resp.status_code == 401

        # New token should work
        engine = client.app.state.engine  # type: ignore[union-attr]
        engine.step()
        resp = client.get("/perceive", params={"token": token2})
        assert resp.status_code == 200

    def test_claim_with_wrong_mode_returns_400(self, client: TestClient) -> None:
        resp = client.post("/register", json={"mode": "summon", "agent_id": "alice"})
        assert resp.status_code == 422  # Pydantic validation: Literal mismatch

    def test_claim_all_presets(self, client: TestClient) -> None:
        for agent_id in ("alice", "bob", "charlie"):
            resp = client.post("/register", json={"mode": "claim", "agent_id": agent_id})
            assert resp.status_code == 200
            assert resp.json()["agent_id"] == agent_id

    def test_claim_preset_gets_merged_template_properties(self, client: TestClient) -> None:
        """Alice has template=soldier (hp=120, location=barracks, role=fighter)
        but overrides hp=150. Final entity should have hp=150, location=barracks,
        role=fighter."""
        client.post("/register", json={"mode": "claim", "agent_id": "alice"})
        engine = client.app.state.engine  # type: ignore[union-attr]
        entity = engine.state.get("alice")
        assert entity is not None
        assert entity["hp"] == 150  # overridden
        assert entity["location"] == "barracks"  # from template
        assert entity["role"] == "fighter"  # from template

    def test_claim_preset_without_template(self, client: TestClient) -> None:
        """Charlie has no template, just direct properties."""
        client.post("/register", json={"mode": "claim", "agent_id": "charlie"})
        engine = client.app.state.engine  # type: ignore[union-attr]
        entity = engine.state.get("charlie")
        assert entity is not None
        assert entity["location"] == "gate"
        assert entity["hp"] == 90


# ===================================================================
# CREATE MODE
# ===================================================================


class TestCreateMode:
    """POST /register with mode=create."""

    def test_create_new_agent_returns_200(self, client: TestClient) -> None:
        resp = client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "newcomer",
                "character": {"name": "Newcomer", "style": "aggressive"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "newcomer"
        assert data["character"]["name"] == "Newcomer"
        assert "token" in data

    def test_create_gets_default_spawn_properties(self, client: TestClient) -> None:
        """Created agent with no template gets default_spawn props."""
        client.post(
            "/register",
            json={"mode": "create", "agent_id": "newcomer"},
        )
        engine = client.app.state.engine  # type: ignore[union-attr]
        entity = engine.state.get("newcomer")
        assert entity is not None
        assert entity["location"] == "lobby"
        assert entity["hp"] == 100

    def test_create_with_template_returns_200_and_gets_template_props(self, client: TestClient) -> None:
        resp = client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "recruit",
                "template": "soldier",
                "character": {"name": "Recruit"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "recruit"

        engine = client.app.state.engine  # type: ignore[union-attr]
        entity = engine.state.get("recruit")
        assert entity is not None
        # Template properties should be present
        assert entity["role"] == "fighter"
        assert entity["hp"] == 120
        assert entity["location"] == "barracks"

    def test_create_with_template_merges_default_spawn(self, client: TestClient) -> None:
        """Template props override default_spawn, but missing keys from
        default_spawn fill in."""
        # medic template has: location=infirmary, hp=80, role=healer
        # default_spawn has: location=lobby, hp=100
        # Result: location=infirmary (template wins), hp=80 (template wins),
        #         role=healer (template only)
        client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "field_medic",
                "template": "medic",
            },
        )
        engine = client.app.state.engine  # type: ignore[union-attr]
        entity = engine.state.get("field_medic")
        assert entity is not None
        assert entity["location"] == "infirmary"
        assert entity["hp"] == 80
        assert entity["role"] == "healer"

    def test_create_with_nonexistent_template_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "lost",
                "template": "wizard",
            },
        )
        assert resp.status_code == 404
        assert "wizard" in resp.json()["detail"]

    def test_create_with_agent_id_matching_preset_returns_409(self, client: TestClient) -> None:
        resp = client.post("/register", json={"mode": "create", "agent_id": "alice"})
        assert resp.status_code == 409
        assert "alice" in resp.json()["detail"]

    def test_create_same_agent_twice_reconnect_returns_200(self, client: TestClient) -> None:
        r1 = client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "returner",
                "character": {"name": "Returner"},
            },
        )
        assert r1.status_code == 200
        token1 = r1.json()["token"]

        r2 = client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "returner",
                "character": {"name": "Returner"},
            },
        )
        assert r2.status_code == 200
        token2 = r2.json()["token"]
        assert token1 != token2, "New token should be issued on reconnect"

    def test_create_reconnect_returns_original_character(self, client: TestClient) -> None:
        """On reconnect, character card from profile should be returned,
        not the one in the new request."""
        client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "returner",
                "character": {"name": "Returner", "trait": "brave"},
            },
        )
        r2 = client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "returner",
                "character": {"name": "Impostor", "trait": "sneaky"},
            },
        )
        assert r2.status_code == 200
        # Should return profile character, not request character
        char = r2.json()["character"]
        assert char["name"] == "Returner"
        assert char["trait"] == "brave"

    def test_create_multiple_custom_agents(self, client: TestClient) -> None:
        tokens = []
        for i in range(5):
            resp = client.post(
                "/register",
                json={
                    "mode": "create",
                    "agent_id": f"agent_{i}",
                    "character": {"name": f"Agent {i}"},
                },
            )
            assert resp.status_code == 200
            tokens.append(resp.json()["token"])

        # All tokens should be unique
        assert len(set(tokens)) == 5


# ===================================================================
# CHARACTERS ENDPOINT
# ===================================================================


class TestCharactersEndpoint:
    """GET /characters."""

    def test_returns_all_presets(self, client: TestClient) -> None:
        resp = client.get("/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        ids = {c["id"] for c in data}
        assert ids == {"alice", "bob", "charlie"}

    def test_all_unclaimed_initially(self, client: TestClient) -> None:
        data = client.get("/characters").json()
        for c in data:
            assert c["claimed"] is False

    def test_after_claim_shows_claimed_true(self, client: TestClient) -> None:
        client.post("/register", json={"mode": "claim", "agent_id": "alice"})
        data = client.get("/characters").json()
        alice = next(c for c in data if c["id"] == "alice")
        assert alice["claimed"] is True

    def test_unclaimed_still_false_after_partial_claim(self, client: TestClient) -> None:
        client.post("/register", json={"mode": "claim", "agent_id": "alice"})
        data = client.get("/characters").json()
        bob = next(c for c in data if c["id"] == "bob")
        assert bob["claimed"] is False
        charlie = next(c for c in data if c["id"] == "charlie")
        assert charlie["claimed"] is False

    def test_all_claimed_after_claiming_all(self, client: TestClient) -> None:
        for agent_id in ("alice", "bob", "charlie"):
            client.post("/register", json={"mode": "claim", "agent_id": agent_id})
        data = client.get("/characters").json()
        assert all(c["claimed"] for c in data)

    def test_characters_has_character_card(self, client: TestClient) -> None:
        data = client.get("/characters").json()
        alice = next(c for c in data if c["id"] == "alice")
        assert alice["character"]["name"] == "Alice"

    def test_created_agents_appear_in_characters(self, client: TestClient) -> None:
        """Dynamically created agents should appear in /characters."""
        client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "custom_one",
                "character": {"name": "Custom"},
            },
        )
        data = client.get("/characters").json()
        ids = {c["id"] for c in data}
        assert "custom_one" in ids
        custom = next(c for c in data if c["id"] == "custom_one")
        assert custom["character"]["name"] == "Custom"
        assert custom["claimed"] is True


# ===================================================================
# AGENT_ID MODE (no token)
# ===================================================================


class TestAgentIdMode:
    """Endpoints accessed via agent_id query param instead of token."""

    def test_perceive_with_agent_id_works(self, registered_client: TestClient) -> None:
        engine = registered_client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        resp = registered_client.get("/perceive", params={"agent_id": "alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert "tick" in data
        assert "self_state" in data
        assert "events" in data
        assert "action_options" in data

    def test_perceive_with_unknown_agent_id_404(self, registered_client: TestClient) -> None:
        resp = registered_client.get("/perceive", params={"agent_id": "unknown_phantom"})
        assert resp.status_code == 404

    def test_perceive_no_params_returns_400(self, registered_client: TestClient) -> None:
        resp = registered_client.get("/perceive")
        assert resp.status_code == 400

    def test_act_with_agent_id_in_body_works(self, registered_client: TestClient) -> None:
        resp = registered_client.post(
            "/act",
            json={
                "agent_id": "alice",
                "action": "say",
                "params": {"message": "hello world"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["queued"] is True

    def test_act_with_think_interval_updates_interval(self, registered_client: TestClient) -> None:
        registered_client.post(
            "/act",
            json={
                "agent_id": "alice",
                "action": "say",
                "params": {"message": "test"},
                "think_interval": 10,
            },
        )
        engine = registered_client.app.state.engine  # type: ignore[union-attr]
        assert engine.get_think_interval("alice") == 10

    def test_act_step_perceive_cycle_with_agent_id(self, registered_client: TestClient) -> None:
        """Full cycle using agent_id only (no tokens).

        Move is mechanical — executes immediately via submit().
        step() still needed for perceiver delivery.
        """
        resp = registered_client.post(
            "/act",
            json={
                "agent_id": "alice",
                "action": "move",
                "params": {"to": "corridor"},
            },
        )
        assert resp.status_code == 200

        engine = registered_client.app.state.engine  # type: ignore[union-attr]
        # Mechanical action already executed; verify via state
        assert engine.state.get("alice")["location"] == "corridor"  # type: ignore[index]
        engine.step()  # needed for perceiver delivery

        data = registered_client.get("/perceive", params={"agent_id": "alice"}).json()
        assert data["self_state"]["location"] == "corridor"


# ===================================================================
# TOKEN AUTHENTICATION
# ===================================================================


class TestTokenAuth:
    """Token management across register/perceive/act."""

    def test_token_works_for_perceive(self, client: TestClient) -> None:
        token = client.post("/register", json={"mode": "claim", "agent_id": "alice"}).json()["token"]
        engine = client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        resp = client.get("/perceive", params={"token": token})
        assert resp.status_code == 200

    def test_token_works_for_act(self, client: TestClient) -> None:
        token = client.post("/register", json={"mode": "claim", "agent_id": "alice"}).json()["token"]

        resp = client.post(
            "/act",
            json={
                "token": token,
                "action": "say",
                "params": {"message": "hi"},
            },
        )
        assert resp.status_code == 200

    def test_invalid_token_perceive_401(self, client: TestClient) -> None:
        resp = client.get("/perceive", params={"token": "totally_bogus"})
        assert resp.status_code == 401

    def test_invalid_token_act_401(self, client: TestClient) -> None:
        resp = client.post(
            "/act",
            json={
                "token": "totally_bogus",
                "action": "say",
                "params": {"message": "hi"},
            },
        )
        assert resp.status_code == 401

    def test_different_agents_get_different_tokens(self, client: TestClient) -> None:
        t1 = client.post("/register", json={"mode": "claim", "agent_id": "alice"}).json()["token"]
        t2 = client.post("/register", json={"mode": "claim", "agent_id": "bob"}).json()["token"]
        assert t1 != t2

    def test_create_token_works_same_as_claim_token(self, client: TestClient) -> None:
        token = client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "custom_agent",
                "character": {"name": "Custom"},
            },
        ).json()["token"]

        engine = client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        resp = client.get("/perceive", params={"token": token})
        assert resp.status_code == 200

        resp = client.post(
            "/act",
            json={
                "token": token,
                "action": "say",
                "params": {"message": "created!"},
            },
        )
        assert resp.status_code == 200


# ===================================================================
# EDGE CASES
# ===================================================================


class TestEdgeCases:
    """Boundary conditions, unusual inputs, error handling."""

    def test_empty_agent_id_claim_error(self, client: TestClient) -> None:
        resp = client.post("/register", json={"mode": "claim", "agent_id": ""})
        # Empty string won't match any preset
        assert resp.status_code == 404

    def test_empty_agent_id_create_gets_200_or_error(self, client: TestClient) -> None:
        """Empty agent_id in create mode: could work (engine allows it)
        or could error. Either way it should not crash."""
        resp = client.post("/register", json={"mode": "create", "agent_id": ""})
        # Should not be 500
        assert resp.status_code != 500

    def test_very_long_agent_id_create(self, client: TestClient) -> None:
        long_id = "a" * 500
        resp = client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": long_id,
                "character": {"name": "Long ID"},
            },
        )
        # Should work or give a proper error, not 500
        assert resp.status_code != 500
        if resp.status_code == 200:
            assert resp.json()["agent_id"] == long_id

    def test_very_long_agent_id_claim_404(self, client: TestClient) -> None:
        long_id = "x" * 1000
        resp = client.post("/register", json={"mode": "claim", "agent_id": long_id})
        assert resp.status_code == 404

    def test_special_characters_in_agent_id(self, client: TestClient) -> None:
        """Agent IDs with special characters should work or fail gracefully."""
        special_ids = [
            "agent-with-dashes",
            "agent_with_underscores",
            "agent.with.dots",
            "agent@domain",
            "agent 123",  # space
            "agent/slash",
        ]
        for sid in special_ids:
            resp = client.post(
                "/register",
                json={
                    "mode": "create",
                    "agent_id": sid,
                    "character": {"name": sid},
                },
            )
            # Must not crash
            assert resp.status_code != 500, f"500 on agent_id={sid!r}"

    def test_unicode_agent_id(self, client: TestClient) -> None:
        resp = client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "\u5c0f\u660e",
                "character": {"name": "\u5c0f\u660e"},
            },
        )
        assert resp.status_code != 500
        if resp.status_code == 200:
            assert resp.json()["agent_id"] == "\u5c0f\u660e"

    def test_missing_agent_id_field_422(self, client: TestClient) -> None:
        """Request body missing agent_id entirely."""
        resp = client.post("/register", json={"mode": "claim"})
        assert resp.status_code == 422  # Pydantic validation error

    def test_missing_mode_field_422(self, client: TestClient) -> None:
        """Request body missing mode entirely."""
        resp = client.post("/register", json={"agent_id": "alice"})
        assert resp.status_code == 422

    def test_act_no_token_no_agent_id_400(self, client: TestClient) -> None:
        resp = client.post(
            "/act",
            json={"action": "say", "params": {"message": "hello"}},
        )
        assert resp.status_code == 400

    def test_claim_then_create_same_id_409(self, client: TestClient) -> None:
        """After claiming a preset, trying to create with that ID fails."""
        client.post("/register", json={"mode": "claim", "agent_id": "alice"})
        resp = client.post("/register", json={"mode": "create", "agent_id": "alice"})
        assert resp.status_code == 409


# ===================================================================
# STRESS / CONCURRENCY PATTERNS
# ===================================================================


class TestStressPatterns:
    """Stress-style tests — bulk operations, rapid re-registration, etc."""

    def test_rapid_claim_reconnect_10_times(self, client: TestClient) -> None:
        """Rapidly re-claim same preset 10 times. Should always work."""
        tokens = []
        for _ in range(10):
            resp = client.post("/register", json={"mode": "claim", "agent_id": "alice"})
            assert resp.status_code == 200
            tokens.append(resp.json()["token"])

        # All tokens should be unique
        assert len(set(tokens)) == 10

        # Only the last token should be valid
        engine = client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        for old_token in tokens[:-1]:
            resp = client.get("/perceive", params={"token": old_token})
            assert resp.status_code == 401

        resp = client.get("/perceive", params={"token": tokens[-1]})
        assert resp.status_code == 200

    def test_create_many_agents(self, client: TestClient) -> None:
        """Create 20 agents in a row. All should register successfully."""
        for i in range(20):
            resp = client.post(
                "/register",
                json={
                    "mode": "create",
                    "agent_id": f"bot_{i:03d}",
                    "character": {"name": f"Bot {i}"},
                },
            )
            assert resp.status_code == 200

        # All should be queryable via perceive
        engine = client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        for i in range(20):
            resp = client.get("/perceive", params={"agent_id": f"bot_{i:03d}"})
            assert resp.status_code == 200

    def test_interleave_claim_and_create(self, client: TestClient) -> None:
        """Mix claim and create operations."""
        # Claim a preset
        r1 = client.post("/register", json={"mode": "claim", "agent_id": "alice"})
        assert r1.status_code == 200

        # Create a custom
        r2 = client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "custom_1",
                "template": "soldier",
            },
        )
        assert r2.status_code == 200

        # Claim another preset
        r3 = client.post("/register", json={"mode": "claim", "agent_id": "bob"})
        assert r3.status_code == 200

        # Create another custom
        r4 = client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "custom_2",
                "template": "medic",
            },
        )
        assert r4.status_code == 200

        # All should be usable
        engine = client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        for aid in ("alice", "bob", "custom_1", "custom_2"):
            resp = client.get("/perceive", params={"agent_id": aid})
            assert resp.status_code == 200, f"Failed for {aid}"

    def test_act_and_perceive_across_multiple_agents(self, client: TestClient) -> None:
        """Multiple agents act, then all perceive."""
        # Register several agents
        for aid in ("alice", "bob", "charlie"):
            client.post("/register", json={"mode": "claim", "agent_id": aid})

        # All agents say something
        for aid in ("alice", "bob", "charlie"):
            client.post(
                "/act",
                json={
                    "agent_id": aid,
                    "action": "say",
                    "params": {"message": f"Hello from {aid}"},
                },
            )

        engine = client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        # All agents should be able to perceive
        for aid in ("alice", "bob", "charlie"):
            resp = client.get("/perceive", params={"agent_id": aid})
            assert resp.status_code == 200

    def test_register_then_act_then_register_again(self, client: TestClient) -> None:
        """Register, act, then re-register. Action should still process."""
        token1 = client.post("/register", json={"mode": "claim", "agent_id": "alice"}).json()["token"]

        client.post(
            "/act",
            json={
                "token": token1,
                "action": "move",
                "params": {"to": "rooftop"},
            },
        )

        engine = client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        # Re-register (reconnect)
        token2 = client.post("/register", json={"mode": "claim", "agent_id": "alice"}).json()["token"]

        # Perceive with new token — should see the moved state
        data = client.get("/perceive", params={"token": token2}).json()
        assert data["self_state"]["location"] == "rooftop"
