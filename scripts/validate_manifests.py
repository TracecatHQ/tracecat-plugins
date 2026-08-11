#!/usr/bin/env python3
"""Validate cross-client Tracecat plugin invariants with the standard library."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "tracecat"
EXPECTED_NAME = "tracecat"
EXPECTED_ENDPOINT = "https://platform.tracecat.com/mcp"


class ManifestError(RuntimeError):
    """A repository manifest violates a cross-client invariant."""


def _load_object(relative_path: str) -> Mapping[str, object]:
    path = REPOSITORY_ROOT / relative_path
    try:
        value = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot load {relative_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestError(f"{relative_path} must contain a JSON object")
    return cast(Mapping[str, object], value)


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ManifestError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ManifestError(f"{label} must be an array")
    return cast(list[object], value)


def _string(value: Mapping[str, object], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ManifestError(f"{label}.{key} must be a non-empty string")
    return item


def _server_config(manifest: Mapping[str, object], label: str) -> Mapping[str, object]:
    servers = _object(manifest.get("mcpServers"), f"{label}.mcpServers")
    return _object(servers.get(EXPECTED_NAME), f"{label}.mcpServers.{EXPECTED_NAME}")


def _plugin_entry(
    marketplace: Mapping[str, object], label: str
) -> Mapping[str, object]:
    entries = _array(marketplace.get("plugins"), f"{label}.plugins")
    matching_entries: list[Mapping[str, object]] = []
    for index, entry in enumerate(entries):
        mapping = _object(entry, f"{label}.plugins[{index}]")
        if mapping.get("name") == EXPECTED_NAME:
            matching_entries.append(mapping)
    if len(matching_entries) != 1:
        raise ManifestError(
            f"{label} must contain exactly one {EXPECTED_NAME!r} plugin entry"
        )
    return matching_entries[0]


def _validate_skills() -> None:
    skills_root = PLUGIN_ROOT / "skills"
    skill_directories = sorted(path for path in skills_root.iterdir() if path.is_dir())
    if not skill_directories:
        raise ManifestError("plugin must contain at least one skill")
    for skill_directory in skill_directories:
        skill_markdown = skill_directory / "SKILL.md"
        if not skill_markdown.is_file():
            raise ManifestError(
                f"missing {skill_markdown.relative_to(REPOSITORY_ROOT)}"
            )
        content = skill_markdown.read_text(encoding="utf-8")
        if "[TODO" in content or "TODO:" in content:
            raise ManifestError(
                f"unfinished TODO in {skill_markdown.relative_to(REPOSITORY_ROOT)}"
            )
        expected_frontmatter = f"name: {skill_directory.name}"
        if expected_frontmatter not in content.split("---", 2)[1]:
            raise ManifestError(
                f"SKILL.md name does not match directory {skill_directory.name!r}"
            )
        if not (skill_directory / "agents" / "openai.yaml").is_file():
            raise ManifestError(
                f"missing Codex skill metadata for {skill_directory.name!r}"
            )


def validate() -> None:
    universal = _load_object("plugins/tracecat/plugin.json")
    codex = _load_object("plugins/tracecat/.codex-plugin/plugin.json")
    claude = _load_object("plugins/tracecat/.claude-plugin/plugin.json")
    universal_mcp = _load_object("plugins/tracecat/mcp.json")
    native_mcp = _load_object("plugins/tracecat/.mcp.json")
    codex_marketplace = _load_object(".agents/plugins/marketplace.json")
    claude_marketplace = _load_object(".claude-plugin/marketplace.json")

    manifests = {
        "universal": universal,
        "codex": codex,
        "claude": claude,
    }
    versions = {
        _string(manifest, "version", label) for label, manifest in manifests.items()
    }
    if len(versions) != 1:
        raise ManifestError(f"plugin manifest versions differ: {sorted(versions)}")
    for label, manifest in manifests.items():
        if _string(manifest, "name", label) != EXPECTED_NAME:
            raise ManifestError(f"{label}.name must be {EXPECTED_NAME!r}")

    universal_server = _server_config(universal_mcp, "universal mcp")
    native_server = _server_config(native_mcp, "native mcp")
    if universal_server.get("type") != "streamable-http":
        raise ManifestError("portable Tracecat MCP transport must be streamable-http")
    if native_server.get("type") != "http":
        raise ManifestError("native Tracecat MCP transport must be http")
    for label, server in {
        "universal mcp": universal_server,
        "native mcp": native_server,
    }.items():
        if server.get("url") != EXPECTED_ENDPOINT:
            raise ManifestError(f"{label} URL must be {EXPECTED_ENDPOINT}")

    codex_entry = _plugin_entry(codex_marketplace, "Codex marketplace")
    codex_source = _object(codex_entry.get("source"), "Codex marketplace source")
    if codex_source.get("source") != "local" or codex_source.get("path") != (
        "./plugins/tracecat"
    ):
        raise ManifestError("Codex marketplace source must target ./plugins/tracecat")

    claude_entry = _plugin_entry(claude_marketplace, "Claude marketplace")
    if claude_entry.get("source") != "./plugins/tracecat":
        raise ManifestError("Claude marketplace source must target ./plugins/tracecat")

    _validate_skills()


def main() -> int:
    try:
        validate()
    except ManifestError as exc:
        print(f"manifest validation failed: {exc}")
        return 1
    print("Tracecat plugin manifests are consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
