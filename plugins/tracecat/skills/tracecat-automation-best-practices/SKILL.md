---
name: tracecat-automation-best-practices
description: Use when building, editing, validating, or debugging generic Tracecat automations through Tracecat MCP, including workflow DSL/YAML authoring, table design, unique indexes, run-python Tracecat imports, agent presets, ai.agent or ai.preset_agent workflows, executions, validation, and workflow best practices.
---

# Tracecat Automation Best Practices

For Slack-facing automations, use `$tracecat-slackbot-best-practices`. In Tracecat Workspace Chat,
load `$tracecat-workspace-chat` first; its host-specific tool mapping overrides the external MCP
steps below. On-demand references: [graph-shape](references/graph-shape.md),
[expressions](references/expressions-and-conditions.md), [run-python](references/run-python.md),
[tables](references/tables.md), [trigger-inputs](references/trigger-inputs.md),
[case-triggers](references/cases-and-triggers.md), [secrets](references/secrets-and-oauth.md),
[agent-outputs](references/agent-outputs.md), [agent-presets](references/agent-presets.md),
[workflow-editing](references/workflow-editing.md).

## Workflow

For an external Tracecat MCP connection, start from live context rather than guessing:

1. Discover the workspace with `list_workspaces`.
2. Read `tracecat://platform/dsl-reference` when DSL syntax or examples are needed.
3. Use `get_workflow_authoring_context` for action schemas, variables, and secrets.
4. For existing workflows, use `get_workflow`, then targeted `edit_workflow` patches — see
   [workflow-editing](references/workflow-editing.md).
5. Validate with `validate_workflow`, run a draft or published execution when appropriate,
   then inspect failures with `list_workflow_executions` and `get_workflow_execution`.

Other hosts can expose a different tool surface. Follow their adapter rather than mechanically
prefixing these bare MCP names.

Clarify production choices that change the workflow contract: workspace, integration/provider,
secret source, publish/run behavior, destructive side effects, approvals, or acceptance
criteria. If the request is already specific enough, proceed.

## Graph shape

Sketch the shape before authoring and keep it as close to one line as the work allows. Prefer
linear over parallel, and readable over fully connected: **fewer edges is the metric.**

- **`depends_on` is execution order, not data wiring.** An action can read
  `ACTIONS.<ref>.result` from any ancestor, not only a direct parent — validation checks that
  the ref exists in the workflow, not that it is a parent. Add an edge when the action must
  *wait*, never to make a value reachable.
- **Gate once. A `run_if` on an action also skips every action below it on the chain, so never
  repeat it downstream.** A chain where every action carries the same `TRIGGER.enabled && ...`
  guard is wrong; only the first action needs it. A downstream action gets its own `run_if` only
  for a *new* condition, written alone. The exception is a join, and it is a trap: a task with
  several parents is not force-skipped while one survives, but the default `join_strategy: all`
  then requires *every* parent to have been visited, so one skipped branch makes the join
  unreachable and **fails the workflow**. Use `join_strategy: any`, or repeat the branch's
  condition on the join so it self-skips first.
- Default to a single chain. Branch only for genuinely independent work worth running
  concurrently, and rejoin only when a later action needs results from more than one branch.
- One parent is the norm. More than one means a deliberate join — choose `join_strategy` on
  purpose.
- Keep ordinary workflows around 20 nodes or fewer and agentic workflows around 6 nodes or
  fewer. Prefer readable left-to-right or top-to-bottom flows, human-readable refs, and layout
  refs aligned with definition refs.

See [graph-shape](references/graph-shape.md) for a worked over-connected rewrite, join
strategies, error edges, and why scatter is not branching.

## Choosing between an agent and Python

Decide by the *kind* of work, and optimize the whole workflow for maintainability and
readability — **the fewest actions and the least code that does the job.**

- **Agentic work → use an agent** (`ai.agent` / `ai.preset_agent`). Anything needing
  judgment, investigation, routing, enrichment choices, summarization, composing a message,
  or posting to Slack. Grant the tools on the preset's `actions` allowlist or on a skill's
  `metadata.tools`, then trust the agent with them. Prefer agents, prompts, and skills — they
  carry the creative thinking with far fewer moving parts than a graph of deterministic nodes.
- **Deterministic data plumbing → use Python** (`core.script.run_python`). Transforming,
  normalizing, redacting, loading or upserting rows into tables, forwarding data between
  systems. This is exactly what Python is for — it is **not** a smell. One clear `run_python`
  action beats scattering the same work across many nodes.

The smell is using Python for the *agentic* part — for example composing or sending an
agent's Slack message from a script instead of giving the agent the Slack tool.

**Prompt-size guardrail:** push behavior into the prompt up to a reasonable size. When a
single prompt grows too large to stay readable, decompose into **subagents or a skill**
rather than inflating one mega-prompt.

## Agent-First Automation

When the user asks for an agentic workflow, an agent preset, or says to use agents, make the
agent the primary owner of the work. Give it the tools it needs and trust it to investigate,
decide, route, compose messages, and act. Default to a thin shape:
`trigger -> reshape/redact -> upsert event record -> ai.agent` (or `ai.preset_agent`).

Persist the normalized event before the agent runs. When events originate in a SIEM, log
platform, SaaS webhook stream, audit trail, or cloud service, store the normalized payload
and review state in a Tracecat table first, with a deterministic upsert. That gives retries,
duplicate webhooks, and replay a durable source of truth. Point the agent at the saved row,
so the workflow — not the agent — owns the first durable record of the event.

A deterministic node earns its place by being thin, direct, and easy to audit, and by doing
work the agent should not own: redact secrets before the agent sees data, normalize schema,
upsert the event row, guard expensive agent runs with a dedupe check, prepare bounded
batches, or checkpoint durable state. Keep judgment, routing, enrichment, message
composition, soft approval decisions, and final notification behavior in the agent. When an
approval question itself needs judgment, let the agent decide or draft the request.

Two different mechanisms cover risk, and they do not compete with preset-owned tools. Use a
deterministic gate for an irreversible external effect the workflow itself performs — the
graph decides whether that node runs at all. Use per-tool `tool_approvals` on the preset for
a risky tool the agent holds: the agent keeps the tool, and the run pauses for a human before
that specific call goes through.

Favor one well-instructed agent or reusable preset over many small deterministic nodes. An
agent's tools normally live on the preset's `actions` allowlist, or on an attached skill's
`metadata.tools` when several agents share the group. That way the agent has the same tools
in Workspace Chat and in every workflow that calls it. Instructions carry behavior rather
than permissions: output contracts, Slack style, dedupe rules, tenant boundaries, and
permitted side effects go in the preset instructions, which the agent reads instead of repo
files. When the agent needs a tool, granting the narrow tool there usually beats wrapping the
same call in a workflow action.

An `ai.preset_agent` node usually carries just `preset` and `user_prompt`, plus an optional
`instructions` append for run-specific context. Its `actions` argument **replaces** the
preset's and its skills' registry tools for that run rather than adding to them — MCP tools
stay attached, and an empty list is ignored — so it suits trying a preset with a different
tool set in a test or an eval. A list left there in a shipping workflow also drops the
registry tools the preset's skills contribute, which is rarely what the author wanted.

Write agent instructions as goals, context, and reasons rather than prohibitions. A blanket
rule can cancel a tool the agent was given: one caller appended "Use only supplied evidence"
and the agent skipped the single policy lookup it had been granted a tool for. Reserve hard
rules for irreversible or outward-facing actions, and put `tool_approvals` or a deterministic
gate behind those instead of relying on the wording of a prompt.

A preset's runtime has more capability than `list_actions` shows: a real shell and file tools,
Python, `curl`, `jq`, and DuckDB. Inspect the preset/runtime context before adding a workflow
helper to compensate for a presumed limitation — see
[agent-presets](references/agent-presets.md).

## Authoring Defaults

- For agentic workflows, push most behavior into the agent prompt/preset. For event-driven
  workflows, a single reshape/redact/upsert action before the agent is usually the right
  deterministic boundary.
- Use `ai.agent` / `ai.preset_agent` for the agentic work; `core.http_request` for
  deterministic API calls; `core.script.run_python` for deterministic data work, once an inline
  expression, `run_if`, or a `core.transform.*` action has been ruled out — see
  [expressions](references/expressions-and-conditions.md) and
  [run-python](references/run-python.md).
- For bulk table writes, prefer one native `core.table.insert_rows` action when rows are already
  shaped (up to 1000 rows per batch). If shaping, chunking, or mixed table/case writes are needed,
  use `core.script.run_python` with imported helpers and bounded batches instead of scattering many
  DB-backed actions.
- Do not give `core.http_request` to an agent unless the user explicitly accepts the broad
  network capability. Put deterministic HTTP in the workflow graph or a tightly scoped subflow.
- Split into subflows only when there is a real orchestration boundary, reusable child
  workflow, separate execution history, approvals, long-running actions, or independent
  checkpointing. Use `core.workflow.execute` and prefer `workflow_alias` over hard-coded IDs.
  Subflow bulk defaults: `loop_strategy: batch`, `batch_size: 32`, `fail_strategy: isolated`,
  `wait_strategy: wait` (use `detach` only when the parent does not need child results).
- Keep run-python and agent outputs small: downstream rows, summary counts, bounded error
  samples.
- Prefer a reusable agent preset over inline `ai.agent`, and the `model` object over the
  deprecated top-level `model_name`/`model_provider` — see
  [agent-presets](references/agent-presets.md).

## Common Mistakes

- Using Python for the *agentic* part — composing or posting an agent's Slack message, or
  making routing/judgment calls in a script. The agent owns message composition, posting (via
  a Slack tool), and judgment; Python owns deterministic data plumbing.
- Over-connecting the graph: an edge from every producer to every consumer. Read from
  ancestors and keep one chain (see [graph-shape](references/graph-shape.md)).
- Repeating a `run_if` down a chain, restating a condition an ancestor already enforced. The
  skip propagates on its own — gate once at the top, and give a downstream action a `run_if`
  only for a new condition it alone introduces (see
  [graph-shape](references/graph-shape.md)).
- Workflow action names are not MCP tool names. Use MCP tools such as `create_workflow` to
  manage workflows, and action names such as `core.http_request` only inside workflow YAML.
- Inventing `tools.*` action names. Discover actions with `list_actions`, then inspect exact
  schemas with `get_action_context`.
- Using `for_each` for ordinary loop management, or using scatter/gather for data-heavy
  batching, filtering, joins, or table writes. Default to scatter for workflow-level loops;
  add gather only when downstream steps need combined results, and omit it otherwise. Be especially
  careful with >10 scattered DB-backed table/case actions, which can exhaust Postgres connection
  slots. Scatter's optional interval can stagger work, but it does not batch DB writes; use one
  `core.table.insert_rows` action or `core.script.run_python` batching for data-heavy processing
  (see [run-python](references/run-python.md)).
- Using `insert_rows(..., upsert=True)` without a unique index on the key column (see
  [tables](references/tables.md)).
- Granting `core.http_request` to an agent without explicit user approval of broad network
  access.
- Shipping a workflow with `actions:` on an `ai.preset_agent` node. It replaces the preset's
  and its skills' registry tools for that run instead of adding to them, so the skills' tools
  quietly disappear. Outside a test or an eval, put the tools on the preset or a skill and
  keep the node to `preset` + `user_prompt`.
- Defining an agent `output_type` when the user did not ask for structured output. Default to
  none, give the agent the tool, and let the side effect be the output; add one only on an
  explicit request or when a downstream step branches on the value (see
  [agent-outputs](references/agent-outputs.md)).
