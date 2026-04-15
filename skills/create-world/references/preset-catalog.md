# Preset Catalog

Presets are reusable config fragments. Import via `scene.use`:
```yaml
scene:
  use: [talk, directed_talk, attempt, move_simple, hunger_system]
```

Each preset does ONE thing. Compose freely. Config's own definitions override presets.

## Communication

| Preset | Adds | When to use |
|--------|------|-------------|
| `talk` | `talk` action (say to everyone) | Every multi-agent scene |
| `directed_talk` | `directed_talk` action (say to one person, push wake) | When agents need private coordination |
| `attempt` | `attempt` action (DM-judged freeform) | Every scene — the overflow valve for creativity |

**Recommended:** Include all three in most scenes. `attempt` is essential — without it, agents can only do predefined actions.

## Movement

| Preset | Adds | When to use |
|--------|------|-------------|
| `move_simple` | `move` action (any visible space) | Small maps, all rooms connected |
| `move_connected` | `move` action (via `connects_to` relationships) | Large maps with restricted connections |
| `same_location_perception` | Visibility + event scope by location | Any spatial world |

**Note:** `move_connected` requires `add_relationship` setup for room connections. `move_simple` works immediately with any `type: space` entities.

## Combat & Conflict

| Preset | Adds | When to use |
|--------|------|-------------|
| `attack` | `attack` action (DM-judged damage) | Worlds with physical conflict |
| `rest` | `rest` action (+15 HP, cap 100) | Worlds with HP/combat |
| `steal` | `steal` action (DM-judged theft) | Worlds with social deception |
| `elimination_hp` | Consequence: hp ≤ 0 → eliminated | Survival, combat |
| `elimination_chips` | Consequence: chips ≤ 0 → eliminated | Games with currency |

## Exploration & Items

| Preset | Adds | When to use |
|--------|------|-------------|
| `observation` | `observe` action (DM describes what you see) | Exploration, investigation |
| `search` | `search` action (DM finds hidden items) | Mysteries, dungeons |
| `use_item` | `use_item` action (DM judges item effect) | Worlds with tools/items |
| `consume` | `consume` action (eat/drink resource, reset hunger) | Survival worlds |
| `trade` | `give` action (transfer resources between agents) | Economic worlds |

## Systems

| Preset | Adds | When to use |
|--------|------|-------------|
| `hunger_system` | Auto-tick hunger +3/tick, starvation at 80 | Survival scenarios |
| `timer` | Timer entity, countdown -1/tick | Any deadline-driven scenario |
| `deck` | 52-card deck entity | Card games |
| `day_night` | Clock entity, day/night cycle every 10 ticks | Worlds with time progression |
| `resource_decay` | All resources -1/tick | Resource scarcity scenarios |

## Recommended Combinations

**Survival bunker:**
```yaml
use: [talk, directed_talk, attempt, move_simple, observation, consume, hunger_system, elimination_hp]
```

**Card game:**
```yaml
use: [talk, directed_talk, attempt, deck]
# + your own game-specific actions (deal, bet, fold)
```

**Social deception:**
```yaml
use: [talk, directed_talk, attempt, observation, steal, same_location_perception, move_simple]
```

**Debate / council:**
```yaml
use: [talk, directed_talk, attempt, timer]
```

**Open world RPG:**
```yaml
use: [talk, directed_talk, attempt, move_connected, same_location_perception, observation, search, use_item, attack, rest, consume, hunger_system, day_night, elimination_hp]
```

## Turn-Based Game Pattern

For games that need turn rotation (werewolf, poker, debate), use the `rotate` operator instead of a preset. This pattern works for any scenario with ordered turns:

```yaml
entities:
  - id: game
    type: game_state
    active_turn: "player_1"
    turn_order: [player_1, player_2, player_3]
    out_players: []              # for rotate skip

actions:
  my_action:
    available_to:
      - { operator: check, left: "game.active_turn", op: "==", right: "$agent.id" }
    effects:
      - { operator: rotate, target: "game.active_turn", sequence: "game.turn_order", skip: "game.out_players" }
    events:
      - { type: "turn_change", scope: "global", push: true }
```

Key elements:
- `rotate` advances through the sequence, wrapping around, skipping eliminated players
- `available_to` gates actions to the current-turn agent
- `push: true` on turn-change events wakes the next agent immediately
- Maintain the skip list via `list_append` when players are eliminated
- For role-based turns (werewolf night), use role names in the sequence instead of agent IDs
