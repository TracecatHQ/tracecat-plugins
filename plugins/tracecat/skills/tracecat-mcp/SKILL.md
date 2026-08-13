---
name: tracecat-mcp
description: Use when an external agent needs to connect to or operate Tracecat through MCP, including workspace discovery, workflows, actions, cases, tables, integrations, agent presets, skills, executions, or safe platform navigation.
---

# Tracecat MCP

Use Tracecat's remote MCP server as the control plane. Discover current workspace state before making changes, preserve revision guards, and load only the domain reference needed for the task.

## Start here

1. Confirm the `tracecat` MCP server is connected. If authentication or endpoint setup fails, read [references/connection.md](references/connection.md).
2. Call `list_workspaces`; never guess a workspace ID from a name or prior session.
3. Read the current object before mutating it. Follow cursors when the matching object may be outside the first page.
4. Choose the narrowest relevant tool family from [references/tool-routing.md](references/tool-routing.md).
5. For writes, reuse the latest returned ID and revision. Validate before publishing or running when the domain supports validation.

## Progressive context routing

- Read [references/platform-concepts.md](references/platform-concepts.md) when the user is unfamiliar with drafts, published versions, registry actions, agent presets, or workspace scoping.
- Read [references/tool-routing.md](references/tool-routing.md) when selecting tools across workflows, cases, tables, integrations, agents, or skills.
- Use the `tracecat-manage-skills` skill for uploading, replacing, or downloading a local skill directory. Its helper keeps raw file bytes out of model context.
- When a future domain skill such as `tracecat-automation-best-practices` is installed, use it for that domain's authoring rules while retaining this skill for connection and routing.

## Operating rules

- Treat UUIDs, slugs, aliases, and refs as distinct identifiers. Obtain the exact identifier accepted by the next tool.
- Prefer focused patch/edit tools over full replacement for existing objects.
- On a revision conflict, re-read current state and reconcile; do not retry blindly with the new revision.
- Keep drafts and published versions distinct. Publishing or running can affect other users and systems, so do it only when requested or clearly required by the task.
- Inspect secret and integration metadata, but never request, print, or persist secret values in prompts or files.
- Use Tracecat-native expressions and action schemas. Call authoring-context tools instead of inventing action arguments.
- Report validation errors and execution failures with the object ID and the safe, structured error details returned by Tracecat.

## Common workflow

For most changes:

1. Discover the workspace and target object.
2. Fetch current state and its revision.
3. Fetch domain authoring context if arguments or schemas are involved.
4. Make the smallest change.
5. Validate.
6. Publish or execute only if requested.
7. Re-read or inspect the execution to verify the outcome.
