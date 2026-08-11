---
name: tracecat-manage-skills
description: Use when creating, uploading, replacing, or updating a local Agent Skill directory in a Tracecat workspace, especially when avoiding inline base64 and preserving the complete file tree through Tracecat MCP.
---

# Manage Tracecat skills

Upload raw local files through short-lived HTTP URLs prepared by Tracecat MCP. The model handles only paths and integrity metadata; the bundled helper streams file bytes directly and emits the exact completion payload.

## Required workflow

1. Resolve the target workspace with `list_workspaces`.
2. Resolve this installed skill's directory and the bundled `scripts/upload_skill_files.py` path.
3. Inspect the local root `SKILL.md`. For a new Tracecat skill, use its frontmatter `name` and optional `description`. For an update, call `list_skills` and select the exact existing `skill_id`; do not create a duplicate.
4. Generate metadata without reading file contents into the conversation:

   ```bash
   python3 <this-skill-dir>/scripts/upload_skill_files.py manifest <local-skill-dir>
   ```

5. Call `prepare_skill_upload` with the emitted `files` array:
   - Create: provide `name` and optional `description`; omit `skill_id`.
   - Update: provide `skill_id`; omit `name` and `description`.
6. Write the exact prepare response to a temporary JSON file with mode `0600`. Do not print or log its signed URLs.
7. Upload the raw files:

   ```bash
   python3 <this-skill-dir>/scripts/upload_skill_files.py upload \
     <local-skill-dir> --plan <temporary-plan.json> --delete-plan
   ```

8. Pass the helper's JSON output directly to `complete_skill_upload`.
9. Inspect `is_publishable` and `validation_errors` in the returned draft. Call `publish_skill` only when publication was requested and the draft is publishable.

The completion call replaces the entire draft. Files not present in the local directory are deleted, and `base_revision` prevents overwriting concurrent edits.

## Hard rules

- Do not call legacy `upload_skill` or `update_skill` when the helper and staged tools are available.
- Never generate, paste, or ask the user to paste base64 file contents.
- Never add Tracecat OAuth or PAT credentials to the helper. Authentication remains in the MCP client; the helper receives only short-lived signed upload URLs.
- Reject symlinked files and directories. Do not upload content outside the selected skill root.
- If the local directory changes after preparation, regenerate metadata and prepare a new plan.
- If URLs expire or any PUT fails, discard the plan and call `prepare_skill_upload` again.
- On `draft_revision_conflict`, re-list or re-read the skill and reconcile before starting a new plan.
- If the client cannot execute local scripts, explain the limitation and provide the helper command for the user to run. Do not silently fall back to model-generated base64.

## References

- Read [references/upload-contract.md](references/upload-contract.md) for payload shapes and the security boundary.
- Read [references/troubleshooting.md](references/troubleshooting.md) only when preparation, HTTP upload, completion, validation, or publication fails.
