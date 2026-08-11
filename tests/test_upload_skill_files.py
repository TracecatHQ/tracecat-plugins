from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any


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


class SkillUploadHelperTests(unittest.TestCase):
    def test_manifest_and_upload_preserve_raw_binary_and_empty_files(self) -> None:
        received: dict[str, tuple[bytes, str | None]] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_PUT(self) -> None:
                content_length = int(self.headers["Content-Length"])
                received[self.path] = (
                    self.rfile.read(content_length),
                    self.headers.get("Content-Type"),
                )
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:
                del format, args

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "example-skill"
            (root / "scripts").mkdir(parents=True)
            (root / "SKILL.md").write_text(
                "---\nname: example-skill\ndescription: Example\n---\n",
                encoding="utf-8",
            )
            binary_content = b"\x00\xffraw-binary\x10"
            (root / "scripts" / "payload.bin").write_bytes(binary_content)
            (root / "scripts" / "__init__.py").write_bytes(b"")

            _, local_files = uploader.discover_skill_files(root)
            manifest = uploader.manifest_payload(local_files)
            self.assertEqual(
                [file["path"] for file in manifest["files"]],
                ["SKILL.md", "scripts/__init__.py", "scripts/payload.bin"],
            )
            self.assertEqual(manifest["files"][1]["size_bytes"], 0)

            port = server.server_address[1]
            plan_files = []
            for index, file in enumerate(local_files):
                plan_files.append(
                    {
                        **file.manifest_payload(),
                        "upload_id": f"00000000-0000-0000-0000-{index:012d}",
                        "upload_url": (
                            f"http://127.0.0.1:{port}/upload/{index}?signature=secret"
                        ),
                        "method": "PUT",
                        "headers": {"Content-Type": file.content_type},
                        "expires_at": "2099-01-01T00:00:00Z",
                    }
                )
            plan = {
                "workspace_id": "11111111-1111-1111-1111-111111111111",
                "skill_id": "22222222-2222-2222-2222-222222222222",
                "base_revision": 7,
                "created": False,
                "files": plan_files,
            }
            plan_path = Path(temporary_directory) / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            plan_path.chmod(0o600)

            completion = uploader.upload_from_plan(
                root,
                plan_path,
                timeout_seconds=5,
            )

        self.assertEqual(received["/upload/1?signature=secret"][0], b"")
        self.assertEqual(
            received["/upload/2?signature=secret"],
            (binary_content, "application/octet-stream"),
        )
        self.assertEqual(completion["base_revision"], 7)
        self.assertEqual(
            [file["path"] for file in completion["files"]],
            ["SKILL.md", "scripts/__init__.py", "scripts/payload.bin"],
        )
        self.assertTrue(
            all("content_base64" not in file for file in completion["files"])
        )

    def test_upload_rejects_tree_drift_before_http(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "example-skill"
            root.mkdir()
            (root / "SKILL.md").write_text(
                "---\nname: example-skill\ndescription: Example\n---\n",
                encoding="utf-8",
            )
            _, local_files = uploader.discover_skill_files(root)
            local_file = local_files[0]
            plan = {
                "workspace_id": "11111111-1111-1111-1111-111111111111",
                "skill_id": "22222222-2222-2222-2222-222222222222",
                "base_revision": 1,
                "files": [
                    {
                        **local_file.manifest_payload(),
                        "upload_id": "33333333-3333-3333-3333-333333333333",
                        "upload_url": "http://127.0.0.1:1/unused?signature=secret",
                        "method": "PUT",
                        "headers": {"Content-Type": local_file.content_type},
                    }
                ],
            }
            plan_path = Path(temporary_directory) / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            (root / "new-file.txt").write_text("changed", encoding="utf-8")

            with self.assertRaisesRegex(
                uploader.SkillUploadError,
                "local skill tree changed after preparation",
            ):
                uploader.upload_from_plan(root, plan_path, timeout_seconds=1)

    def test_manifest_rejects_symlinked_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "example-skill"
            root.mkdir()
            (root / "SKILL.md").write_text(
                "---\nname: example-skill\ndescription: Example\n---\n",
                encoding="utf-8",
            )
            outside = Path(temporary_directory) / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            (root / "linked.txt").symlink_to(outside)

            with self.assertRaisesRegex(
                uploader.SkillUploadError,
                "symlinked file is not allowed",
            ):
                uploader.discover_skill_files(root)


if __name__ == "__main__":
    unittest.main()
