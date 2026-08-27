# Tracecat MCP tool routing

Load the smallest tool family that satisfies the request.

| User intent | Start with | Important follow-up |
| --- | --- | --- |
| Find a workspace | `list_workspaces` | Reuse the exact workspace ID everywhere else |
| Find or inspect workflows | `list_workflows`, `get_workflow` | Use `edit_workflow` for focused changes |
| Author workflow actions | `get_workflow_authoring_context` | `validate_workflow` before publish or run |
| Discover an integration action | `list_actions`, `get_action_context` | Use the returned schema exactly |
| Debug a workflow run | `list_workflow_executions` | `get_workflow_execution` for structured failure details |
| Manage webhook or case triggers | `get_webhook`, `get_case_trigger` | Use the matching update tool after reading current state |
| Manage tables or rows | `list_tables`, `get_table` | Prefer batch row tools for multiple rows |
| Manage cases, tags, fields, or dropdowns | The matching `list_*` tool | Resolve definition IDs before associations or values |
| Inspect variables or secrets | `list_variables`, `list_secrets_metadata` | Work with metadata only; never request secret values |
| Configure an agent preset | `get_agent_preset_authoring_context` | Inspect integrations and skills before create/update |
| Upload or update a local skill | `list_skills`, then `upload_skill` or `update_skill` | `update_skill` for an existing skill; `upload_skill` suffixes the slug on a name collision rather than failing |
| Publish a skill and attach it to a preset | `publish_skill`, then `update_agent_preset` | Only published versions attach; re-submit the preset's `skills` bindings so the new version resolves |

## Workflow edit selection

- Use `edit_workflow` with the latest `draft_revision` for focused RFC 6902 changes.
- Use `update_workflow` without `definition_yaml` for metadata-only changes.
- Use inline YAML only for creation or an intentional bulk replacement.
- On a conflict, fetch the new draft and reconcile the patch against it.

## Pagination

List/search tools return `items`, `next_cursor`, `prev_cursor`, `has_more`, and `has_previous`. Continue with `next_cursor` when a unique match was not found on the current page. Do not interpret absence from page one as absence from the workspace.
