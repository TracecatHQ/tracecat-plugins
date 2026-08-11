# Skill upload troubleshooting

## `prepare_skill_upload` is unavailable

The connected Tracecat deployment predates staged MCP skill uploads. Do not generate base64. Upgrade the deployment or ask the user to run a supported direct-upload flow.

## Missing root `SKILL.md`

Select the skill directory itself, not its parent. File names are case-sensitive and the root file must be exactly `SKILL.md`.

## Local file set or digest changed

The directory changed after preparation. Delete the plan, rerun `manifest`, and call `prepare_skill_upload` again. Do not modify the plan to conceal drift.

## HTTP upload failed

Signed URLs may have expired, the client may be offline, or a required content-type header may have been altered. Discard the plan and prepare a fresh one. The helper intentionally omits signed URL details from errors.

## Upload missing or integrity error on completion

At least one raw PUT did not store the expected bytes. Rerun the complete preparation and upload sequence; do not reuse individual upload IDs from different plans.

## Draft revision conflict

Another writer changed the skill after preparation. Re-read or re-list the skill, compare the intended local tree with current state, then prepare a new plan from the reconciled directory.

## Draft is not publishable

Read `validation_errors`. Correct root frontmatter, paths, or file contents locally, then upload a new complete tree. Do not publish until `is_publishable` is true.
