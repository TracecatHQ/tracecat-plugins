#!/usr/bin/env python3
"""Build and verify base64 skill upload payloads for Tracecat MCP.

`upload_skill` and `update_skill` accept the whole skill tree as one
`files` argument, so the encoded bytes travel as tool arguments. This helper
does not avoid that. It removes the parts an agent should never do by hand:
walking the directory safely, refusing symlinks, enforcing a root `SKILL.md`,
computing digests, base64-encoding every file, and proving the encoding
round-trips before anything is sent.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

_CHUNK_SIZE_BYTES = 1024 * 1024
_EXCLUDED_DIRECTORIES = frozenset({".git", ".venv", "__pycache__", "node_modules"})
_EXCLUDED_FILES = frozenset({".DS_Store"})
_SKILL_MARKDOWN_PATH = "SKILL.md"
_LARGE_PAYLOAD_WARNING_BYTES = 512 * 1024
_CONTENT_TYPES = {
    ".bash": "text/x-shellscript; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".json": "application/json",
    ".md": "text/markdown; charset=utf-8",
    ".py": "text/x-python; charset=utf-8",
    ".sh": "text/x-shellscript; charset=utf-8",
    ".toml": "application/toml",
    ".txt": "text/plain; charset=utf-8",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}


class SkillUploadError(RuntimeError):
    """Safe user-facing failure that never includes encoded file contents."""


@dataclass(frozen=True, slots=True)
class LocalSkillFile:
    """Integrity metadata and local path for one skill file."""

    path: str
    absolute_path: Path
    sha256: str
    size_bytes: int
    content_type: str

    def digest_entry(self) -> dict[str, str | int]:
        """Return the integrity record for this file."""

        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


class CliArguments(argparse.Namespace):
    """Typed argparse result shared by the helper subcommands."""

    def __init__(self) -> None:
        super().__init__()
        self.command: str = ""
        self.root: Path = Path()
        self.output: Path = Path()
        self.payload: Path = Path()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(_CHUNK_SIZE_BYTES):
            hasher.update(chunk)
    return hasher.hexdigest()


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if known_type := _CONTENT_TYPES.get(suffix):
        return known_type
    guessed_type, _ = mimetypes.guess_type(path.name)
    if guessed_type is None:
        return "application/octet-stream"
    if guessed_type.startswith("text/"):
        return f"{guessed_type}; charset=utf-8"
    return guessed_type


def _relative_posix_path(root: Path, path: Path) -> str:
    relative_path = path.relative_to(root).as_posix()
    path_object = PurePosixPath(relative_path)
    if (
        relative_path in {"", "."}
        or path_object.is_absolute()
        or ".." in path_object.parts
        or str(path_object) != relative_path
    ):
        raise SkillUploadError(f"invalid relative skill path: {relative_path!r}")
    return relative_path


def discover_skill_files(
    root_value: str | Path,
) -> tuple[Path, tuple[LocalSkillFile, ...]]:
    """Discover regular files below a skill root without following symlinks."""

    root_input = Path(root_value).expanduser()
    try:
        root = root_input.resolve(strict=True)
    except OSError as exc:
        raise SkillUploadError(f"skill root does not exist: {root_input}") from exc
    if not root.is_dir():
        raise SkillUploadError(f"skill root is not a directory: {root}")

    local_files: list[LocalSkillFile] = []
    for current_value, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_value)
        retained_directories: list[str] = []
        for directory_name in sorted(directory_names):
            directory = current / directory_name
            if directory_name in _EXCLUDED_DIRECTORIES:
                continue
            if directory.is_symlink():
                relative = _relative_posix_path(root, directory)
                raise SkillUploadError(
                    f"symlinked directory is not allowed: {relative}"
                )
            retained_directories.append(directory_name)
        directory_names[:] = retained_directories

        for file_name in sorted(file_names):
            if file_name in _EXCLUDED_FILES or file_name.endswith((".pyc", ".pyo")):
                continue
            file_path = current / file_name
            relative_path = _relative_posix_path(root, file_path)
            if file_path.is_symlink():
                raise SkillUploadError(
                    f"symlinked file is not allowed: {relative_path}"
                )
            if not file_path.is_file():
                raise SkillUploadError(
                    f"non-regular file is not allowed: {relative_path}"
                )
            local_files.append(
                LocalSkillFile(
                    path=relative_path,
                    absolute_path=file_path,
                    sha256=_sha256_file(file_path),
                    size_bytes=file_path.stat().st_size,
                    content_type=_content_type(file_path),
                )
            )

    local_files.sort(key=lambda file: file.path)
    if not any(file.path == _SKILL_MARKDOWN_PATH for file in local_files):
        raise SkillUploadError(
            f"skill root must contain a regular file named {_SKILL_MARKDOWN_PATH}"
        )
    return root, tuple(local_files)


def _encode_file(file: LocalSkillFile) -> str:
    """Return verified base64 for one file, re-decoding it as a sanity check."""

    content = file.absolute_path.read_bytes()
    if len(content) != file.size_bytes or hashlib.sha256(content).hexdigest() != (
        file.sha256
    ):
        raise SkillUploadError(f"file changed while it was being read: {file.path}")
    encoded = base64.b64encode(content).decode("ascii")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise SkillUploadError(
            f"base64 round-trip failed for {file.path}: encoding is not valid"
        ) from exc
    if decoded != content:
        raise SkillUploadError(
            f"base64 round-trip failed for {file.path}: decoded bytes differ"
        )
    return encoded


def upload_files_payload(files: Sequence[LocalSkillFile]) -> list[dict[str, str]]:
    """Return the exact `files` array accepted by upload_skill and update_skill."""

    entries: list[dict[str, str]] = []
    for file in files:
        if file.path == _SKILL_MARKDOWN_PATH:
            try:
                _ = file.absolute_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise SkillUploadError(
                    f"{_SKILL_MARKDOWN_PATH} must be readable UTF-8 text"
                ) from exc
        entries.append(
            {
                "path": file.path,
                "content_base64": _encode_file(file),
                "content_type": file.content_type,
            }
        )
    return entries


def manifest_payload(files: Sequence[LocalSkillFile]) -> dict[str, object]:
    """Return the upload payload plus its integrity summary."""

    upload_files = upload_files_payload(files)
    return {
        "file_count": len(files),
        "total_size_bytes": sum(file.size_bytes for file in files),
        "encoded_size_bytes": sum(
            len(entry["content_base64"]) for entry in upload_files
        ),
        "files": upload_files,
        "digests": [file.digest_entry() for file in files],
    }


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise SkillUploadError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], value)


def _required_string(value: Mapping[str, object], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise SkillUploadError(f"{label}.{key} must be a non-empty string")
    return item


def load_payload(payload_value: str | Path) -> dict[str, object]:
    """Load and structurally validate a payload emitted by `manifest`."""

    payload_path = Path(payload_value).expanduser()
    try:
        raw = cast(object, json.loads(payload_path.read_text(encoding="utf-8")))
    except OSError as exc:
        raise SkillUploadError(f"cannot read payload: {payload_path}") from exc
    except json.JSONDecodeError as exc:
        raise SkillUploadError(f"payload is not valid JSON: {payload_path}") from exc

    payload = _as_mapping(raw, "payload")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise SkillUploadError("payload.files must be a non-empty JSON array")
    for index, entry_value in enumerate(cast(list[object], files)):
        label = f"payload.files[{index}]"
        entry = _as_mapping(entry_value, label)
        _ = _required_string(entry, "path", label)
        content = entry.get("content_base64")
        if not isinstance(content, str):
            raise SkillUploadError(f"{label}.content_base64 must be a string")
    return dict(payload)


def verify_payload(
    root_value: str | Path, payload_value: str | Path
) -> dict[str, object]:
    """Decode an emitted payload and compare it byte-for-byte with the source."""

    payload = load_payload(payload_value)
    entries = [
        _as_mapping(entry, "payload.files[]")
        for entry in cast(list[object], payload["files"])
    ]
    _, local_files = discover_skill_files(root_value)
    local_by_path = {file.path: file for file in local_files}

    payload_paths = sorted(str(entry["path"]) for entry in entries)
    if len(set(payload_paths)) != len(payload_paths):
        raise SkillUploadError("payload contains duplicate paths")
    if payload_paths != sorted(local_by_path):
        missing = sorted(set(local_by_path) - set(payload_paths))
        unexpected = sorted(set(payload_paths) - set(local_by_path))
        raise SkillUploadError(
            "payload does not match the local skill tree; "
            f"missing={missing} unexpected={unexpected}"
        )

    verified_bytes = 0
    for entry in entries:
        path = str(entry["path"])
        local_file = local_by_path[path]
        try:
            decoded = base64.b64decode(
                cast(str, entry["content_base64"]), validate=True
            )
        except ValueError as exc:
            raise SkillUploadError(f"invalid base64 content for {path}") from exc
        expected = local_file.absolute_path.read_bytes()
        if decoded != expected:
            raise SkillUploadError(f"decoded bytes differ from source file: {path}")
        if hashlib.sha256(decoded).hexdigest() != local_file.sha256:
            raise SkillUploadError(f"decoded SHA-256 differs from source file: {path}")
        verified_bytes += len(decoded)

    return {
        "verified": True,
        "file_count": len(entries),
        "total_size_bytes": verified_bytes,
    }


def _write_payload(output_value: str | Path, payload: Mapping[str, object]) -> Path:
    output_path = Path(output_value).expanduser()
    if not output_path.parent.is_dir():
        raise SkillUploadError(f"output directory does not exist: {output_path.parent}")
    try:
        descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            _ = handle.write("\n")
        # O_CREAT leaves the mode of a pre-existing file untouched.
        os.chmod(output_path, 0o600)
    except OSError as exc:
        raise SkillUploadError(f"cannot write payload: {output_path}") from exc
    return output_path


def _warn_if_payload_permissions_are_broad(payload_value: str | Path) -> None:
    try:
        mode = Path(payload_value).expanduser().stat().st_mode
    except OSError:
        return
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(
            "warning: payload is readable by other users; prefer mode 0600",
            file=sys.stderr,
        )


def _print_manifest_summary(output_path: Path, payload: Mapping[str, object]) -> None:
    encoded_size = cast(int, payload["encoded_size_bytes"])
    print(f"payload: {output_path}")
    print(f"files: {payload['file_count']}")
    print(f"total_size_bytes: {payload['total_size_bytes']}")
    print(f"encoded_size_bytes: {encoded_size}")
    print("digests:")
    for digest in cast(list[Mapping[str, object]], payload["digests"]):
        print(f"  {digest['sha256']}  {digest['size_bytes']:>9}  {digest['path']}")
    if encoded_size > _LARGE_PAYLOAD_WARNING_BYTES:
        print(
            f"warning: {encoded_size} encoded bytes will pass through model context "
            "as one tool argument; trim large or binary files",
            file=sys.stderr,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and verify base64 skill upload payloads for Tracecat MCP.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser(
        "manifest", help="emit the files array for upload_skill or update_skill"
    )
    _ = manifest_parser.add_argument("root", type=Path, help="local skill directory")
    _ = manifest_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="payload JSON file to create with mode 0600",
    )

    verify_parser = subparsers.add_parser(
        "verify", help="round-trip an emitted payload against the source directory"
    )
    _ = verify_parser.add_argument("root", type=Path, help="local skill directory")
    _ = verify_parser.add_argument(
        "--payload",
        type=Path,
        required=True,
        help="payload JSON file emitted by the manifest subcommand",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv, namespace=CliArguments())
    try:
        if args.command == "manifest":
            _, files = discover_skill_files(args.root)
            payload = manifest_payload(files)
            output_path = _write_payload(args.output, payload)
            _print_manifest_summary(output_path, payload)
            return 0
        _warn_if_payload_permissions_are_broad(args.payload)
        result = verify_payload(args.root, args.payload)
        print(
            f"verified {result['file_count']} files "
            f"({result['total_size_bytes']} bytes) against {args.root}"
        )
        return 0
    except SkillUploadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
