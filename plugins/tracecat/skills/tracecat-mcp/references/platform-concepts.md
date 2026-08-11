# Tracecat platform concepts

## Scope and identifiers

Every operation is scoped to a workspace. Organization membership does not replace a workspace ID. Objects may expose UUIDs, slugs, aliases, names, and refs; use the exact identifier required by each tool.

## Workflows

A workflow has mutable draft state and published state. Draft edits use optimistic revisions. Validation checks the draft; publishing makes a version available for non-draft execution. A draft run and a published-version run are different choices.

Workflow actions come from the Tracecat registry. Action names and argument schemas are discoverable through authoring-context tools. Workspace variables and secrets are referenced through Tracecat expressions, not copied into workflow definitions as plaintext.

## Skills and agent presets

A workspace skill has a mutable draft and immutable published versions. Only published versions can be attached to agent presets. A local directory upload should preserve the complete tree rooted at `SKILL.md`.

Agent presets combine instructions, model configuration, allowed actions or namespaces, integrations, approvals, and published skills. Inspect the preset authoring context before creating or changing one.

## Tables and cases

Tables are workspace data stores with typed columns and row APIs. Cases add security-case semantics, events, tags, fields, dropdown definitions, tasks, and workflow triggers. Definition IDs and per-case values are separate objects; discover definitions before assigning values.

## Validation and execution

Validation is not execution. Publishing is not verification. After a requested run, inspect its execution record and surface structured errors instead of inferring success from tool acceptance.
