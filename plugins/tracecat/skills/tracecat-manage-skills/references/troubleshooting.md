# Skill upload troubleshooting

## Two skills now share one name

`upload_skill` always creates a new logical skill, and a slug collision is resolved by suffixing the slug rather than failing. The duplicate call succeeded. Call `list_skills`, identify the row you meant to keep by `id` and `current_version_id`, and use `update_skill` against that `skill_id` from now on. Detach and remove the stray row through the UI or workspace API.

## Missing root `SKILL.md`

The server rejects any payload without a top-level `SKILL.md`. Point the helper at the skill directory itself, not its parent. The filename is case-sensitive and a nested `docs/SKILL.md` does not count.

## `SKILL.md` is not valid UTF-8

The server decodes the root file to merge `name` and `description` into its frontmatter. A `SKILL.md` that is not UTF-8 text fails before anything is written. The helper checks this locally during `manifest`.

## Oversized argument payload

The whole tree travels as one `files` argument and base64 inflates it. If the client rejects the call, shrink the tree: drop binary assets, move long prose into `references/` files, delete generated output. Do not split the tree across several `update_skill` calls — each call replaces the entire draft, so a partial call deletes every path it omits.

## Draft failed validation

`update_skill` and `upload_skill` raise `skill_upload_validation_failed` with a per-path error list. Fix the local files, rerun `manifest`, and resend the complete tree. `invalid_base64` and `invalid_path` in that list point at a hand-assembled payload — regenerate it with the helper.

## Published, but the agent still runs the old skill

Preset skill bindings are pinned to a version at write time. `publish_skill` moves the skill's `current_version_id` but does not touch presets already bound to the previous version. Call `update_agent_preset` with the preset's `skills` list — the same `skill_id` entries — to re-resolve the bindings, then confirm with `get_agent_preset` that `skills[].skill_version` incremented.

## Binding rejected as unpublished

`skill_not_published` means the skill has no `current_version_id`. `update_skill` only writes a draft. Call `publish_skill` before binding.

## The write looked like it failed but actually landed

A large skill or preset write can return a response big enough to read as an error in the client. Do not retry — a retried `upload_skill` creates a duplicate row, and a retried preset write can churn versions. Confirm with a separate read instead: `list_skills` for the skill's `current_version_id`, `get_agent_preset` for `skills[].skill_version`. Retry only if the read shows the change is genuinely absent.

## Helper reports the tree changed

`verify` decodes the payload and compares it against the live directory. A mismatch means the directory moved after `manifest` ran. Rerun `manifest` and resend; never edit the payload file to make the check pass.
