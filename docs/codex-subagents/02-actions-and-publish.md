# Actions And Publish

YAML defines engine actions. `publish` is a `ws.py` helper used by Codex
subagents.

## YAML Action

```yaml
actions:
  submit_artifact:
    params:
      - { name: artifact_id, type: string, required: true }
      - { name: title, type: string, required: true }
      - { name: content_ref, type: string, required: true }
      - { name: summary, type: free_text, required: true }
    events:
      - type: artifact_submitted
        scope: target_only
        target: critic
        push: true
```

The engine validates the action params, records the event, routes inboxes, and
may emit a director signal.

## ws.py publish

`publish` performs:

```text
append row to this worker's lane file
then call engine act(action, params)
```

Example:

```bash
python3 "$WORLDSEED_WORKSPACE/ws.py" publish submit_artifact \
  --lane artifacts.jsonl \
  --row '{"artifact_id":"draft-v1","title":"Draft V1","content_ref":"agents/writer/files/draft-v1.md","summary":"First draft"}' \
  artifact_id=draft-v1 \
  title="Draft V1" \
  content_ref="agents/writer/files/draft-v1.md" \
  summary="First draft"
```

Two sources of truth:

```text
lane row        content truth for final story/presentation
engine action   coordination truth for events/inboxes/signals
```

If the lane row has extra fields, pass explicit `key=value` action params so
the engine receives only fields declared by YAML.

## Lane Rules

```text
agents/{id}/*.jsonl      append-only artifact streams
agents/{id}/files/...    long bodies, images, generated assets
agents/{id}/scratch/...  private drafts and scripts
```

Agents do not edit other agents' lanes. Use ids for cross-agent references:

```json
{
  "critique_id": "crit-001",
  "target_artifact_id": "draft-v1",
  "target_owner_agent": "writer",
  "label": "too generic",
  "comment": "Needs a concrete user and sharper claim."
}
```

