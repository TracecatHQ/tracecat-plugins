#!/usr/bin/env python3
"""Transfer raw skill files using short-lived URLs prepared by Tracecat."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import mimetypes
import os
import re
import ssl
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TextIO, cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

_CHUNK_SIZE_BYTES = 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_EXCLUDED_DIRECTORIES = frozenset({".git", ".venv", "__pycache__", "node_modules"})
_EXCLUDED_FILES = frozenset({".DS_Store"})
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
    """Safe user-facing failure that never includes a signed transfer URL."""


@dataclass(frozen=True, slots=True)
class LocalSkillFile:
    """Integrity metadata and local path for one skill file."""

    path: str
    absolute_path: Path
    sha256: str
    size_bytes: int
    content_type: str

    def manifest_payload(self) -> dict[str, str | int]:
        """Return the MCP preparation payload for this file."""

        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
        }


@dataclass(frozen=True, slots=True)
class PreparedUpload:
    """One server-prepared raw-byte upload."""

    path: str
    sha256: str
    size_bytes: int
    content_type: str
    upload_id: str
    upload_url: str
    method: str
    headers: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class UploadPlan:
    """Tracecat MCP response needed to upload and complete a skill draft."""

    workspace_id: str
    skill_id: str
    base_revision: int
    files: tuple[PreparedUpload, ...]


@dataclass(frozen=True, slots=True)
class PreparedDownload:
    """One server-prepared raw-byte download."""

    path: str
    sha256: str
    size_bytes: int
    content_type: str
    download_url: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class DownloadPlan:
    """Tracecat MCP response needed to download a skill draft."""

    workspace_id: str
    skill_id: str
    skill_name: str
    draft_revision: int
    files: tuple[PreparedDownload, ...]


class CliArguments(argparse.Namespace):
    """Typed argparse result shared by the helper subcommands."""

    def __init__(self) -> None:
        super().__init__()
        self.command: str = ""
        self.root: Path = Path()
        self.plan: str | None = None
        self.stdin_plan: bool = False
        self.timeout: float = 60.0
        self.delete_plan: bool = False
        self.delete_extra: bool = False


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
    *,
    require_skill_file: bool = True,
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
            size_bytes = file_path.stat().st_size
            local_files.append(
                LocalSkillFile(
                    path=relative_path,
                    absolute_path=file_path,
                    sha256=_sha256_file(file_path),
                    size_bytes=size_bytes,
                    content_type=_content_type(file_path),
                )
            )

    local_files.sort(key=lambda file: file.path)
    if require_skill_file and not any(file.path == "SKILL.md" for file in local_files):
        raise SkillUploadError("skill root must contain a regular file named SKILL.md")
    return root, tuple(local_files)


def manifest_payload(files: Sequence[LocalSkillFile]) -> dict[str, object]:
    """Return the exact metadata object accepted by prepare_skill_upload."""

    return {"files": [file.manifest_payload() for file in files]}


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise SkillUploadError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], value)


def _as_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise SkillUploadError(f"{label} must be a JSON array")
    return cast(list[object], value)


def _required_string(value: Mapping[str, object], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise SkillUploadError(f"{label}.{key} must be a non-empty string")
    return item


def _required_integer(value: Mapping[str, object], key: str, label: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int):
        raise SkillUploadError(f"{label}.{key} must be an integer")
    return item


def _validated_plan_path(path: str, label: str) -> str:
    if "\\" in path:
        raise SkillUploadError(f"{label}.path must use POSIX separators")
    path_object = PurePosixPath(path)
    if (
        path in {"", "."}
        or path_object.is_absolute()
        or ".." in path_object.parts
        or str(path_object) != path
    ):
        raise SkillUploadError(f"{label}.path is not a normalized relative path")
    return path


def _parse_headers(value: object, label: str) -> tuple[tuple[str, str], ...]:
    mapping = _as_mapping(value, f"{label}.headers")
    headers: list[tuple[str, str]] = []
    for key, item in mapping.items():
        if not isinstance(item, str):
            raise SkillUploadError(f"{label}.headers values must be strings")
        if not key or any(character in key for character in "\r\n"):
            raise SkillUploadError(f"{label}.headers contains an invalid name")
        if any(character in item for character in "\r\n"):
            raise SkillUploadError(f"{label}.headers contains an invalid value")
        headers.append((key, item))
    return tuple(sorted(headers, key=lambda header: header[0].lower()))


def _parse_prepared_upload(value: object, index: int) -> PreparedUpload:
    label = f"plan.files[{index}]"
    mapping = _as_mapping(value, label)
    path = _validated_plan_path(_required_string(mapping, "path", label), label)
    sha256 = _required_string(mapping, "sha256", label).lower()
    if _SHA256_PATTERN.fullmatch(sha256) is None:
        raise SkillUploadError(f"{label}.sha256 must contain 64 hexadecimal characters")
    size_bytes = _required_integer(mapping, "size_bytes", label)
    if size_bytes < 0:
        raise SkillUploadError(f"{label}.size_bytes must be non-negative")
    method = _required_string(mapping, "method", label)
    if method != "PUT":
        raise SkillUploadError(f"{label}.method must be PUT")
    return PreparedUpload(
        path=path,
        sha256=sha256,
        size_bytes=size_bytes,
        content_type=_required_string(mapping, "content_type", label),
        upload_id=_required_string(mapping, "upload_id", label),
        upload_url=_required_string(mapping, "upload_url", label),
        method=method,
        headers=_parse_headers(mapping.get("headers"), label),
    )


def _parse_prepared_download(value: object, index: int) -> PreparedDownload:
    label = f"plan.files[{index}]"
    mapping = _as_mapping(value, label)
    path = _validated_plan_path(_required_string(mapping, "path", label), label)
    sha256 = _required_string(mapping, "sha256", label).lower()
    if _SHA256_PATTERN.fullmatch(sha256) is None:
        raise SkillUploadError(f"{label}.sha256 must contain 64 hexadecimal characters")
    size_bytes = _required_integer(mapping, "size_bytes", label)
    if size_bytes < 0:
        raise SkillUploadError(f"{label}.size_bytes must be non-negative")
    return PreparedDownload(
        path=path,
        sha256=sha256,
        size_bytes=size_bytes,
        content_type=_required_string(mapping, "content_type", label),
        download_url=_required_string(mapping, "download_url", label),
        expires_at=_required_string(mapping, "expires_at", label),
    )


def _load_json(file_handle: TextIO, label: str) -> object:
    try:
        return cast(object, json.load(file_handle))
    except json.JSONDecodeError as exc:
        raise SkillUploadError(f"{label} is not valid JSON: {exc.msg}") from exc


def load_upload_plan(plan_value: str | Path) -> UploadPlan:
    """Load and validate a prepare_skill_upload response."""

    if str(plan_value) == "-":
        raw_plan = _load_json(sys.stdin, "stdin upload plan")
    else:
        plan_path = Path(plan_value).expanduser()
        try:
            with plan_path.open(encoding="utf-8") as file_handle:
                raw_plan = _load_json(file_handle, f"upload plan {plan_path}")
        except OSError as exc:
            raise SkillUploadError(f"cannot read upload plan: {plan_path}") from exc

    mapping = _as_mapping(raw_plan, "plan")
    raw_files = _as_list(mapping.get("files"), "plan.files")
    if not raw_files:
        raise SkillUploadError("plan.files must contain at least one upload")
    files = tuple(
        _parse_prepared_upload(raw_file, index)
        for index, raw_file in enumerate(raw_files)
    )
    paths = [file.path for file in files]
    if len(paths) != len(set(paths)):
        raise SkillUploadError("plan.files contains duplicate paths")
    if "SKILL.md" not in paths:
        raise SkillUploadError("plan.files must include root SKILL.md")

    base_revision = _required_integer(mapping, "base_revision", "plan")
    if base_revision < 0:
        raise SkillUploadError("plan.base_revision must be non-negative")
    return UploadPlan(
        workspace_id=_required_string(mapping, "workspace_id", "plan"),
        skill_id=_required_string(mapping, "skill_id", "plan"),
        base_revision=base_revision,
        files=files,
    )


def load_download_plan(plan_value: str | Path) -> DownloadPlan:
    """Load and validate a prepare_skill_download response."""

    if str(plan_value) == "-":
        raw_plan = _load_json(sys.stdin, "stdin download plan")
    else:
        plan_path = Path(plan_value).expanduser()
        try:
            with plan_path.open(encoding="utf-8") as file_handle:
                raw_plan = _load_json(file_handle, f"download plan {plan_path}")
        except OSError as exc:
            raise SkillUploadError(f"cannot read download plan: {plan_path}") from exc

    mapping = _as_mapping(raw_plan, "plan")
    raw_files = _as_list(mapping.get("files"), "plan.files")
    if not raw_files:
        raise SkillUploadError("plan.files must contain at least one download")
    files = tuple(
        _parse_prepared_download(raw_file, index)
        for index, raw_file in enumerate(raw_files)
    )
    paths = [file.path for file in files]
    if len(paths) != len(set(paths)):
        raise SkillUploadError("plan.files contains duplicate paths")
    if "SKILL.md" not in paths:
        raise SkillUploadError("plan.files must include root SKILL.md")

    draft_revision = _required_integer(mapping, "draft_revision", "plan")
    if draft_revision < 0:
        raise SkillUploadError("plan.draft_revision must be non-negative")
    return DownloadPlan(
        workspace_id=_required_string(mapping, "workspace_id", "plan"),
        skill_id=_required_string(mapping, "skill_id", "plan"),
        skill_name=_required_string(mapping, "skill_name", "plan"),
        draft_revision=draft_revision,
        files=files,
    )


def _validated_upload_url(upload: PreparedUpload) -> SplitResult:
    parsed = urlsplit(upload.upload_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise SkillUploadError(f"invalid HTTP upload URL for {upload.path}")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise SkillUploadError(f"unsafe HTTP upload URL for {upload.path}")
    return parsed


def _validated_download_url(download: PreparedDownload) -> SplitResult:
    parsed = urlsplit(download.download_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise SkillUploadError(f"invalid HTTP download URL for {download.path}")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise SkillUploadError(f"unsafe HTTP download URL for {download.path}")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise SkillUploadError(
            f"invalid HTTP download URL for {download.path}"
        ) from exc
    return parsed


def _content_length_headers(upload: PreparedUpload) -> dict[str, str]:
    headers = dict(upload.headers)
    content_length_key = next(
        (key for key in headers if key.lower() == "content-length"), None
    )
    if content_length_key is not None:
        if headers[content_length_key] != str(upload.size_bytes):
            raise SkillUploadError(
                f"invalid Content-Length in upload plan for {upload.path}"
            )
    else:
        headers["Content-Length"] = str(upload.size_bytes)
    return headers


def _upload_file(
    local_file: LocalSkillFile,
    upload: PreparedUpload,
    *,
    timeout_seconds: float,
) -> None:
    parsed = _validated_upload_url(upload)
    hostname = parsed.hostname
    if hostname is None:
        raise SkillUploadError(f"invalid HTTP upload URL for {upload.path}")
    target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    headers = _content_length_headers(upload)
    if parsed.scheme == "https":
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            hostname,
            parsed.port,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        )
    else:
        connection = http.client.HTTPConnection(
            hostname,
            parsed.port,
            timeout=timeout_seconds,
        )

    try:
        with local_file.absolute_path.open("rb") as file_handle:
            connection.request(upload.method, target, body=file_handle, headers=headers)
            response = connection.getresponse()
            _ = response.read(1024)
        if not 200 <= response.status < 300:
            response_status = f"{response.status} {response.reason}"
            raise SkillUploadError(
                f"HTTP upload failed for {upload.path}: status {response_status}"
            )
    except SkillUploadError:
        raise
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise SkillUploadError(
            f"HTTP upload failed for {upload.path}: {type(exc).__name__}"
        ) from exc
    finally:
        connection.close()


def _prepare_download_root(root_value: str | Path) -> Path:
    root_input = Path(root_value).expanduser()
    if root_input.is_symlink():
        raise SkillUploadError(
            f"symlinked target directory is not allowed: {root_input}"
        )
    try:
        root_input.mkdir(parents=True, exist_ok=True)
        root = root_input.resolve(strict=True)
    except OSError as exc:
        raise SkillUploadError(
            f"cannot create download target directory: {root_input}"
        ) from exc
    if not root.is_dir():
        raise SkillUploadError(f"download target is not a directory: {root}")
    _, _ = discover_skill_files(root, require_skill_file=False)
    return root


def _prepare_download_path(root: Path, relative_path: str) -> Path:
    path = root
    for part in PurePosixPath(relative_path).parts[:-1]:
        path /= part
        try:
            path_status = path.lstat()
        except FileNotFoundError:
            try:
                path.mkdir()
            except OSError as exc:
                raise SkillUploadError(
                    f"cannot create parent directory for {relative_path}"
                ) from exc
            continue
        except OSError as exc:
            raise SkillUploadError(
                f"cannot inspect parent directory for {relative_path}"
            ) from exc
        if stat.S_ISLNK(path_status.st_mode):
            raise SkillUploadError(
                f"symlinked path is not allowed while downloading: {relative_path}"
            )
        if not stat.S_ISDIR(path_status.st_mode):
            raise SkillUploadError(
                f"non-directory parent is not allowed while downloading: {relative_path}"
            )

    destination = root / relative_path
    try:
        destination_status = destination.lstat()
    except FileNotFoundError:
        return destination
    except OSError as exc:
        raise SkillUploadError(
            f"cannot inspect download target: {relative_path}"
        ) from exc
    if stat.S_ISLNK(destination_status.st_mode):
        raise SkillUploadError(
            f"symlinked file is not allowed while downloading: {relative_path}"
        )
    if not stat.S_ISREG(destination_status.st_mode):
        raise SkillUploadError(
            f"non-regular file is not allowed while downloading: {relative_path}"
        )
    return destination


def _delete_bad_download(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _download_file(
    destination: Path,
    download: PreparedDownload,
    *,
    timeout_seconds: float,
) -> None:
    parsed = _validated_download_url(download)
    hostname = parsed.hostname
    if hostname is None:
        raise SkillUploadError(f"invalid HTTP download URL for {download.path}")
    target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    if parsed.scheme == "https":
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            hostname,
            parsed.port,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        )
    else:
        connection = http.client.HTTPConnection(
            hostname,
            parsed.port,
            timeout=timeout_seconds,
        )

    wrote_destination = False
    try:
        connection.request("GET", target)
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            _ = response.read(1024)
            response_status = f"{response.status} {response.reason}"
            raise SkillUploadError(
                f"HTTP download failed for {download.path}: status {response_status}"
            )

        hasher = hashlib.sha256()
        size_bytes = 0
        with destination.open("wb") as file_handle:
            wrote_destination = True
            while chunk := response.read(_CHUNK_SIZE_BYTES):
                file_handle.write(chunk)
                hasher.update(chunk)
                size_bytes += len(chunk)
        if size_bytes != download.size_bytes:
            raise SkillUploadError(
                f"download size mismatch for {download.path}: "
                f"expected {download.size_bytes}, received {size_bytes}"
            )
        if hasher.hexdigest() != download.sha256:
            raise SkillUploadError(f"download SHA-256 mismatch for {download.path}")
    except SkillUploadError:
        if wrote_destination:
            _delete_bad_download(destination)
        raise
    except (OSError, http.client.HTTPException, ValueError) as exc:
        if wrote_destination:
            _delete_bad_download(destination)
        raise SkillUploadError(
            f"HTTP download failed for {download.path}: {type(exc).__name__}"
        ) from exc
    finally:
        connection.close()


def download_from_plan(
    root_value: str | Path,
    plan_value: str | Path,
    *,
    delete_extra: bool,
    timeout_seconds: float = 60.0,
) -> dict[str, object]:
    """Reconcile a local directory with a prepared skill download."""

    plan = load_download_plan(plan_value)
    root = _prepare_download_root(root_value)
    downloaded: list[str] = []
    skipped: list[str] = []
    for download in plan.files:
        destination = _prepare_download_path(root, download.path)
        if destination.exists() and _sha256_file(destination) == download.sha256:
            print(f"{download.path}: skipped (up-to-date)", file=sys.stderr)
            skipped.append(download.path)
            continue
        _download_file(
            destination,
            download,
            timeout_seconds=timeout_seconds,
        )
        downloaded.append(download.path)

    deleted: list[str] = []
    if delete_extra:
        _, local_files = discover_skill_files(root)
        plan_paths = {download.path for download in plan.files}
        for local_file in local_files:
            if local_file.path not in plan_paths:
                try:
                    local_file.absolute_path.unlink()
                except OSError as exc:
                    raise SkillUploadError(
                        f"cannot delete extra file: {local_file.path}"
                    ) from exc
                deleted.append(local_file.path)

    return {
        "downloaded": downloaded,
        "skipped": skipped,
        "deleted": deleted,
        "draft_revision": plan.draft_revision,
    }


def _match_plan_to_local_files(
    local_files: Sequence[LocalSkillFile],
    plan: UploadPlan,
) -> tuple[tuple[LocalSkillFile, PreparedUpload], ...]:
    local_by_path = {file.path: file for file in local_files}
    plan_by_path = {file.path: file for file in plan.files}
    missing_paths = sorted(set(plan_by_path) - set(local_by_path))
    extra_paths = sorted(set(local_by_path) - set(plan_by_path))
    if missing_paths or extra_paths:
        details: list[str] = []
        if missing_paths:
            details.append(f"missing locally: {', '.join(missing_paths)}")
        if extra_paths:
            details.append(f"not present in plan: {', '.join(extra_paths)}")
        raise SkillUploadError(
            f"local skill tree changed after preparation ({'; '.join(details)})"
        )

    matches: list[tuple[LocalSkillFile, PreparedUpload]] = []
    for upload in plan.files:
        local_file = local_by_path[upload.path]
        if local_file.sha256 != upload.sha256:
            raise SkillUploadError(
                f"local file changed after preparation (SHA-256): {upload.path}"
            )
        if local_file.size_bytes != upload.size_bytes:
            raise SkillUploadError(
                f"local file changed after preparation (size): {upload.path}"
            )
        if local_file.content_type != upload.content_type:
            raise SkillUploadError(
                f"local file content type differs from upload plan: {upload.path}"
            )
        matches.append((local_file, upload))
    return tuple(matches)


def upload_from_plan(
    root_value: str | Path,
    plan_value: str | Path,
    *,
    timeout_seconds: float,
) -> dict[str, object]:
    """Verify the local tree, stream raw bytes, and return completion arguments."""

    _, local_files = discover_skill_files(root_value)
    plan = load_upload_plan(plan_value)
    matches = _match_plan_to_local_files(local_files, plan)
    for local_file, upload in matches:
        _upload_file(local_file, upload, timeout_seconds=timeout_seconds)
    return {
        "workspace_id": plan.workspace_id,
        "skill_id": plan.skill_id,
        "base_revision": plan.base_revision,
        "files": [
            {"path": upload.path, "upload_id": upload.upload_id}
            for upload in plan.files
        ],
    }


def _write_json(value: object) -> None:
    json.dump(value, sys.stdout, indent=2, sort_keys=True)
    _ = sys.stdout.write("\n")


def _warn_if_plan_permissions_are_broad(
    plan_value: str | Path, *, plan_kind: str
) -> None:
    if str(plan_value) == "-":
        return
    plan_path = Path(plan_value).expanduser()
    try:
        mode = stat.S_IMODE(plan_path.stat().st_mode)
    except OSError:
        return
    if mode & 0o077:
        print(
            f"warning: {plan_kind} plan is readable by other users; prefer mode 0600",
            file=sys.stderr,
        )


def _delete_plan_best_effort(plan_value: str | Path) -> None:
    if str(plan_value) == "-":
        print(
            "warning: --delete-plan has no effect when reading stdin", file=sys.stderr
        )
        return
    plan_path = Path(plan_value).expanduser()
    try:
        plan_path.unlink()
    except OSError as exc:
        print(
            f"warning: could not delete upload plan {plan_path}: {type(exc).__name__}",
            file=sys.stderr,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload Tracecat skill files without base64 or MCP credentials."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser(
        "manifest", help="emit file metadata for prepare_skill_upload"
    )
    _ = manifest_parser.add_argument("root", type=Path, help="local skill directory")

    upload_parser = subparsers.add_parser(
        "upload", help="stream files using a prepare_skill_upload response"
    )
    _ = upload_parser.add_argument("root", type=Path, help="local skill directory")
    _ = upload_parser.add_argument(
        "--plan",
        required=True,
        help="prepare response JSON file, or '-' to read stdin",
    )
    _ = upload_parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="per-file HTTP timeout in seconds (default: 60)",
    )
    _ = upload_parser.add_argument(
        "--delete-plan",
        action="store_true",
        help="delete the signed upload plan after all PUTs succeed",
    )

    download_parser = subparsers.add_parser(
        "download", help="sync files using a prepare_skill_download response"
    )
    _ = download_parser.add_argument(
        "root", type=Path, metavar="target-dir", help="local target directory"
    )
    plan_group = download_parser.add_mutually_exclusive_group(required=True)
    _ = plan_group.add_argument(
        "--plan",
        help="prepare response JSON file, or '-' to read stdin",
    )
    _ = plan_group.add_argument(
        "--stdin-plan",
        action="store_true",
        help="read the prepare response JSON from stdin (preferred)",
    )
    _ = download_parser.add_argument(
        "--delete-extra",
        action="store_true",
        help="delete non-ignored local files absent from the plan",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv, namespace=CliArguments())
    try:
        if args.command == "manifest":
            _, files = discover_skill_files(args.root)
            _write_json(manifest_payload(files))
            return 0
        if args.command == "upload":
            if args.timeout <= 0:
                raise SkillUploadError("--timeout must be greater than zero")
            if args.plan is None:
                raise SkillUploadError("--plan is required")
            _warn_if_plan_permissions_are_broad(args.plan, plan_kind="upload")
            completion = upload_from_plan(
                args.root,
                args.plan,
                timeout_seconds=args.timeout,
            )
            if args.delete_plan:
                _delete_plan_best_effort(args.plan)
            _write_json(completion)
            return 0
        plan_value = "-" if args.stdin_plan else args.plan
        if plan_value is None:
            raise SkillUploadError("--plan or --stdin-plan is required")
        _warn_if_plan_permissions_are_broad(plan_value, plan_kind="download")
        summary = download_from_plan(
            args.root,
            plan_value,
            delete_extra=args.delete_extra,
        )
        _write_json(summary)
        return 0
    except SkillUploadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
