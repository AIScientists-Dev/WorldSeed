# Configs

A WorldSeed scene needs two config files:

1. **[Scene Config](SCENE_CONFIG.md)** (`{scene_id}.yaml`) — Defines the world: entities, actions, rules, perception. What exists and how it behaves.

2. **[UI Config](UI_CONFIG.md)** (`{scene_id}.ui.json`) — Defines how the world renders: which entity types map to which visual scene types, property bindings, layout, assets. How it looks.

## Reference Docs

| Document | What it covers |
|----------|---------------|
| [Scene Config](SCENE_CONFIG.md) | Config syntax: sections, fields, types, examples |
| [Scene DSL](SCENE_DSL.md) | Expression language: preconditions, effects, functions, arithmetic |
| [Scene Design](SCENE_DESIGN.md) | Design guide: checklists, patterns, anti-patterns, testing |
| [UI Config](UI_CONFIG.md) | Dashboard rendering: visual types, bindings, layout |

Scene config is required. UI config is optional (without it, everything renders as gray fallback badges).

## File Locations

```
configs/
  teahouse.yaml            ← Scene config
  ai_layoffs.yaml
  template.yaml            ← Starting template
  SCENE_CONFIG.md          ← Full reference
  ...

frontend/public/configs/
  teahouse.ui.json         ← UI config
  ai_layoffs.ui.json
  ...

frontend/public/assets/scenes/{asset_pack}/
  agents/{agent_id}.png    ← Agent portraits
  entities/{entity_id}.png ← Zone/entity images
```

## Design Principle

Both configs follow the same zero-hardcode principle: entity types, property names, action names, and relationship types are all free strings. The engine never assumes a property is called "location" or a type is called "space". The UI config's bind mechanism maps arbitrary property names to visual slots — same idea.
