---
name: tracecat-workspace-chat
description: Use whenever Tracecat Workspace Chat answers platform questions or operates workflows, cases, tables, agent presets, integrations, secrets, variables, or other workspace features. Adapts generic Tracecat MCP guidance to the tools actually exposed in Workspace Chat and routes platform facts to bundled local docs. Do not use for external Tracecat MCP connections or Tracecat source-code development.
---

# Tracecat Workspace Chat

Use this skill before any Tracecat platform operation or product how-to in Workspace Chat.
The chat is already bound to one workspace, and its registry-action tools do not match the
external Tracecat MCP surface one-for-one.

## Authority and routing

1. This skill and [the Workspace Chat tool map](references/tool-mapping.md) are authoritative
   for tool-name mappings, missing capabilities, and host-specific behavior. The schemas exposed
   with the current session's tools are authoritative for arguments. If generic MCP guidance
   conflicts with this adapter, follow the adapter.
2. For platform usage, navigation, configuration, concepts, or capability questions, search the
   bundled docs under `references/docs/`. Start with `references/docs/docs.json` to understand
   navigation, then read only the relevant `.mdx` pages and any snippets they import. The docs are
   authoritative for product facts; do not answer from memory when a local page is available. The
   Tracecat application image injects this directory at build time, so it can be absent when the
   source plugin is inspected outside Workspace Chat.
3. For workflow, table, expression, or agent-preset authoring practices, also use
   `$tracecat-automation-best-practices` after applying this adapter's tool map. Use that skill's
   domain practices, but ignore its external-MCP control-plane tool names.
4. For Slack-facing automations, also use `$tracecat-slackbot-best-practices`.

## Operating rules

- Read [the Workspace Chat tool map](references/tool-mapping.md) before translating MCP-oriented
  instructions or calling a platform tool.
- Never call `list_workspaces` or pass a `workspace_id`; the session supplies the workspace.
- Use only tools present in the current session. Do not synthesize `core.workflow.<mcp_name>` or
  claim an unavailable operation succeeded.
- Inspect each exposed tool schema for its exact arguments rather than inferring them from an MCP
  operation with a similar name.
- Read the current object and revision before edits. Validate changes through the available
  validate-only operation before applying the same change when supported.
- Publishing, running, deleting, or making externally visible changes still requires the user's
  request or clear task necessity. This adapter changes routing, not authorization.

## When local docs do not answer

Say that the bundled docs do not cover the detail and that Workspace Chat has no internet access.
Point the user to the current [Tracecat documentation](https://docs.tracecat.com),
[Tracecat community](https://discord.com/invite/H4XZwsYzY4), Tracecat support, or the
[Tracecat GitHub repository](https://github.com/TracecatHQ/tracecat). Do not invent a product fact,
UI path, vendor step, support address, or missing tool.
