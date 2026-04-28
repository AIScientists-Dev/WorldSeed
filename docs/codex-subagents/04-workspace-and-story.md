# Workspace And Story

This adapter treats the workspace as the durable evidence folder.

## trajectory.md

For Codex and workers during the run.

Contains:

```text
objective
success criteria
roles
suggested pressure sequence
expected artifact types
stop/ship conditions
```

It is not engine logic and not the user-facing story.

## story.md

For the user near the end.

It should explain:

```text
what happened
who produced what
which branches diverged
which critiques changed direction
what was revised
what was selected or rejected
where final files live
```

`story.md` should cite artifact ids, critique ids, selected/rejected ids, and
final refs.

## Final HTML

Optional. Generate it after the run if it helps.

Good final HTML:

```text
starts with the conclusion
shows the process spatially or narratively
places critiques next to target artifacts
shows revision lineage
keeps raw evidence collapsible
uses relative refs to workspace files
```

If the page becomes a generic data dump, skip it and ship `story.md` plus the
artifact refs.

