from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "scripts"
ADAPTER_SCRIPTS = ROOT / "skills" / "douyin-cloud-download" / "scripts"
for path in (SCRIPTS, ADAPTER_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dcd_setup.release import load_release_config
from dcd_setup.rollback import rollback, snapshot_current_release, write_current_release
from dcd_core.diagnostics import create_diagnostic_bundle
from dcd_core.state import CURRENT_JOB_SCHEMA, load_and_migrate


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


setup = load_module("maturity_setup_controller", SCRIPTS / "setup.py")
adapter = load_module("maturity_douyin_cloud", ADAPTER_SCRIPTS / "douyin_cloud.py")


class _BytesResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class ProductMaturityTests(unittest.TestCase):
    def test_release_lock_is_valid_and_rejects_bad_quark_digest(self):
        config = load_release_config(ROOT)
        self.assertEqual(config.product_version, "1.0.0")
        self.assertEqual(len(config.douk_commit), 40)
        self.assertEqual(len(config.quark_sha256), 64)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "VERSION").write_text("1.0.0\n", encoding="utf-8")
            lock = json.loads((ROOT / "UPSTREAMS.lock.json").read_text(encoding="utf-8"))
            lock["quark"]["sha256"] = "not-a-sha256"
            (root / "UPSTREAMS.lock.json").write_text(json.dumps(lock), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "quark.sha256"):
                load_release_config(root)

    def test_quark_install_rejects_unreviewed_package_before_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            fake = _BytesResponse(b"unreviewed-package")
            with mock.patch.object(setup, "official_quark_config", return_value=(setup.QUARK_VERSION, "https://pdds.quark.cn/skill.zip")), mock.patch.object(
                setup.urllib.request, "urlopen", return_value=fake
            ):
                with self.assertRaisesRegex(RuntimeError, "SHA256 does not match"):
                    setup.install_quark(home)
            self.assertFalse((home / "skills" / "quarkclouddrive").exists())

    def test_legacy_manifest_migrates_and_writes_back_atomically(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "job_id": "job-1",
                        "status": "failed",
                        "requested_destinations": ["quark", "baidu"],
                        "error": {"name": "upstream_failed", "message": "network"},
                    }
                ),
                encoding="utf-8",
            )
            migrated, changed = load_and_migrate(path)
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(changed)
            self.assertEqual(migrated["schema_version"], CURRENT_JOB_SCHEMA)
            self.assertEqual(persisted["schema_version"], CURRENT_JOB_SCHEMA)
            self.assertEqual(persisted["error"]["code"], "DCD-DOWNLOAD-010")
            self.assertEqual(persisted["uploads"]["quark"]["status"], "pending")
            self.assertEqual(persisted["uploads"]["baidu"]["status"], "pending")

    def test_rollback_restores_program_and_runtime_but_preserves_mutable_state(self):
        commit = "a" * 40
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            skill = home / "skills" / "douyin-cloud-download"
            quark = home / "skills" / "quarkclouddrive"
            (skill / "scripts").mkdir(parents=True)
            (quark / "codex").mkdir(parents=True)
            (skill / "scripts" / "program.txt").write_text("old-program", encoding="utf-8")
            (quark / "SKILL.md").write_text("old-quark", encoding="utf-8")
            (quark / "codex" / "auth.json").write_text("old-auth", encoding="utf-8")

            runtime = home / "state" / "douyin-cloud-download" / "upstream" / commit[:12]
            (runtime / "Volume").mkdir(parents=True)
            (runtime / "code.txt").write_text("old-runtime", encoding="utf-8")
            (runtime / "Volume" / "settings.json").write_text("old-user-state", encoding="utf-8")
            (runtime / "encipher.py").write_text("old-encipher", encoding="utf-8")
            write_current_release(home, {"schema_version": 1, "product_version": "0.9.0", "upstreams": {"douk": {"commit": commit}}})

            snap = snapshot_current_release(home)
            assert snap is not None
            (skill / "scripts" / "program.txt").write_text("new-program", encoding="utf-8")
            (quark / "SKILL.md").write_text("new-quark", encoding="utf-8")
            (quark / "codex" / "auth.json").write_text("new-auth", encoding="utf-8")
            (runtime / "code.txt").write_text("new-runtime", encoding="utf-8")
            (runtime / "Volume" / "settings.json").write_text("new-user-state", encoding="utf-8")
            (runtime / "encipher.py").write_text("new-encipher", encoding="utf-8")

            result = rollback(home, str(snap["snapshot_id"]))
            self.assertTrue(result["ok"])
            self.assertEqual((skill / "scripts" / "program.txt").read_text(encoding="utf-8"), "old-program")
            self.assertEqual((quark / "SKILL.md").read_text(encoding="utf-8"), "old-quark")
            self.assertEqual((runtime / "code.txt").read_text(encoding="utf-8"), "old-runtime")
            self.assertEqual((quark / "codex" / "auth.json").read_text(encoding="utf-8"), "new-auth")
            self.assertEqual((runtime / "Volume" / "settings.json").read_text(encoding="utf-8"), "new-user-state")
            self.assertEqual((runtime / "encipher.py").read_text(encoding="utf-8"), "new-encipher")

    def test_error_protocol_keeps_legacy_name_and_adds_stable_metadata(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(adapter, "state_root", return_value=Path(temp)):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = adapter.fail("upstream_failed", "temporary failure")
            payload = json.loads(stream.getvalue().strip())
            self.assertEqual(code, 2)
            self.assertEqual(payload["error"], "upstream_failed")
            self.assertEqual(payload["error_code"], "DCD-DOWNLOAD-010")
            self.assertTrue(payload["retryable"])
            self.assertTrue(payload["recovery"])

    def test_diagnostic_bundle_redacts_secrets_and_carries_release_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            state = home / "state" / "douyin-cloud-download"
            logs = state / "logs"
            jobs = state / "jobs" / "job-1"
            skill = home / "skills" / "douyin-cloud-download"
            logs.mkdir(parents=True)
            jobs.mkdir(parents=True)
            skill.mkdir(parents=True)
            (logs / "douyin-cloud-download.jsonl").write_text(
                json.dumps({"Cookie": "secret-cookie", "url": "https://example.com/private", "access_token": "token-123"}) + "\n",
                encoding="utf-8",
            )
            (jobs / "manifest.json").write_text(json.dumps({"BDUSS": "secret-bduss", "job_id": "job-1"}), encoding="utf-8")
            (skill / "PRODUCT_VERSION").write_text("1.0.0\n", encoding="utf-8")
            (skill / "UPSTREAMS.lock.json").write_text((ROOT / "UPSTREAMS.lock.json").read_text(encoding="utf-8"), encoding="utf-8")

            bundle = create_diagnostic_bundle(state, {"ready": False, "Authorization": "Bearer secret-auth"})
            with zipfile.ZipFile(bundle) as zf:
                names = set(zf.namelist())
                content = "\n".join(zf.read(name).decode("utf-8", errors="replace") for name in names)
            self.assertIn("release/PRODUCT_VERSION", names)
            self.assertIn("release/UPSTREAMS.lock.json", names)
            self.assertIn("1.0.0", content)
            for secret in ("secret-cookie", "token-123", "secret-bduss", "secret-auth", "https://example.com/private"):
                self.assertNotIn(secret, content)

    def test_baidu_installer_is_fail_closed_when_checksum_cannot_be_verified(self):
        text = (ROOT / "skills" / "baidu-drive" / "scripts" / "install.sh").read_text(encoding="utf-8-sig")
        self.assertIn("未找到 sha256sum/shasum，无法验证安装器完整性", text)
        self.assertIn("无可信 SHA256 校验值，拒绝执行安装器", text)
        self.assertGreaterEqual(text.count("exit 1"), 2)


if __name__ == "__main__":
    unittest.main()
