# Skill upload contract

Four MCP tools cover the whole surface: `list_skills`, `upload_skill`, `update_skill`, `publish_skill`. Each write tool takes the complete file tree in one call.

## Local payload

`manifest` writes a JSON file at mode `0600`:

```json
{
  "file_count": 3,
  "total_size_bytes": 4821,
  "encoded_size_bytes": 6428,
  "files": [
    {
      "path": "SKILL.md",
      "content_base64": "LS0tCm5hbWU6IGV4YW1wbGUtc2tpbGwKLS0tCg==",
      "content_type": "text/markdown; charset=utf-8"
    },
    {
      "path": "references/troubleshooting.md",
      "content_base64": "IyBUcm91Ymxlc2hvb3RpbmcK",
      "content_type": "text/markdown; charset=utf-8"
    }
  ],
  "digests": [
    { "path": "SKILL.md", "sha256": "<64 lowercase hex characters>", "size_bytes": 28 }
  ]
}
```

`files` is shaped for the MCP tools and is passed verbatim. `digests` and the counters are local bookkeeping — do not send them. Paths are POSIX-relative to the skill root. The set must contain a root `SKILL.md`. Empty files are supported. `content_type` is optional; the server guesses from the path when it is omitted.

## `upload_skill`

Creates a new logical skill and its first draft.

```json
{
  "workspace_id": "<workspace UUID>",
  "name": "example-skill",
  "description": "Optional summary",
  "files": [{ "path": "SKILL.md", "content_base64": "...", "content_type": "text/markdown; charset=utf-8" }]
}
```

Returns the skill, including `id`, `slug`, `draft_revision`, `is_draft_publishable`, `draft_validation_errors`, and `draft_file_count`.

The server merges `name` and `description` into the root `SKILL.md` frontmatter before validation, so the stored frontmatter always matches the arguments. Slug collisions are resolved by suffixing the slug, not by failing — calling this twice with one name produces two skills.

## `update_skill`

Replaces an existing skill's draft. Does not publish.

```json
{
  "workspace_id": "<workspace UUID>",
  "skill_id": "<skill UUID>",
  "name": "example-skill",
  "description": "Optional summary",
  "files": [{ "path": "SKILL.md", "content_base64": "...", "content_type": "text/markdown; charset=utf-8" }]
}
```

The submitted set becomes the draft in full: paths absent from `files` are removed. For a skill that already has a published version, `name` and `description` update the stored `SKILL.md` frontmatter but do not rename the skill row.

## `publish_skill`

```json
{
  "workspace_id": "<workspace UUID>",
  "skill_id": "<skill UUID>"
}
```

Returns the immutable version: `id`, `version`, `manifest_sha256`, `file_count`, `total_size_bytes`, and the file manifest. Only published versions can be attached to agent presets.

## Re-binding a preset

`update_agent_preset` takes `skills` as a list of `{"skill_id": "<skill UUID>"}`. There is no version field. The server resolves each `skill_id` to that skill's `current_version_id` at write time and stores the resolved pair, so a binding is a snapshot. Publishing a new version leaves existing bindings on the old one until the preset's `skills` list is written again.

`get_agent_preset` returns the resolved bindings as `{skill_id, skill_version_id, skill_name, skill_version}`. Compare `skill_version` before and after to confirm the re-bind landed.

## Security properties

- Tracecat OAuth and PAT credentials stay in the MCP client. The helper never sees them, makes no network calls, and imports only the standard library.
- The helper refuses symlinked files and symlinked directories, and refuses non-regular files, so nothing outside the selected root is read.
- Every emitted `content_base64` is decoded and compared against the source bytes before it is written, and `verify` repeats that comparison against the live directory.
- Payload files are created with mode `0600`.

What this path does not protect: the encoded contents of every file are tool arguments and therefore transit model context and any transcript or log the client keeps. That is inherent to the shipped tools. Keep secrets out of skill directories.
