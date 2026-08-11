# Deterministic skill upload contract

The transfer is split so the MCP client retains Tracecat authentication while the local helper handles raw bytes.

## 1. Local manifest

The helper emits only integrity metadata:

```json
{
  "files": [
    {
      "path": "SKILL.md",
      "sha256": "<64 lowercase hex characters>",
      "size_bytes": 1234,
      "content_type": "text/markdown; charset=utf-8"
    }
  ]
}
```

Paths are POSIX-relative to the selected skill root. The complete set must contain root `SKILL.md`. Empty files are supported.

## 2. Prepare through MCP

`prepare_skill_upload` creates or selects the logical skill, captures its draft revision, and creates one workspace- and skill-bound upload session per file. Its response contains:

- `workspace_id`, `skill_id`, and `base_revision`
- `created`, indicating whether a logical skill was created
- one short-lived `PUT` URL, upload ID, required headers, SHA-256, size, and path per file

The URL is a temporary credential. Store the response in a user-only temporary file and delete it after use.

## 3. Raw HTTP upload

The helper verifies that the current local file set exactly matches the plan, then streams each file with the returned method and headers. It never receives a Tracecat access token and never emits signed URLs.

## 4. Complete through MCP

The helper emits arguments shaped for `complete_skill_upload`:

```json
{
  "workspace_id": "<workspace UUID>",
  "skill_id": "<skill UUID>",
  "base_revision": 4,
  "files": [
    {
      "path": "SKILL.md",
      "upload_id": "<upload UUID>"
    }
  ]
}
```

Tracecat verifies object existence, exact byte count, and SHA-256 before attaching anything. Completion deletes draft paths absent from the submitted set and applies all attachments under the captured revision guard.

## Security properties

- Long-lived OAuth and PAT credentials stay inside the MCP client.
- Signed URLs expire and are bound to a specific staged object and content type.
- Upload IDs are bound to the authenticated workspace and skill.
- Local symlinks are rejected.
- The model handles metadata and short-lived transfer instructions, never encoded file contents.
