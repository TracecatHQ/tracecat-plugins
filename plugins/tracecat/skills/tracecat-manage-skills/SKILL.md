---
name: tracecat-manage-skills
description: Use when creating, uploading, updating, publishing, or re-binding a local Agent Skill directory through Tracecat MCP, including pushing a fix to a skill an agent preset already uses.
---

# Manage Tracecat skills

Tracecat MCP ships four skill tools: `list_skills`, `upload_skill`, `update_skill`, and `publish_skill`. All three write tools take the entire skill tree as one `files` argument, where each entry carries `content_base64`. Those encoded bytes are tool arguments, so they pass through model context. There is no staged-transfer path for skills; do not look for one.

The bundled helper does not avoid that cost. It removes the parts that are error-prone by hand: the safe directory walk, symlink rejection, root `SKILL.md` enforcement, SHA-256 digests, and a correctly shaped `files` array whose base64 has already been decoded and compared against the source bytes.

## Upload a new skill

1. Resolve the target workspace with `list_workspaces`.
2. Call `list_skills` first. If a skill with this name already exists, stop and use `## Updating a live skill` instead — `upload_skill` always creates a new row, so a second call yields two skills with the same `name` and different slugs.
3. Read the local root `SKILL.md` frontmatter for `name` and `description`.
4. Build the payload:

   ```bash
   python3 <this-skill-dir>/scripts/upload_skill_files.py manifest <local-skill-dir> \
     --output <payload.json>
   ```

   The helper writes `payload.json` with mode `0600` and prints only the path, file count, byte totals, and per-file digests.
5. Round-trip the payload once as a sanity check, then move on:

   ```bash
   python3 <this-skill-dir>/scripts/upload_skill_files.py verify <local-skill-dir> \
     --payload <payload.json>
   ```

6. Read `payload.json` and pass its `files` array verbatim to `upload_skill` along with `workspace_id`, `name`, and `description`. Delete the payload file afterwards.
7. Call `publish_skill` with the returned `skill_id` when the skill should be attachable to presets. An unpublished draft cannot be bound.

Pass the same `name` the local frontmatter declares. The server merges the `name` and `description` arguments into the stored root `SKILL.md` frontmatter before validating, so a mismatched argument silently rewrites the frontmatter that gets stored.

## Updating a live skill

A fix that stops after `update_skill` changes nothing that any agent runs. Three calls, in order:

1. `update_skill` with `workspace_id`, `skill_id`, `name`, and the full `files` array. This replaces the draft. It does not publish.
2. `publish_skill` with the same `skill_id`. Skills are versioned; this mints a new immutable version and moves the skill's `current_version_id`.
3. `update_agent_preset` with the consuming preset's `skills` list — the same `{"skill_id": ...}` entries it already had. Each binding is re-pinned to that skill's current published version at write time, so a preset bound before step 2 keeps running the old version until this call rewrites it.

Skipping step 3 is the classic failure: the new version exists, the preset never sees it.

Verify by re-fetching, because no tool reads a skill's files back and no diff API exists. `list_skills` shows the skill's `current_version_id`; `get_agent_preset` shows `skills[].skill_version_id` and `skills[].skill_version`. Confirm both moved. The absence of a read-back API is not a reason to skip the push.

This is routine, reversible work. Every published version is immutable and still bound-able, so a bad push is undone by publishing a corrected tree and re-binding. Do it rather than narrating risk; reserve caution for operations that actually cannot be undone.

## Size

The whole tree travels as one argument, and base64 inflates bytes by roughly a third. Keep skill directories small and text-only.

- Prefer Markdown, YAML, and scripts. A large binary asset is a bad fit for this transport; host it elsewhere and reference it.
- Move long-form detail into `references/` files the agent reads on demand rather than into `SKILL.md`.
- If the payload still exceeds the client's argument limit, split the skill itself into two skills. Do not split one tree across several `update_skill` calls — each call replaces the entire draft, so a partial call deletes everything it omits.

## Hard rules

- `upload_skill` creates; `update_skill` replaces. Never call `upload_skill` against a name that already exists — the slug retry makes the duplicate succeed instead of failing.
- Both write calls replace the entire draft. Files absent from the local directory are deleted from the skill. Always send the complete tree.
- Publishing does not move existing preset bindings. Re-write the preset's `skills` list to pick up a new version.
- Reject symlinked files and directories, and never send content from outside the selected skill root. The helper enforces this; do not work around it.
- The root file must be exactly `SKILL.md`, at the top level, and valid UTF-8. The server rejects a payload without it.
- Never hand-assemble base64 or ask the user to paste it. Run the helper; its round-trip check is what makes the encoding trustworthy.
- Delete the payload file after the call. It is a full copy of the skill on disk at mode `0600`.
- If the client cannot execute local scripts, say so and give the user the helper command to run. Do not substitute model-generated base64.

## References

- Read [references/upload-contract.md](references/upload-contract.md) for the literal payload shapes and what this path does and does not protect.
- Read [references/troubleshooting.md](references/troubleshooting.md) when an upload, update, publish, or preset re-bind does not land.
