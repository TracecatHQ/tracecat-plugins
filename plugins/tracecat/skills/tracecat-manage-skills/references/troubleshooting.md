# Skill upload troubleshooting

## Two skills now share one name

`prepare_skill_upload` without a `skill_id` always creates a new logical skill, and a slug collision is resolved by suffixing the slug rather than failing. The duplicate call succeeded. Call `list_skills`, identify the row you meant to keep by `id` and `current_version_id`, and pass that `skill_id` from now on. Detach and remove the stray row through the UI or workspace API.

## Missing root `SKILL.md`

The server rejects any file set without a top-level `SKILL.md`. Point the helper at the skill directory itself, not its parent. The filename is case-sensitive and a nested `docs/SKILL.md` does not count.

## `SKILL.md` is not valid UTF-8

The server decodes the root file to merge `name` and `description` into its frontmatter. A `SKILL.md` that is not UTF-8 text fails before anything is written. The helper checks this locally while walking the directory.

## `draft_revision_conflict`

`complete_skill_upload` refuses a `base_revision` that no longer matches the live draft, which means the draft moved after `prepare_skill_upload` ran. Call `get_skill` without `path` to read the current `draft_revision` and the manifest a complete-tree replacement would overwrite, then re-prepare and re-upload against the new revision. Never guess a revision number.

## An upload URL stopped working

The prepared URLs are short-lived; each entry carries its own `expires_at`. Once one has expired, re-run `prepare_skill_upload` for the whole tree and upload against the fresh URLs. Do not reuse `upload_id` values from an earlier prepare.

## Draft failed validation

The write raises `skill_upload_validation_failed` with a per-path error list. Fix the local files, rerun the helper's `metadata` subcommand, and resend the complete tree. An `invalid_path` entry points at a hand-assembled metadata array — regenerate it with the helper.

## A file uploaded but never landed in the draft

`complete_skill_upload` only attaches the paths it is given. A path left out of its `files` array is treated as deleted from the draft, however recently its bytes were PUT. Always send back every path from the prepare response with its `upload_id`.

## Published, but the agent still runs the old skill

Preset skill bindings are pinned to a version at write time. `publish_skill` moves the skill's `current_version_id` but does not touch presets already bound to the previous version. Call `update_agent_preset` with the preset's `skills` list — the same `skill_id` entries — to re-resolve the bindings, then confirm with `get_agent_preset` that `skills[].skill_version` incremented.

## Binding rejected as unpublished

`skill_not_published` means the skill has no `current_version_id`. `complete_skill_upload` only writes a draft. Call `publish_skill` before binding.

## The skill's tools never reach the agent

A preset's `namespaces` filter applies to the registry tools in the union of its `actions` and every attached skill's `metadata.tools`, and silently drops the ones outside it. Read `get_agent_preset`: granted tools appear as a flat list in `tool_policy.actions`, and filtered ones in `tool_policy.blocked_tools`. Widen `namespaces` or move the tool into an allowed namespace. MCP tools a skill declares (`mcp.<slug>` / `mcp.<slug>.<tool>`) are not filtered by `namespaces` and do not appear in `blocked_tools`, so when one of those is missing look instead at the preset's `mcp_integration_ids`.

## The write looked like it failed but actually landed

A large preset write can return a response big enough to read as an error in the client. Do not retry — a retried create makes a duplicate row, and a retried preset write can churn versions. Confirm with a separate read instead: `list_skills` for the skill's `current_version_id`, `get_agent_preset` for `skills[].skill_version`. Retry only if the read shows the change is genuinely absent.

## The tree changed mid-upload

Digests are computed when the helper walks the directory. If files change between that walk and the PUTs, the uploaded bytes no longer match the metadata the server was given. Re-run `metadata`, re-prepare, and re-upload; never edit a digest to make a check pass.
