"""Creative scenario tests — push engine capabilities beyond spatial movement.

Each test validates a fundamentally different engine capability:
1. Spell Cooldowns: tick-based timestamps, mana economy, win/loss consequences
2. Stock Market: value transfer, arithmetic in effects, economic auto_tick cycles
3. Metamorphosis: state machine transitions via consequences, zero-agent worlds
4. Virus Network: self-modifying topology via add/remove_relationship,
   relationship-gated perception
5. Reputation Cascade: reputation as action gate, dynamic relationship creation,
   cascade effects
"""

from __future__ import annotations

from worldseed.engine.action_queue import ActionQueue
from worldseed.engine.consequence_scanner import ConsequenceScanner
from worldseed.engine.event_log import EventLog
from worldseed.engine.rules_engine import RulesEngine
from worldseed.engine.state_store import StateStore
from worldseed.engine.tick import TickEngine
from worldseed.models import ActionSubmission, Entity
from worldseed.models.config_schema import (
    ActionConfig,
    AutoTickConfig,
    ConsequenceConfig,
    EffectConfig,
    EventConfig,
    ParamConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)

# ============================================================
# Scenario 1: Wizard Duel — TICK-BASED COOLDOWNS
# ============================================================


class TestSpellCooldowns:
    """Wizard duel: mana economy, damage, and win/loss detection."""

    def _build(self) -> tuple[SceneConfig, StateStore, EventLog]:
        config = SceneConfig(
            scene=SceneMetaConfig(id="duel", description="Wizard duel"),
            entities=[],
            actions={
                "fireball": ActionConfig(
                    description="25 damage, costs 20 mana",
                    params=[ParamConfig(name="target", type="entity_ref")],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$agent.mana",
                            op=">=",
                            right=20,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="$agent.mana",
                            by=20,
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="$target.hp",
                            by=25,
                        ),
                        EffectConfig(
                            operator="set",
                            target="$agent.last_fireball_tick",
                            value="$tick",
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="spell",
                            detail="$agent cast fireball at $target",
                            ttl=3,
                            scope="global",
                        ),
                    ],
                ),
                "shield": ActionConfig(
                    description="Raise shield, costs 10 mana",
                    params=[],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$agent.mana",
                            op=">=",
                            right=10,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="$agent.mana",
                            by=10,
                        ),
                        EffectConfig(
                            operator="set",
                            target="$agent.shield",
                            value=15,
                        ),
                    ],
                ),
            },
            consequences={
                "wizard_defeated": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="pyra.hp",
                            op="<=",
                            right=0,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="arena.winner",
                            value="glacius",
                        ),
                    ],
                ),
            },
            auto_tick=[
                AutoTickConfig(
                    description="Mana regen",
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="pyra.mana",
                            by=3,
                        ),
                        EffectConfig(
                            operator="increment",
                            target="glacius.mana",
                            by=3,
                        ),
                    ],
                ),
            ],
        )
        store = StateStore()
        store.add(Entity(id="arena", type="duel", _data={"winner": "none"}))
        store.add(
            Entity(
                id="pyra",
                type="agent",
                _data={
                    "hp": 100,
                    "mana": 50,
                    "shield": 0,
                    "last_fireball_tick": -100,
                },
            )
        )
        store.add(
            Entity(
                id="glacius",
                type="agent",
                _data={
                    "hp": 100,
                    "mana": 50,
                    "shield": 0,
                    "last_fireball_tick": -100,
                },
            )
        )
        return config, store, EventLog()

    def test_fireball_deals_damage_and_costs_mana(self) -> None:
        """Fireball: target loses 25 HP, caster loses 20 mana."""
        config, store, event_log = self._build()
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(
                agent_id="pyra",
                action_type="fireball",
                params={"target": "glacius"},
            ),
            tick=1,
        )
        assert result.success
        assert store.get("glacius")["hp"] == 75  # type: ignore[union-attr]
        assert store.get("pyra")["mana"] == 30  # type: ignore[union-attr]

    def test_insufficient_mana_blocks_fireball(self) -> None:
        """Can't cast fireball with less than 20 mana."""
        config, store, event_log = self._build()
        store.update_property("pyra", "mana", 10)
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(
                agent_id="pyra",
                action_type="fireball",
                params={"target": "glacius"},
            ),
            tick=1,
        )
        assert not result.success
        assert store.get("glacius")["hp"] == 100  # type: ignore[union-attr]

    def test_tick_stored_on_cast(self) -> None:
        """Casting stores the tick number for cooldown tracking."""
        config, store, event_log = self._build()
        engine = RulesEngine(config, store, event_log)

        engine.process_action(
            ActionSubmission(
                agent_id="pyra",
                action_type="fireball",
                params={"target": "glacius"},
            ),
            tick=7,
        )
        assert store.get("pyra")["last_fireball_tick"] == 7  # type: ignore[union-attr]

    def test_defeat_consequence_fires(self) -> None:
        """When HP <= 0, consequence sets winner."""
        config, store, event_log = self._build()
        store.update_property("pyra", "hp", 20)
        engine = RulesEngine(config, store, event_log)
        scanner = ConsequenceScanner(config, store, event_log)

        engine.process_action(
            ActionSubmission(
                agent_id="glacius",
                action_type="fireball",
                params={"target": "pyra"},
            ),
            tick=1,
        )
        # HP is now -5
        assert store.get("pyra")["hp"] == -5  # type: ignore[union-attr]
        triggered, _dm_pending = scanner.scan(tick=1)
        assert "wizard_defeated" in triggered
        assert store.get("arena")["winner"] == "glacius"  # type: ignore[union-attr]

    def test_mana_regen_auto_tick(self) -> None:
        """Auto_tick regenerates mana each tick."""
        config, store, event_log = self._build()
        tick_engine = TickEngine(config, store, event_log, ActionQueue())

        store.update_property("pyra", "mana", 10)
        tick_engine.step()
        assert store.get("pyra")["mana"] == 13  # type: ignore[union-attr]


# ============================================================
# Scenario 2: Stock Market — VALUE TRANSFER
# ============================================================


class TestStockMarket:
    """Stock market: buy/sell transfers value, prices move, dividends pay."""

    def _build(self) -> tuple[SceneConfig, StateStore, EventLog]:
        config = SceneConfig(
            scene=SceneMetaConfig(id="market", description="Stock market"),
            entities=[],
            actions={
                "buy_nova": ActionConfig(
                    description="Buy NovaCorp shares",
                    params=[ParamConfig(name="quantity", type="number")],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="nova.shares_available",
                            op=">=",
                            right="$quantity",
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="$agent.cash",
                            op=">=",
                            right="nova.price",
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="$agent.cash",
                            by="nova.price * $quantity",
                        ),
                        EffectConfig(
                            operator="increment",
                            target="$agent.nova_shares",
                            by="$quantity",
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="nova.shares_available",
                            by="$quantity",
                        ),
                        EffectConfig(
                            operator="increment",
                            target="nova.price",
                            by=2,
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="trade",
                            detail="$agent bought $quantity NovaCorp",
                            ttl=3,
                            scope="global",
                        ),
                    ],
                ),
                "sell_nova": ActionConfig(
                    description="Sell NovaCorp shares",
                    params=[ParamConfig(name="quantity", type="number")],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$agent.nova_shares",
                            op=">=",
                            right="$quantity",
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="$agent.cash",
                            by="nova.price * $quantity",
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="$agent.nova_shares",
                            by="$quantity",
                        ),
                        EffectConfig(
                            operator="increment",
                            target="nova.shares_available",
                            by="$quantity",
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="nova.price",
                            by=3,
                        ),
                    ],
                ),
            },
            auto_tick=[
                AutoTickConfig(
                    description="Dividends",
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="whale.cash",
                            by="2 * whale.nova_shares",
                        ),
                    ],
                ),
            ],
        )
        store = StateStore()
        store.add(
            Entity(
                id="nova",
                type="stock",
                _data={"price": 100, "shares_available": 50},
            )
        )
        store.add(
            Entity(
                id="whale",
                type="agent",
                _data={"cash": 10000, "nova_shares": 0},
            )
        )
        return config, store, EventLog()

    def test_buy_transfers_cash_to_shares(self) -> None:
        """Buying: cash decreases by price*qty, shares increase."""
        config, store, event_log = self._build()
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(
                agent_id="whale",
                action_type="buy_nova",
                params={"quantity": 5},
            ),
            tick=1,
        )
        assert result.success
        # cash: 10000 - (100 * 5) = 9500
        assert store.get("whale")["cash"] == 9500.0  # type: ignore[union-attr]
        assert store.get("whale")["nova_shares"] == 5  # type: ignore[union-attr]
        # Price went up by 2
        assert store.get("nova")["price"] == 102  # type: ignore[union-attr]
        # Shares available decreased
        assert store.get("nova")["shares_available"] == 45  # type: ignore[union-attr]

    def test_cant_buy_more_shares_than_available(self) -> None:
        """Can't buy if shares_available < quantity."""
        config, store, event_log = self._build()
        store.update_property("nova", "shares_available", 3)
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(
                agent_id="whale",
                action_type="buy_nova",
                params={"quantity": 5},
            ),
            tick=1,
        )
        assert not result.success

    def test_sell_returns_cash_and_drops_price(self) -> None:
        """Selling: cash increases, shares decrease, price drops."""
        config, store, event_log = self._build()
        store.update_property("whale", "nova_shares", 10)
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(
                agent_id="whale",
                action_type="sell_nova",
                params={"quantity": 3},
            ),
            tick=1,
        )
        assert result.success
        # cash: 10000 + (100 * 3) = 10300
        assert store.get("whale")["cash"] == 10300.0  # type: ignore[union-attr]
        assert store.get("whale")["nova_shares"] == 7  # type: ignore[union-attr]
        # Price dropped by 3
        assert store.get("nova")["price"] == 97  # type: ignore[union-attr]

    def test_dividends_pay_per_share(self) -> None:
        """Auto_tick pays dividends proportional to shares held."""
        config, store, event_log = self._build()
        store.update_property("whale", "nova_shares", 10)
        store.update_property("whale", "cash", 1000)
        tick_engine = TickEngine(config, store, event_log, ActionQueue())

        tick_engine.step()
        # Dividends: 2 * 10 = 20
        assert store.get("whale")["cash"] == 1020.0  # type: ignore[union-attr]


# ============================================================
# Scenario 3: Metamorphosis — STATE MACHINE via consequences
# ============================================================


class TestMetamorphosis:
    """Lifecycle: egg -> larva -> pupa -> butterfly through auto_tick + consequences."""

    def _build(self) -> tuple[SceneConfig, StateStore, EventLog]:
        config = SceneConfig(
            scene=SceneMetaConfig(id="garden", description="Insect lifecycle"),
            entities=[],
            actions={},
            consequences={
                "egg_to_larva": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="bug.stage",
                            op="==",
                            right="egg",
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="bug.age_in_stage",
                            op=">=",
                            right=4,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="bug.stage",
                            value="larva",
                        ),
                        EffectConfig(
                            operator="set",
                            target="bug.age_in_stage",
                            value=0,
                        ),
                    ],
                ),
                "larva_to_pupa": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="bug.stage",
                            op="==",
                            right="larva",
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="bug.energy",
                            op=">=",
                            right=80,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="bug.stage",
                            value="pupa",
                        ),
                        EffectConfig(
                            operator="set",
                            target="bug.age_in_stage",
                            value=0,
                        ),
                    ],
                ),
                "pupa_to_butterfly": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="bug.stage",
                            op="==",
                            right="pupa",
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="bug.age_in_stage",
                            op=">=",
                            right=6,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="bug.stage",
                            value="butterfly",
                        ),
                        EffectConfig(
                            operator="set",
                            target="bug.age_in_stage",
                            value=0,
                        ),
                        EffectConfig(
                            operator="increment",
                            target="garden.butterflies",
                            by=1,
                        ),
                    ],
                ),
            },
            auto_tick=[
                AutoTickConfig(
                    description="Age",
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="bug.age_in_stage",
                            by=1,
                        ),
                    ],
                ),
                AutoTickConfig(
                    description="Larvae eat",
                    condition=[
                        PreconditionConfig(
                            operator="check",
                            left="bug.stage",
                            op="==",
                            right="larva",
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="bug.energy",
                            by=10,
                        ),
                    ],
                ),
            ],
        )
        store = StateStore()
        store.add(
            Entity(
                id="garden",
                type="environment",
                _data={"butterflies": 0},
            )
        )
        store.add(
            Entity(
                id="bug",
                type="insect",
                _data={"stage": "egg", "age_in_stage": 0, "energy": 10},
            )
        )
        return config, store, EventLog()

    def test_egg_hatches_after_4_ticks(self) -> None:
        """After 4 ticks of aging, egg transitions to larva."""
        config, store, event_log = self._build()
        tick_engine = TickEngine(config, store, event_log, ActionQueue())

        for _ in range(4):
            tick_engine.step()

        assert store.get("bug")["stage"] == "larva"  # type: ignore[union-attr]
        assert store.get("bug")["age_in_stage"] == 0  # type: ignore[union-attr]

    def test_larva_pupates_when_energy_sufficient(self) -> None:
        """Larva transitions to pupa when energy >= 80."""
        config, store, event_log = self._build()
        # Start as larva with energy 70
        store.update_property("bug", "stage", "larva")
        store.update_property("bug", "energy", 70)
        tick_engine = TickEngine(config, store, event_log, ActionQueue())

        # Each tick: +10 energy (larva eating). After 1 tick: 80 -> triggers pupa
        tick_engine.step()
        assert store.get("bug")["stage"] == "pupa"  # type: ignore[union-attr]

    def test_full_lifecycle_egg_to_butterfly(self) -> None:
        """Complete lifecycle: egg -> larva -> pupa -> butterfly."""
        config, store, event_log = self._build()
        tick_engine = TickEngine(config, store, event_log, ActionQueue())

        # Run enough ticks for full lifecycle
        # egg: 4 ticks to hatch
        # larva: needs energy >= 80, starts at 10, gains 10/tick -> ~7 ticks
        # pupa: 6 ticks to emerge
        for _ in range(30):
            tick_engine.step()

        assert store.get("bug")["stage"] == "butterfly"  # type: ignore[union-attr]
        assert store.get("garden")["butterflies"] == 1  # type: ignore[union-attr]


# ============================================================
# Scenario 4: Virus Network — SELF-MODIFYING TOPOLOGY
# ============================================================


class TestVirusNetwork:
    """Network: firewall removes links, grant_access adds perception edges."""

    def _build(self) -> tuple[SceneConfig, StateStore, EventLog]:
        config = SceneConfig(
            scene=SceneMetaConfig(id="network", description="Computer network"),
            entities=[],
            actions={
                "firewall": ActionConfig(
                    description="Cut a link between two nodes",
                    params=[
                        ParamConfig(name="node_a", type="entity_ref"),
                        ParamConfig(name="node_b", type="entity_ref"),
                    ],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="remove_relationship",
                            from_entity="$node_a",
                            type="link",
                            to="$node_b",
                        ),
                        EffectConfig(
                            operator="remove_relationship",
                            from_entity="$node_b",
                            type="link",
                            to="$node_a",
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="defense",
                            detail="$agent firewalled $node_a <-> $node_b",
                            ttl=5,
                            scope="global",
                        ),
                    ],
                ),
                "patch": ActionConfig(
                    description="Patch a node",
                    params=[ParamConfig(name="target", type="entity_ref")],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$target.patched",
                            op="==",
                            right=False,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$target.patched",
                            value=True,
                        ),
                    ],
                ),
                "clean": ActionConfig(
                    description="Remove infection",
                    params=[ParamConfig(name="target", type="entity_ref")],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$target.infected",
                            op="==",
                            right=True,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$target.infected",
                            value=False,
                        ),
                    ],
                ),
                "grant_access": ActionConfig(
                    description="Grant another admin access to a node",
                    params=[
                        ParamConfig(name="target_admin", type="entity_ref"),
                        ParamConfig(name="node", type="entity_ref"),
                    ],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="add_relationship",
                            from_entity="$target_admin",
                            type="access_to",
                            to="$node",
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(
            Entity(
                id="server_a",
                type="node",
                _data={
                    "infected": True,
                    "patched": False,
                    "integrity": 80,
                    "link": ["server_b"],
                },
            )
        )
        store.add(
            Entity(
                id="server_b",
                type="node",
                _data={
                    "infected": False,
                    "patched": False,
                    "integrity": 100,
                    "link": ["server_a"],
                },
            )
        )
        store.add(
            Entity(
                id="admin",
                type="agent",
                _data={"skill": 80, "access_to": ["server_a"]},
            )
        )
        return config, store, EventLog()

    def test_firewall_removes_bidirectional_links(self) -> None:
        """Firewalling cuts the link in both directions."""
        config, store, event_log = self._build()
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(
                agent_id="admin",
                action_type="firewall",
                params={"node_a": "server_a", "node_b": "server_b"},
            ),
            tick=1,
        )
        assert result.success
        # Both directions removed
        a = store.get("server_a")
        b = store.get("server_b")
        assert a is not None and b is not None
        assert "server_b" not in a.get("link", [])
        assert "server_a" not in b.get("link", [])

    def test_grant_access_expands_relationships(self) -> None:
        """Granting access adds a new relationship to the admin."""
        config, store, event_log = self._build()
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(
                agent_id="admin",
                action_type="grant_access",
                params={"target_admin": "admin", "node": "server_b"},
            ),
            tick=1,
        )
        assert result.success
        admin = store.get("admin")
        assert admin is not None
        access_targets = admin.get("access_to", [])
        assert "server_a" in access_targets
        assert "server_b" in access_targets

    def test_clean_then_patch_secures_node(self) -> None:
        """Clean removes infection, patch makes it immune."""
        config, store, event_log = self._build()
        engine = RulesEngine(config, store, event_log)

        # Clean infected server
        result = engine.process_action(
            ActionSubmission(
                agent_id="admin",
                action_type="clean",
                params={"target": "server_a"},
            ),
            tick=1,
        )
        assert result.success
        assert store.get("server_a")["infected"] is False  # type: ignore[union-attr]

        # Patch it
        result = engine.process_action(
            ActionSubmission(
                agent_id="admin",
                action_type="patch",
                params={"target": "server_a"},
            ),
            tick=2,
        )
        assert result.success
        assert store.get("server_a")["patched"] is True  # type: ignore[union-attr]

        # Can't patch again (already patched)
        result = engine.process_action(
            ActionSubmission(
                agent_id="admin",
                action_type="patch",
                params={"target": "server_a"},
            ),
            tick=3,
        )
        assert not result.success


# ============================================================
# Scenario 5: Music Scene — REPUTATION AS ACTION GATE
# ============================================================


class TestReputationCascade:
    """Music scene: reputation gates venue access, collabs create relationships."""

    def _build(self) -> tuple[SceneConfig, StateStore, EventLog]:
        config = SceneConfig(
            scene=SceneMetaConfig(id="music", description="Music scene"),
            entities=[],
            actions={
                "perform": ActionConfig(
                    description="Perform at a venue",
                    params=[ParamConfig(name="venue", type="entity_ref")],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$agent.reputation",
                            op=">=",
                            right="$venue.min_reputation",
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="$agent.energy",
                            op=">=",
                            right=20,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="$agent.energy",
                            by=20,
                        ),
                        EffectConfig(
                            operator="increment",
                            target="$agent.reputation",
                            by=5,
                        ),
                        EffectConfig(
                            operator="increment",
                            target="$agent.fans",
                            by=30,
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="performance",
                            detail="$agent performed at $venue!",
                            ttl=5,
                            scope="global",
                        ),
                    ],
                ),
                "collab": ActionConfig(
                    description="Collaborate with another artist",
                    params=[ParamConfig(name="partner", type="entity_ref")],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$agent.energy",
                            op=">=",
                            right=15,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="$agent.energy",
                            by=15,
                        ),
                        EffectConfig(
                            operator="increment",
                            target="$agent.reputation",
                            by=8,
                        ),
                        EffectConfig(
                            operator="increment",
                            target="$partner.reputation",
                            by=8,
                        ),
                        EffectConfig(
                            operator="add_relationship",
                            from_entity="$agent",
                            type="collab_with",
                            to="$partner",
                        ),
                        EffectConfig(
                            operator="add_relationship",
                            from_entity="$partner",
                            type="collab_with",
                            to="$agent",
                        ),
                    ],
                ),
                "start_beef": ActionConfig(
                    description="Start a feud",
                    params=[
                        ParamConfig(name="rival", type="entity_ref"),
                        ParamConfig(name="diss", type="free_text"),
                    ],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="add_relationship",
                            from_entity="$agent",
                            type="beefing_with",
                            to="$rival",
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="$rival.reputation",
                            by=5,
                        ),
                        EffectConfig(
                            operator="increment",
                            target="$agent.scandal_count",
                            by=1,
                        ),
                    ],
                ),
            },
            consequences={
                "gets_signed": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="mc.reputation",
                            op=">=",
                            right="label.signing_threshold",
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="mc.signed",
                            op="==",
                            right=False,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="mc.signed",
                            value=True,
                        ),
                        EffectConfig(
                            operator="increment",
                            target="mc.money",
                            by=500,
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(
            Entity(
                id="the_pit",
                type="venue",
                _data={"min_reputation": 0, "prestige": 10},
            )
        )
        store.add(
            Entity(
                id="arena",
                type="venue",
                _data={"min_reputation": 70, "prestige": 90},
            )
        )
        store.add(
            Entity(
                id="label",
                type="label",
                _data={"signing_threshold": 60},
            )
        )
        store.add(
            Entity(
                id="mc",
                type="agent",
                _data={
                    "reputation": 45,
                    "fans": 200,
                    "energy": 100,
                    "money": 50,
                    "signed": False,
                    "scandal_count": 0,
                },
            )
        )
        store.add(
            Entity(
                id="singer",
                type="agent",
                _data={
                    "reputation": 55,
                    "fans": 500,
                    "energy": 80,
                    "money": 100,
                    "signed": False,
                    "scandal_count": 0,
                },
            )
        )
        return config, store, EventLog()

    def test_low_rep_blocked_from_arena(self) -> None:
        """Can't perform at arena with reputation 45 (needs 70)."""
        config, store, event_log = self._build()
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(
                agent_id="mc",
                action_type="perform",
                params={"venue": "arena"},
            ),
            tick=1,
        )
        assert not result.success

    def test_low_rep_can_play_small_venue(self) -> None:
        """Can perform at the_pit with any reputation."""
        config, store, event_log = self._build()
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(
                agent_id="mc",
                action_type="perform",
                params={"venue": "the_pit"},
            ),
            tick=1,
        )
        assert result.success
        assert store.get("mc")["reputation"] == 50  # type: ignore[union-attr]
        assert store.get("mc")["fans"] == 230  # type: ignore[union-attr]

    def test_collab_boosts_both_artists(self) -> None:
        """Collaborating boosts both artists' rep.

        Creates bidirectional collab_with relationships.
        """
        config, store, event_log = self._build()
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(
                agent_id="mc",
                action_type="collab",
                params={"partner": "singer"},
            ),
            tick=1,
        )
        assert result.success
        assert store.get("mc")["reputation"] == 53  # type: ignore[union-attr]
        assert store.get("singer")["reputation"] == 63  # type: ignore[union-attr]

        # Bidirectional collab relationship created
        mc = store.get("mc")
        singer = store.get("singer")
        assert mc is not None and singer is not None
        assert "singer" in mc.get("collab_with", [])
        assert "mc" in singer.get("collab_with", [])

    def test_beef_damages_rival_reputation(self) -> None:
        """Starting beef reduces rival's reputation and increases scandal count."""
        config, store, event_log = self._build()
        engine = RulesEngine(config, store, event_log)

        result = engine.process_action(
            ActionSubmission(
                agent_id="mc",
                action_type="start_beef",
                params={"rival": "singer", "diss": "your beats are weak"},
            ),
            tick=1,
        )
        assert result.success
        assert store.get("singer")["reputation"] == 50  # type: ignore[union-attr]
        assert store.get("mc")["scandal_count"] == 1  # type: ignore[union-attr]

    def test_signing_consequence_fires_at_threshold(self) -> None:
        """When reputation reaches label threshold, signing consequence fires."""
        config, store, event_log = self._build()
        store.update_property("mc", "reputation", 59)
        engine = RulesEngine(config, store, event_log)
        scanner = ConsequenceScanner(config, store, event_log)

        # Perform to cross threshold: 59 + 5 = 64 >= 60
        engine.process_action(
            ActionSubmission(
                agent_id="mc",
                action_type="perform",
                params={"venue": "the_pit"},
            ),
            tick=1,
        )
        triggered, _dm_pending = scanner.scan(tick=1)
        assert "gets_signed" in triggered
        assert store.get("mc")["signed"] is True  # type: ignore[union-attr]
        assert store.get("mc")["money"] == 550  # type: ignore[union-attr]
