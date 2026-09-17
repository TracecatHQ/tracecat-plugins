# Skill upload contract

Six MCP tools cover the whole surface: `list_skills`, `get_skill`, `prepare_skill_download`, `prepare_skill_upload`, `complete_skill_upload`, `publish_skill`. Writes are staged in two calls with a plain HTTP transfer in between; no tool ever carries file bytes.

## Local metadata

`metadata` prints the array `prepare_skill_upload` accepts, and nothing else:

```json
[
  {
    "path": "SKILL.md",
    "sha256": "<64 lowercase hex characters>",
    "size_bytes": 28,
    "content_type": "text/markdown; charset=utf-8"
  },
  {
    "path": "references/troubleshooting.md",
    "sha256": "<64 lowercase hex characters>",
    "size_bytes": 812,
    "content_type": "text/markdown; charset=utf-8"
  }
]
```

Paths are POSIX-relative to the skill root. The set must contain a root `SKILL.md`. Empty files are supported.

## `prepare_skill_upload`

Creates a skill, or prepares a replacement draft for an existing one, and returns the upload plan.

```json
{
  "workspace_id": "<workspace UUID>",
  "name": "example-skill",
  "description": "Optional summary",
  "files": [
    {
      "path": "SKILL.md",
      "sha256": "<64 lowercase hex characters>",
      "size_bytes": 28,
      "content_type": "text/markdown; charset=utf-8"
    }
  ]
}
```

Omit `skill_id` and pass `name` to create. Pass `skill_id` and omit `name`/`description` to replace an existing draft. Slug collisions are resolved by suffixing the slug, not by failing — creating twice with one name produces two skills.

The response carries `workspace_id`, `skill_id`, `base_revision`, `created`, and one entry per file:

```json
{
  "skill_id": "<skill UUID>",
  "base_revision": 3,
  "created": false,
  "files": [
    {
      "path": "SKILL.md",
      "sha256": "<64 lowercase hex characters>",
      "size_bytes": 28,
      "content_type": "text/markdown; charset=utf-8",
      "upload_id": "<upload UUID>",
      "upload_url": "https://<short-lived URL>",
      "method": "PUT",
      "headers": {},
      "expires_at": "<timestamp>"
    }
  ]
}
```

On a create, the server merges `name` and `description` into the root `SKILL.md` frontmatter before validation, so the stored frontmatter always matches the arguments.

## Transferring the bytes

`PUT` each file's raw bytes to its `upload_url` with the returned `method` and `headers`, streamed from disk. Never read the bytes into model context, and never reuse a URL past its `expires_at`.

## `complete_skill_upload`

Attaches the staged blobs and replaces the draft. Does not publish.

```json
{
  "workspace_id": "<workspace UUID>",
  "skill_id": "<skill UUID>",
  "base_revision": 3,
  "files": [{ "path": "SKILL.md", "upload_id": "<upload UUID>" }]
}
```

The submitted set becomes the draft in full: paths absent from `files` are removed. `base_revision` must still match the live draft, or the call fails with `draft_revision_conflict`. Returns the draft read: paths, digests, sizes, `draft_revision`, `is_publishable`, and `validation_errors`.

## `get_skill`

```json
{
  "workspace_id": "<workspace UUID>",
  "skill_id": "<skill UUID>",
  "path": "SKILL.md"
}
```

Without `path`, returns the draft manifest — paths, SHA-256 digests, sizes, `draft_revision`, `is_publishable`, `validation_errors` — and never file contents. With `path`, returns that one draft file: small UTF-8 text inline, anything else as a short-lived download URL whose bytes are fetched to disk. Use `prepare_skill_download` to pull the complete draft.

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

`get_agent_preset` returns the resolved bindings as `{skill_id, skill_version_id, skill_name, skill_version}`. Compare `skill_version` before and after to confirm the re-bind landed. Tools contributed by a bound skill's `metadata.tools` show up merged into `tool_policy.actions` as a flat list, with no per-skill provenance.

## Security properties

- Tracecat OAuth and PAT credentials stay in the MCP client. The helper never sees them, makes no network calls, and imports only the standard library.
- The helper refuses symlinked files and symlinked directories, and refuses non-regular files, so nothing outside the selected root is read.
- File contents travel directly between disk and the storage URL, so they do not transit model context, transcripts, or client logs.
- Each file's SHA-256 and size are declared before the transfer, so the server can reject bytes that do not match what was prepared.

What this path does not protect: file paths, sizes, digests, and content types are tool arguments and are visible in any transcript the client keeps. Upload URLs are bearer-capable for their lifetime — treat them as secrets and do not paste them anywhere durable. Keep secrets out of skill directories.

## Legacy inline payloads

Earlier servers exposed `upload_skill` and `update_skill`, which took the tree as one `files` array of `content_base64` entries. Those tools are gone from current Tracecat. The helper's `manifest` and `verify` subcommands still build and round-trip that array for a deployment that predates the staged flow; do not reach for them otherwise.
