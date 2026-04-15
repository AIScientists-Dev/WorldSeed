"""End-to-end test: Old Chen steals food from the bunker."""

from __future__ import annotations

import pytest

from tests.helpers import CONFIGS_DIR
from worldseed.engine.rules_engine import ActionResult
from worldseed.world import WorldEngine


def test_theft_scenario() -> None:
    """Full 4-step theft: move -> move -> take -> move.

    Mechanical actions (move, take) execute immediately via submit().
    step() is still called for auto_tick/consequences/perceiver.
    """
    engine = WorldEngine(CONFIGS_DIR / "bunker.yaml")
    engine.register_from_config()

    # === Verify initial state ===
    chen = engine.state.get("old_chen")
    assert chen is not None
    assert chen["location"] == "sleeping_quarters"
    assert chen["private_stash"] == 0

    food = engine.state.get("food_supply")
    assert food is not None
    assert food["quantity"] == 20

    li = engine.state.get("xiao_li")
    assert li is not None
    assert li["location"] == "sleeping_quarters"

    # === Step 1: chen -> hallway ===
    result = engine.submit("old_chen", "move", {"to": "hallway"})
    assert isinstance(result, ActionResult) and result.success
    assert chen["location"] == "hallway"
    engine.step()  # tick 1: auto_tick runs

    # === Step 2: chen -> storage_room ===
    result = engine.submit("old_chen", "move", {"to": "storage_room"})
    assert isinstance(result, ActionResult) and result.success
    assert chen["location"] == "storage_room"
    engine.step()  # tick 2: auto_tick runs

    # === Step 3: chen takes food ===
    # Auto_tick runs each step: 3 agents * 0.1 = 0.3/tick
    # After tick 1: 20 - 0.3 = 19.7
    # After tick 2: 19.7 - 0.3 = 19.4
    # submit("take") at tick 2: food = 19.4 - 3 = 16.4
    # step() tick 3: auto_tick(-0.3) -> 16.4 - 0.3 = 16.1
    result = engine.submit(
        "old_chen",
        "take",
        {
            "target": "food_supply",
            "amount": 3,
        },
    )
    assert isinstance(result, ActionResult) and result.success
    assert chen["private_stash"] == 3
    engine.step()  # tick 3: auto_tick runs
    assert food["quantity"] == pytest.approx(16.1, abs=0.01)

    # === Step 4: chen -> hallway (heading back) ===
    # step() tick 4: auto_tick(-0.3) -> 16.1 - 0.3 = 15.8
    result = engine.submit("old_chen", "move", {"to": "hallway"})
    assert isinstance(result, ActionResult) and result.success
    assert chen["location"] == "hallway"
    engine.step()  # tick 4: auto_tick runs
    assert food["quantity"] == pytest.approx(15.8, abs=0.01)

    # === Other agents unaffected ===
    assert li["location"] == "sleeping_quarters"

    wang = engine.state.get("doctor_wang")
    assert wang is not None
    assert wang["location"] == "hallway"
