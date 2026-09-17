# Agent presets

Before creating or updating presets, call `get_agent_preset_authoring_context` and
`list_integrations`. Check workspace model credentials, attachable MCP integrations, output
type options, variables, and available tools.

Give a preset the tools its job actually calls for, and trust it with them. Encode routing,
table names, output style, and production action rules directly in the preset instructions;
the agent reads its own instructions, not repo files.

Prefer a preset when reusable behavior already exists. Inline `ai.agent` fits when the prompt
should live with one workflow and is not worth sharing.

## Where tools live

An agent's tools normally live on the preset's `actions` allowlist, or on an attached skill's
`metadata.tools` when the tools group naturally and more than one agent reuses them; one-off
tools usually stay on the preset. That way the agent has the same tools in Workspace Chat and
in every workflow that calls it. A skill declares them in its `SKILL.md` frontmatter:

```yaml
---
name: slack-triage
description: Post and thread triage updates in Slack.
metadata:
  tools:
    - tools.slack.post_message
    - tools.slack.list_replies
---
```

The effective tool set is the union: the preset's `actions` plus every attached skill's
`metadata.tools`. A skill's tools are granted as soon as the preset resolves, whether or not
the model ever opens the skill; only the skill's instructions load on demand. A skill may
declare up to 64 tools, named as registry action names or as `mcp.<slug>` / `mcp.<slug>.<tool>`.

**The `namespaces` trap.** The preset's `namespaces` filter then applies to the registry tools
in that union, and silently drops the ones outside it — declared, attached, and absent at
runtime. They appear under `tool_policy.blocked_tools` on `get_agent_preset`, so read that
after attaching a skill to a namespace-restricted preset. MCP tools a skill declares
(`mcp.<slug>` / `mcp.<slug>.<tool>`) are not filtered by `namespaces` and do not show up in
`blocked_tools`.

Preset-owned tools help for a second reason: presets are also Workspace Chat copilots. The
same preset is expected to answer a plain typed question, not only a workflow-shaped payload,
so anything it needs to do the job is better travelling with the preset than with one call
site.

## Calling a preset from a workflow

An `ai.preset_agent` node usually carries just `preset` and `user_prompt`, plus an optional
`instructions` append, which is concatenated after the preset's own instructions for
run-specific context.

The node's `actions` argument **replaces** the preset's and its skills' registry tool list for
that run rather than adding to it. MCP tools from the preset and its skills stay attached, and
an empty `actions: []` at the call site is ignored. That makes it a good fit for trying a
preset with a different tool set in a test or an eval. In a workflow that ships it is usually
the wrong place: the list also drops the registry tools the preset's skills contribute, so
prefer moving those tools onto the preset or a skill.

## Preset fields

- `instructions` — behavior, contracts, routing, tone, and rules.
- Model selection — see below.
- `actions` — the allowed registry actions.
- `namespaces` — a namespace filter over the registry tools in the effective set; MCP tools
  are unaffected.
- `skills` — published skill bindings, each contributing its `metadata.tools`.
- `mcp_integration_ids` — attached workspace MCP integrations.
- `tool_approvals` — per-tool human approval (Enterprise); the run pauses until a human decides.
- `agents` — subagents the preset can delegate to.
- `output_type` — structured output; leave unset unless the user asks for it.
- `enable_internet_access` — whether the sandbox can reach the internet.

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

Passing an empty list *does* clear a list field on `update_agent_preset`: `skills: []` detaches
all skills, and `actions: []` on that MCP call clears the preset's action allowlist. This is the
preset field, not the workflow-YAML argument of the same name — an `actions: []` on an
`ai.preset_agent` node is a no-op. Re-read the preset with
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
