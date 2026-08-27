# Agent presets

Before creating or updating presets, call `get_agent_preset_authoring_context` and
`list_integrations`. Check workspace model credentials, attachable MCP integrations, output
type options, variables, and available tools.

Give presets only the tools they need. Encode routing, table names, output style, and
production action rules directly in the preset instructions; the agent reads its own
instructions, not repo files.

Prefer a preset when reusable behavior already exists. Use inline `ai.agent` only when the
prompt should live with one workflow and should not be shared.

## Model selection

Prefer the `model` object for inline `ai.agent`; top-level `model_name`/`model_provider` are
deprecated unless the user asks for the legacy shape.

```yaml
args:
  model:
    model_name: claude-sonnet-4-6
    model_provider: anthropic
```

## Partial updates are not uniformly "omitted = unchanged"

`update_agent_preset` builds its update payload by dropping every argument left at `None`, so
an omitted `output_type`, `actions`, `skills`, or `mcp_integration_ids` is left unchanged
rather than cleared. The consequence runs the other way: **there is no way to clear
`output_type` from a preset over MCP** — passing `None` is indistinguishable from omitting it,
and only an explicit `"output_type": null` on the REST `PATCH /agent/presets/{id}` body
removes it. Removing a structured output contract is a UI or API edit, not an MCP one.

Passing an empty list *does* clear a list field: `skills: []` detaches all skills, and
`actions: []` clears the action allowlist. Re-read the preset with
`get_agent_preset_authoring_context` after any partial update rather than assuming what
landed.

Fields that change what the agent can execute — instructions, actions, MCP integrations,
subagents, skill bindings, output type — cut a new preset version on write. A no-op update
does not.

## Runtime capability

A preset's runtime has more capability than `list_actions` shows. The agent runs inside a
sandbox with a real shell and file tools (`Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`),
plus CLI utilities: Python and `uv`, `curl`, `jq`, and the DuckDB CLI for local SQL over CSV,
JSON, and Parquet. So an agent can shape data, parse JSON, and run tabular queries without a
workflow node for it. Before adding a workflow helper or preprocessing step to compensate for
a presumed limitation, inspect the preset/runtime context. When the agent can safely do the
bounded work itself, keep it in the preset instructions.
