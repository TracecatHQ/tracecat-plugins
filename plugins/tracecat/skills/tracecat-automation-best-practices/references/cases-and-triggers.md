# Case triggers

A case trigger starts a workflow when a selected case event fires. It is configured on the
workflow, not on the case, and it lives alongside the webhook and schedule config rather than
on a page of its own.

## Trigger payload

The payload a case trigger dispatches has this exact shape:

- `${{ TRIGGER.case_id }}` — the case UUID as a string.
- `${{ TRIGGER.event.type }}` — one of the event type strings below.
- `${{ TRIGGER.event.data }}` — the event's own payload; its keys depend on the event type.
- `${{ TRIGGER.event.created_at }}` — ISO 8601, always timezone-aware.
- `${{ TRIGGER.event.id }}`, `${{ TRIGGER.event.user_id }}`, `${{ TRIGGER.event.wf_exec_id }}`.
- `${{ TRIGGER.tags }}` — a list of objects with `id`, `ref`, `name`, and `color`.
- `${{ TRIGGER.workspace_id }}`.

**There is no `TRIGGER.payload` key.** Tracecat's own DSL reference currently shows
`case_payload: "${{ TRIGGER.payload }}"` in its case-trigger example; that example is wrong and
resolves to nothing. Use `TRIGGER.case_id` to fetch the case, and `TRIGGER.event.data` for what
changed. If you have seen that example, unlearn it — it is the most likely reason a
case-triggered workflow receives an empty input.

The full case record is not in the payload. When the workflow needs the case's status,
severity, fields, or comments, call `core.cases.get_case` with `${{ TRIGGER.case_id }}`.

## Event types

Thirty values, matched exactly as written:

`case_created`, `case_updated`, `case_closed`, `case_reopened`, `case_viewed`,
`priority_changed`, `severity_changed`, `status_changed`, `fields_changed`,
`assignee_changed`, `attachment_created`, `attachment_deleted`, `tag_added`, `tag_removed`,
`payload_changed`, `task_created`, `task_deleted`, `task_status_changed`,
`task_priority_changed`, `task_workflow_changed`, `task_assignee_changed`,
`dropdown_value_changed`, `table_row_linked`, `table_row_unlinked`, `comment_created`,
`comment_updated`, `comment_deleted`, `comment_reply_created`, `comment_reply_updated`,
`comment_reply_deleted`.

Subscribe to the narrowest set that does the job. `case_updated` and `fields_changed` fire on
routine analyst edits and will run the workflow far more often than `case_created` or
`status_changed`.

## Configuration

Three fields:

```yaml
case_trigger:
  status: online              # or offline
  event_types: ["case_created", "status_changed"]
  tag_filters: ["phishing", "malware"]
```

- **`status: online` requires a non-empty `event_types`** — the validator raises
  `event_types must be non-empty when status is online`.
- **`status: online` also requires a published workflow** with a valid definition. Enabling a
  trigger on a draft-only workflow fails with `Publish the workflow before enabling case
  triggers`.
- **`tag_filters` match on the tag's `ref`** — the slug, not the display name — with **OR**
  semantics: the case runs the workflow if it carries *any* listed tag. An empty list means no
  tag filtering, so every matching event fires.

## Reading and writing the config

Prefer the `get_case_trigger` and `update_case_trigger` MCP tools over JSON-patching
`/case_trigger` through `edit_workflow`. Both work; the dedicated tools validate the enum
values and, on `update_case_trigger`, **create any tag refs that do not exist yet**, which a
raw patch does not.

**Treat `update_case_trigger` as a full replacement, not a partial update.** The tool passes
all three fields through to the service whether or not you supplied them, so an omitted
`event_types` clears the subscription list and an omitted `tag_filters` clears the tag
allowlist. Read the current config with `get_case_trigger` first, then send `status`,
`event_types`, and `tag_filters` together on every write.

## Silent failure modes

**Workflow-originated case events are ignored.** An event whose data carries a `wf_exec_id` —
that is, a case change made by a workflow — never dispatches a case trigger. This prevents
loops, and it also means a workflow cannot chain to itself by writing to the case it was
triggered by. When you need that hand-off, call the next workflow explicitly with
`core.workflow.execute`.

**An invalid workflow auto-disables its own trigger.** If the consumer finds no workflow
definition, a stale definition version, empty definition content, or content that fails DSL
validation, it flips the trigger's `status` to `offline` and moves on. So "my case trigger
stopped firing" usually means the workflow's published definition broke — check
`get_case_trigger` for an unexpected `offline`, fix the definition, republish, then set the
trigger back online. Nothing re-enables it for you.
