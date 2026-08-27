# Agent outputs and structured output types

**Default to no `output_type`. Let the agent call the tool.**

An agent whose job is to communicate — post to Slack, post to Teams, answer in chatops, open or
comment on a case — should be handed that tool and told to use it. The side effect *is* the
output. Its final text is then a plain run summary for the execution log, and nothing
downstream needs to parse it.

Define an `output_type` **only when a downstream deterministic step must branch on the value.**
If nothing consumes it, it is ceremony with a cost:

- It duplicates the work. The message exists twice — once as the tool call the agent actually
  made, once as returned data — and the two can silently disagree about what was sent. The
  execution record then shows a message that may never have been posted.
- It invites the anti-pattern directly. Once the message is in the output, the obvious next
  step is to compose in the agent and post from the workflow. That is exactly the "Python owns
  the agentic part" smell: the wording lives in a schema, Block Kit and tone become
  workflow-graph edits, and responsibility splits across two places.
- It constrains the model. A schema-constrained final response is a different generation task
  from a free-form one, and it is the one the model is worse at.

**Always ask the user before adding an `output_type`.** It changes the workflow's contract, and
the answer is usually "no, the agent should just post it."

## When it is right

Add one when a `run_if`, a table write, or a subflow argument genuinely reads a field. Keep the
schema to the fields that are actually consumed — a boolean gate and an ID, not a full report.
Then the agent's structured output is control-flow data, and the human-facing message is still
the agent's own tool call.

## Valid values

`output_type` is either one of eight literals — `bool`, `float`, `int`, `str`, `list[bool]`,
`list[float]`, `list[int]`, `list[str]` — or a JSON Schema dict for anything else.

The string form `'list[{"finding": "str", "severity": "str"}]'` appears in Tracecat's DSL
reference. That is an `ai.action` shape, **not** a preset `output_type`; passing it to a preset
fails validation. For structured objects on a preset, pass a JSON Schema dict.

`update_agent_preset` cannot clear an `output_type` once set — see
[agent-presets](agent-presets.md) for the partial-update semantics.

## Dry runs need no schema

A dry run does not need a machine-readable plan. Put the instruction in the prompt — "if
`dry_run` is true, describe what you would have done and do not post" — and read the plain-text
response. A `{"would_post": true, "message": "..."}` schema for a dry run buys nothing that the
text did not already say, and it re-introduces the duplicate-message problem for the one case
where nothing is sent.

## Drive behavior with language, not a mode enum

A router that emits `{"mode": "weekly_digest", "window_days": 7}` for the agent to parse looks
tidy and is a dead end:

- The agent becomes unusable in ad-hoc chat, because a human types a question, not a mode.
- Every new behavior has to be added in three places — the router, the enum, the prompt — plus
  the evals.
- The router now owns judgment it cannot exercise, since a JSON enum cannot express "the same
  digest, but only the unresolved ones."

Have the router compose a **plain-English request** instead: "Post this week's access-review
digest for the last 7 days to #sec-ops." A cron and a human then share one interface, and new
behavior is a prompt change.

Keep genuinely deterministic control flow structured and separate — a boolean gating a table
write, an ID a subflow needs — as a field the *workflow* reads in a `run_if`, not as an
instruction the agent has to parse back out of its own input.
