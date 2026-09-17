---
name: tracecat-manage-skills
description: Use when creating, uploading, updating, publishing, or re-binding a local Agent Skill directory through Tracecat MCP, including pushing a fix to a skill an agent preset already uses.
---

# Manage Tracecat skills

Tracecat MCP ships six skill tools: `list_skills`, `get_skill`, `prepare_skill_download`, `prepare_skill_upload`, `complete_skill_upload`, and `publish_skill`.

Writes are staged, not inlined. File bytes never travel as tool arguments: `prepare_skill_upload` takes metadata only — path, SHA-256, size, content type — and returns a short-lived `PUT` URL per file; the bytes go to those URLs over plain HTTP; `complete_skill_upload` then attaches the staged blobs and replaces the draft. Do not look for an inline `content_base64` argument, and never read file bytes into context to send them.

The bundled helper removes the parts that are error-prone by hand: the safe directory walk, symlink rejection, root `SKILL.md` enforcement, and SHA-256 digests.

## Upload a skill

The same four steps create a skill and replace an existing one. The only difference is which identity arguments `prepare_skill_upload` takes.

1. Resolve the target workspace with `list_workspaces`, then call `list_skills`. For a new skill, confirm the name is free — omitting `skill_id` always creates a new row, so a second create yields two skills with the same `name` and different slugs. For an existing skill, take its `skill_id`.
2. Build the metadata array:

   ```bash
   python3 <this-skill-dir>/scripts/upload_skill_files.py metadata <local-skill-dir>
   ```

   It prints the `files` array verbatim: one entry per file with `path`, `sha256`, `size_bytes`, and `content_type`. No file contents.

3. Call `prepare_skill_upload` with `workspace_id` and that `files` array, plus either:
   - `name` (and optional `description`) and **no** `skill_id`, to create a skill; or
   - `skill_id` and **no** `name`/`description`, to replace an existing skill's draft.

   For a create, pass the same `name` the local frontmatter declares — the server merges `name` and `description` into the stored root `SKILL.md` frontmatter before validating, so a mismatched argument silently rewrites what gets stored.

   The response carries `skill_id`, `base_revision`, `created`, and a per-file `upload_id`, `upload_url`, `method`, `headers`, and `expires_at`.

4. `PUT` each file's raw bytes to its `upload_url` with the returned method and headers, straight from disk. The URLs are short-lived; check `expires_at` and re-prepare rather than retrying a stale one.

5. Call `complete_skill_upload` with `workspace_id`, `skill_id`, the `base_revision` from step 3, and a `files` array of `{"path": ..., "upload_id": ...}` for every file. This replaces the draft and does not publish.

6. Call `publish_skill` with the `skill_id` when the skill should be attachable to presets. An unpublished draft cannot be bound.

`base_revision` is a concurrency guard. A `draft_revision_conflict` means someone else edited the draft since step 3 — call `get_skill` to see the current `draft_revision` and what a complete-tree replacement would delete, then re-prepare.

## Updating a live skill

A fix that stops after `complete_skill_upload` changes nothing that any agent runs. Three steps, in order:

1. `prepare_skill_upload` with `skill_id` → `PUT` the bytes → `complete_skill_upload`. This replaces the draft. It does not publish.
2. `publish_skill` with the same `skill_id`. Skills are versioned; this mints a new immutable version and moves the skill's `current_version_id`.
3. `update_agent_preset` with the consuming preset's `skills` list — the same `{"skill_id": ...}` entries it already had. Each binding is re-pinned to that skill's current published version at write time, so a preset bound before step 2 keeps running the old version until this call rewrites it.

Skipping step 3 is the classic failure: the new version exists, the preset never sees it.

Verify by re-fetching. `get_skill` without `path` returns the draft manifest — paths, digests, sizes, `draft_revision`, `is_publishable`, `validation_errors` — and never file contents; `get_skill` with `path` reads one file, inline when it is small UTF-8 text. `list_skills` shows the skill's `current_version_id`; `get_agent_preset` shows `skills[].skill_version_id` and `skills[].skill_version`. Confirm both moved.

This is routine, reversible work. Every published version is immutable and still bound-able, so a bad push is undone by publishing a corrected tree and re-binding. Do it rather than narrating risk; reserve caution for operations that actually cannot be undone.

## Declaring the skill's tools

A skill carries its own tools. Declare them in the root `SKILL.md` frontmatter under
`metadata.tools`, as registry action names or `mcp.<slug>` / `mcp.<slug>.<tool>` entries, up to
64 per skill:

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

Every preset the skill is attached to receives those tools on top of its own `actions`
allowlist. They are granted as soon as the preset resolves, whether or not the model opens the
skill; only the skill's instructions load on demand.

Prefer this over listing the same tools on each preset's `actions` when the tools group
naturally and several agents reuse them — one edit and a re-publish then updates every consuming
preset. Keep a tool on the preset's `actions` when it is specific to that one agent.

One caveat: a preset's `namespaces` filter applies over the union, and silently blocks skill
tools outside it. After attaching a skill to a namespace-restricted preset, check
`tool_policy.blocked_tools` on `get_agent_preset`.

Changing `metadata.tools` changes what agents can execute, so it follows the same three steps as
any other fix: replace the draft, `publish_skill`, then `update_agent_preset` to re-pin the
binding. A read of the resulting preset shows the granted tools as one flat list in
`tool_policy.actions`, with no per-skill provenance — the union is what you can verify.

## Size

Bytes no longer pass through model context, but each file still has a server-side size limit and a whole tree is still easier to review when it is small and text-only.

- Prefer Markdown, YAML, and scripts. Host a large binary asset elsewhere and reference it.
- Move long-form detail into `references/` files the agent reads on demand rather than into `SKILL.md`.
- If a tree is too large to reason about, split the skill itself into two skills. Do not split one tree across several `complete_skill_upload` calls — each call replaces the entire draft, so a partial call deletes everything it omits.

## Hard rules

- Omitting `skill_id` creates; passing it replaces. Never create against a name that already exists — the slug retry makes the duplicate succeed instead of failing.
- Every write replaces the entire draft. Files absent from the local directory are deleted from the skill. Always send the complete tree.
- Upload every prepared file before calling `complete_skill_upload`, and pass every path back with its `upload_id`.
- Never inline file bytes or base64 into a tool argument, and never read an upload or download URL's bytes into context. Stream to and from disk.
- Publishing does not move existing preset bindings. Re-write the preset's `skills` list to pick up a new version.
- Reject symlinked files and directories, and never send content from outside the selected skill root. The helper enforces this; do not work around it.
- The root file must be exactly `SKILL.md`, at the top level, and valid UTF-8. The server rejects a file set without it.
- If the client cannot execute local scripts, say so and give the user the helper command to run. Do not substitute model-generated digests.

## References

- Read [references/upload-contract.md](references/upload-contract.md) for the literal request and response shapes and what this path does and does not protect.
- Read [references/troubleshooting.md](references/troubleshooting.md) when an upload, publish, or preset re-bind does not land.
