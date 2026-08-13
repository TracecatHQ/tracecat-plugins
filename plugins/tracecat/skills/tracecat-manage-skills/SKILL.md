---
name: tracecat-manage-skills
description: Use when creating, reading, downloading, uploading, replacing, or updating an Agent Skill directory in a Tracecat workspace, especially when avoiding inline base64 and preserving the complete file tree through Tracecat MCP.
---

# Manage Tracecat skills

Transfer raw skill files through short-lived HTTP URLs prepared by Tracecat MCP. The model handles only paths and integrity metadata; the bundled helper streams file bytes directly.

## Required workflow

1. Resolve the target workspace with `list_workspaces`.
2. Resolve this installed skill's directory and the bundled `scripts/upload_skill_files.py` path.
3. Choose one path:
   - Existing skill: call `list_skills` and select the exact `skill_id`, then call `prepare_skill_download`. Feed the exact response through stdin to download the draft before reading or editing it:

     ```bash
     python3 <this-skill-dir>/scripts/upload_skill_files.py download \
       <local-skill-dir> --stdin-plan
     ```

     Edit the downloaded files locally. Use `--delete-extra` when the local directory must exactly mirror the draft.
   - New skill: create or inspect the local root `SKILL.md`; use its frontmatter `name` and optional `description`.
4. Generate upload metadata without reading file contents into the conversation:

   ```bash
   python3 <this-skill-dir>/scripts/upload_skill_files.py manifest <local-skill-dir>
   ```

5. Call `prepare_skill_upload` with the emitted `files` array:
   - Create: provide `name` and optional `description`; omit `skill_id`.
   - Update: provide `skill_id`; omit `name` and `description`.
6. Feed the exact prepare response through stdin. Do not print, log, or persist its signed URLs.
7. Upload the raw files:

   ```bash
   python3 <this-skill-dir>/scripts/upload_skill_files.py upload \
     <local-skill-dir> --plan -
   ```

8. Pass the helper's JSON output directly to `complete_skill_upload`.
9. Inspect `is_publishable` and `validation_errors` in the returned draft. Call `publish_skill` only when publication was requested and the draft is publishable.

The completion call replaces the entire draft. Files not present in the local directory are deleted, and `base_revision` prevents overwriting concurrent edits.

## Hard rules

- Never generate, paste, or ask the user to paste base64 file contents.
- Never add Tracecat OAuth or PAT credentials to the helper. Authentication remains in the MCP client; the helper receives only short-lived signed upload URLs.
- Pass signed download and upload plans to the helper through stdin; never print or log their URLs.
- Reject symlinked files and directories. Do not upload content outside the selected skill root.
- If the local directory changes after preparation, regenerate metadata and prepare a new plan.
- If URLs expire or any GET or PUT fails, discard the plan and prepare a new transfer.
- On `draft_revision_conflict`, re-list or re-read the skill and reconcile before starting a new plan.
- If the client cannot execute local scripts, explain the limitation and provide the helper command for the user to run. Do not silently fall back to model-generated base64.

## References

- Read [references/upload-contract.md](references/upload-contract.md) for payload shapes and the security boundary.
- Read [references/troubleshooting.md](references/troubleshooting.md) only when preparation, HTTP upload, completion, validation, or publication fails.
