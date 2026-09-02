# Workspace Chat tool mapping

Workspace Chat runs registry actions in the workspace already attached to the session. External
Tracecat MCP guidance uses a different control-plane surface. Apply these mappings before following
generic authoring guidance. The current session's exposed tool schemas remain authoritative for
complete argument shapes.

## Workspace and context

- `list_workspaces`: unavailable and unnecessary. Never pass `workspace_id` to a Workspace Chat
  registry action.
- `tracecat://platform/dsl-reference`: unavailable. Search `references/docs/` locally, using
  `references/docs/docs.json` as the navigation index.
- `list_actions`, `get_action_context`, and `get_workflow_authoring_context`: use
  `core.workflow.get_authoring_context`. Pass either `action_names=[...]` or `query=...`; do not
  wrap `action_names` in an `actions` object.
- `list_workflows`: unavailable in the default Workspace Chat surface. Use a workflow ID supplied
  by the conversation or current entity context; do not invent or enumerate one.

## Workflows

| External MCP operation | Workspace Chat action |
| --- | --- |
| `create_workflow` | `core.workflow.create_workflow` |
| `get_workflow` | `core.workflow.get_workflow` |
| `edit_workflow` | `core.workflow.edit_workflow` |
| `publish_workflow` | `core.workflow.publish` |
| `run_workflow` | `core.workflow.run` |
| `list_workflow_executions` | `core.workflow.list_executions` |
| `get_workflow_execution` | `core.workflow.get_status` with `include_events=true` when debugging |

There is no `update_workflow` action. Read the draft with
`core.workflow.get_workflow(workflow_id=...)`, then patch `/metadata`, `/definition`, `/layout`, or
`/schedules` with RFC 6902 operations through `core.workflow.edit_workflow`, passing the returned
`draft_revision` as `base_revision` and the operations as `patch_ops`.

There is no standalone `validate_workflow` action. For an existing workflow, submit the proposed
patch to `core.workflow.edit_workflow(validate_only=true)`, then apply the identical `patch_ops`
against the same `base_revision` with `validate_only=false`. `core.workflow.create_workflow`
validates a supplied definition. Do not publish or run merely to validate.

Use `core.workflow.get_webhook` and `core.workflow.update_webhook` for webhook state. Use
`core.workflow.get_case_trigger` and `core.workflow.update_case_trigger` for case triggers.
`update_case_trigger` is a partial update: omitted fields stay unchanged. Read first and pass every
desired field when replacing the effective configuration. Do not attempt to edit a case trigger
through workflow JSON Patch.

## Tables and cases

- `list_tables` maps to `core.table.list_tables`; `get_table` maps to
  `core.table.get_table_metadata` by table name.
- `search_table_rows` maps to `core.table.search_rows`; `export_csv` maps to
  `core.table.download(name=..., format="csv")`.
- `create_column_index` and `drop_column_index` map to
  `core.table.update_column(..., update={"is_index": true|false})`.
- Use the available `core.table.*` and `core.cases.*` action names exactly as exposed. Preserve
  read-before-write and pagination rules from the generic skill, but omit workspace IDs.

## Agent presets and integrations

- Preset create/get/list/update operations map to `ai.agent.create_preset`,
  `ai.agent.get_preset`, `ai.agent.list_presets`, and `ai.agent.update_preset`.
- `ai.agent.update_preset` uses `slug` to identify the current preset, `new_slug` to rename it,
  and `mcp_integrations` rather than `mcp_integration_ids`. `mcp_integrations` is a list of
  workspace MCP integration IDs.
- `get_agent_preset_authoring_context` has no full equivalent. Use
  `core.workflow.get_authoring_context` for enabled models, action schemas, variables, and secret
  hints.
- `list_integrations` has no default Workspace Chat equivalent. Do not claim to enumerate
  attachable MCP integrations.
