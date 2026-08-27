from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

_SKILL_MARKDOWN = "---\nname: example-skill\ndescription: Example\n---\n"


def _load_uploader() -> ModuleType:
    script_path = (
        Path(__file__).parents[1]
        / "plugins"
        / "tracecat"
        / "skills"
        / "tracecat-manage-skills"
        / "scripts"
        / "upload_skill_files.py"
    )
    spec = importlib.util.spec_from_file_location(
        "tracecat_upload_skill_files", script_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


uploader = _load_uploader()


def _write_example_skill(root: Path) -> bytes:
    """Create a skill tree with a binary file and an empty file."""

    (root / "scripts").mkdir(parents=True)
    (root / "SKILL.md").write_text(_SKILL_MARKDOWN, encoding="utf-8")
    binary_content = b"\x00\xffraw-binary\x10"
    (root / "scripts" / "payload.bin").write_bytes(binary_content)
    (root / "scripts" / "__init__.py").write_bytes(b"")
    return binary_content


def _run_manifest(root: Path, output: Path) -> int:
    """Run the manifest subcommand without leaking its summary into test output."""

    with contextlib.redirect_stdout(io.StringIO()):
        return int(uploader.main(["manifest", str(root), "--output", str(output)]))


class SkillUploadHelperTests(unittest.TestCase):
    def test_manifest_preserves_raw_binary_and_empty_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "example-skill"
            binary_content = _write_example_skill(root)

            _, local_files = uploader.discover_skill_files(root)
            payload = uploader.manifest_payload(local_files)

            self.assertEqual(
                [file["path"] for file in payload["files"]],
                ["SKILL.md", "scripts/__init__.py", "scripts/payload.bin"],
            )
            self.assertEqual(payload["file_count"], 3)
            self.assertEqual(
                payload["total_size_bytes"],
                len(_SKILL_MARKDOWN.encode("utf-8")) + len(binary_content),
            )
            self.assertEqual(payload["digests"][1]["size_bytes"], 0)
            self.assertEqual(payload["files"][1]["content_base64"], "")
            self.assertEqual(
                base64.b64decode(payload["files"][2]["content_base64"], validate=True),
                binary_content,
            )
            self.assertEqual(
                payload["files"][2]["content_type"], "application/octet-stream"
            )

    def test_manifest_entries_match_upload_skill_file_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "example-skill"
            _ = _write_example_skill(root)

            _, local_files = uploader.discover_skill_files(root)
            payload = uploader.manifest_payload(local_files)

            for entry in payload["files"]:
                self.assertEqual(
                    sorted(entry), ["content_base64", "content_type", "path"]
                )
                self.assertIsInstance(entry["path"], str)
                self.assertIsInstance(entry["content_base64"], str)
                self.assertIsInstance(entry["content_type"], str)
                self.assertNotIn("\\", entry["path"])
                self.assertFalse(entry["path"].startswith("/"))

    def test_manifest_digests_match_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "example-skill"
            _ = _write_example_skill(root)

            _, local_files = uploader.discover_skill_files(root)
            payload = uploader.manifest_payload(local_files)

            for digest in payload["digests"]:
                source = (root / digest["path"]).read_bytes()
                self.assertEqual(digest["sha256"], hashlib.sha256(source).hexdigest())
                self.assertEqual(digest["size_bytes"], len(source))

    def test_emitted_payload_round_trips_against_source_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "example-skill"
            _ = _write_example_skill(root)
            payload_path = Path(temporary_directory) / "payload.json"

            self.assertEqual(_run_manifest(root, payload_path), 0)
            self.assertEqual(payload_path.stat().st_mode & 0o777, 0o600)

            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            for entry in payload["files"]:
                self.assertEqual(
                    base64.b64decode(entry["content_base64"], validate=True),
                    (root / entry["path"]).read_bytes(),
                )

            result = uploader.verify_payload(root, payload_path)
            self.assertTrue(result["verified"])
            self.assertEqual(result["file_count"], 3)

    def test_verify_rejects_tree_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "example-skill"
            _ = _write_example_skill(root)
            payload_path = Path(temporary_directory) / "payload.json"
            self.assertEqual(_run_manifest(root, payload_path), 0)

            (root / "new-file.txt").write_text("added", encoding="utf-8")
            with self.assertRaisesRegex(
                uploader.SkillUploadError,
                "payload does not match the local skill tree",
            ):
                uploader.verify_payload(root, payload_path)

            (root / "new-file.txt").unlink()
            (root / "SKILL.md").write_text(
                f"{_SKILL_MARKDOWN}changed\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                uploader.SkillUploadError,
                "decoded bytes differ from source file",
            ):
                uploader.verify_payload(root, payload_path)

    def test_discovery_rejects_symlinked_files_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "example-skill"
            root.mkdir()
            (root / "SKILL.md").write_text(_SKILL_MARKDOWN, encoding="utf-8")
            outside = Path(temporary_directory) / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            (root / "linked.txt").symlink_to(outside)

            with self.assertRaisesRegex(
                uploader.SkillUploadError,
                "symlinked file is not allowed",
            ):
                uploader.discover_skill_files(root)

            (root / "linked.txt").unlink()
            outside_directory = Path(temporary_directory) / "outside-dir"
            outside_directory.mkdir()
            (outside_directory / "leaked.txt").write_text("leaked", encoding="utf-8")
            (root / "linked-dir").symlink_to(outside_directory)

            with self.assertRaisesRegex(
                uploader.SkillUploadError,
                "symlinked directory is not allowed",
            ):
                uploader.discover_skill_files(root)

    def test_discovery_requires_root_skill_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "example-skill"
            (root / "references").mkdir(parents=True)
            (root / "references" / "SKILL.md").write_text(
                _SKILL_MARKDOWN, encoding="utf-8"
            )

            with self.assertRaisesRegex(
                uploader.SkillUploadError,
                "must contain a regular file named SKILL.md",
            ):
                uploader.discover_skill_files(root)


if __name__ == "__main__":
    unittest.main()
