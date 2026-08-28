from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "douyin_cloud.py"
SPEC = importlib.util.spec_from_file_location("douyin_cloud", SCRIPT)
dc = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(dc)


class ClassificationTests(unittest.TestCase):
    def test_classifies_full_links(self):
        self.assertEqual(dc.classify_url("https://www.douyin.com/video/1"), "works")
        self.assertEqual(dc.classify_url("https://www.douyin.com/note/1"), "works")
        self.assertEqual(dc.classify_url("https://www.douyin.com/user/a"), "account")
        self.assertEqual(dc.classify_url("https://www.douyin.com/user/a?modal_id=1"), "works")
        self.assertEqual(dc.classify_url("https://www.douyin.com/collection/1"), "mix")
        self.assertEqual(dc.classify_url("https://live.douyin.com/123"), "live")

    def test_auto_groups_and_deduplicates(self):
        urls = [
            "https://www.douyin.com/video/1",
            "https://www.douyin.com/user/a",
            "https://www.douyin.com/video/1",
            "https://www.douyin.com/collection/2",
        ]
        groups = dc.grouped_urls("auto", urls)
        self.assertEqual(groups["works"], [urls[0]])
        self.assertEqual(groups["account"], [urls[1]])
        self.assertEqual(groups["mix"], [urls[3]])

    def test_rejects_non_douyin_url(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            dc.validate_url("https://www.tiktok.com/video/1")

    def test_defaults_to_author_folder_layout(self):
        args = dc.build_parser().parse_args(["download", "--mode", "saved-music"])
        manifest = dc.new_manifest(args, "abcdef123456", Path("payload"))
        self.assertEqual(dc.DEFAULT_CLOUD_ROOT, "抖音下载")
        self.assertEqual(manifest["cloud_root"], "抖音下载")
        self.assertEqual(manifest["cloud_layout"], "./抖音下载/[作者]")
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            dc.build_parser().parse_args(["download", "--mode", "saved-music", "--remote-dir", "other"])


class ArgumentTests(unittest.TestCase):
    def namespace(self, **updates):
        data = {
            "mode": "works", "url": ["https://www.douyin.com/video/1"],
            "selector": [], "earliest": None, "latest": None, "pages": None,
            "account_tab": "post",
        }
        data.update(updates)
        return argparse.Namespace(**data)

    def test_saved_folder_requires_scope(self):
        with self.assertRaisesRegex(dc.SkillError, "Select a saved folder"):
            dc.validate_download_args(self.namespace(mode="saved-folders", url=[]))

    def test_account_date_range(self):
        with self.assertRaisesRegex(dc.SkillError, "earliest"):
            dc.validate_download_args(self.namespace(mode="account", earliest="2026-08-02", latest="2026-08-01"))

    def test_non_account_options_rejected(self):
        with self.assertRaisesRegex(dc.SkillError, "Account"):
            dc.validate_download_args(self.namespace(account_tab="favorite"))


class PayloadTests(unittest.TestCase):
    def test_runtime_commit_accepts_a_vendored_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            (runtime / dc.RUNTIME_COMMIT_FILE).write_text(dc.PINNED_COMMIT + "\n", encoding="utf-8")
            self.assertEqual(dc.runtime_commit(runtime), dc.PINNED_COMMIT)

    def test_inventory_core_media_live_photo_music_and_cover(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = {
                "video.mp4": b"video",
                "album/01.jpg": b"image",
                "live-photo/clip.mov": b"live-photo",
                "music/song.mp3": b"music",
                "covers/static-cover.webp": b"cover",
                "metadata.json": b"must not upload as media",
            }
            for relative, content in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            found = dc.inventory(root)
            self.assertEqual(len(found), 5)
            kinds = {item["path"]: item["media_type"] for item in found}
            self.assertEqual(kinds["video.mp4"], "video")
            self.assertEqual(kinds["album/01.jpg"], "image")
            self.assertEqual(kinds["music/song.mp3"], "music")
            self.assertEqual(kinds["covers/static-cover.webp"], "cover")

    def test_temporary_settings_flags_and_restoration(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            volume = repo / "Volume"
            volume.mkdir()
            original = {"cookie": "SECRET", "root": "old", "music": False}
            settings = volume / "settings.json"
            settings.write_text(json.dumps(original), encoding="utf-8-sig")
            opts = {"artifacts": ["music", "static-cover", "dynamic-cover"], "live_quality": "1"}
            with dc.temporary_settings(repo, repo / "payload", opts):
                changed = json.loads(settings.read_text(encoding="utf-8-sig"))
                self.assertTrue(changed["music"])
                self.assertTrue(changed["static_cover"])
                self.assertTrue(changed["dynamic_cover"])
                self.assertEqual(changed["storage_format"], "")
                self.assertEqual(changed["folder_name"], "_staging")
                self.assertEqual(changed["split"], "__")
                self.assertEqual(changed["cookie"], "SECRET")
            self.assertEqual(json.loads(settings.read_text(encoding="utf-8-sig")), original)

    def test_organizes_media_into_direct_author_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "_staging"
            source.mkdir()
            (source / "2026-08-27 12_00_00__视频__作者甲__作品.mp4").write_bytes(b"video")
            (source / "作者乙__配乐__123.mp3").write_bytes(b"music")
            dc.organize_by_author(root)
            self.assertTrue((root / "作者甲" / "2026-08-27 12_00_00__视频__作者甲__作品.mp4").is_file())
            self.assertTrue((root / "作者乙" / "作者乙__配乐__123.mp3").is_file())
            self.assertFalse(source.exists())
            folders = dc.author_folders(dc.inventory(root))
            self.assertEqual({item["author"]: item["file_count"] for item in folders}, {"作者甲": 1, "作者乙": 1})

    def test_secret_redaction(self):
        message = dc.sanitize_message("Cookie: abc; access_token=xyz https://cdn.example/signed normal")
        self.assertNotIn("abc", message)
        self.assertNotIn("xyz", message)
        self.assertNotIn("cdn.example", message)


class UpstreamModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_account_and_mix_mode_calls(self):
        account = type("Fake", (), {})()
        account.check_sec_user_id = AsyncMock(return_value="sec")
        account.deal_account_detail = AsyncMock(return_value=True)
        options = {"account_tab": "favorite", "earliest": "2026-08-01", "latest": "2026-08-27", "pages": 2}
        await dc.run_worker_mode(account, "account", ["u"], options, Path("."))
        account.deal_account_detail.assert_awaited_once_with(
            1, "sec", tab="favorite", earliest="2026-08-01", latest="2026-08-27", pages=2,
        )

        mix = type("Fake", (), {})()
        mix._check_mix_id = AsyncMock(return_value=(True, "item", "title"))
        mix.deal_mix_detail = AsyncMock(return_value=True)
        await dc.run_worker_mode(mix, "mix", ["u"], options, Path("."))
        mix.deal_mix_detail.assert_awaited_once_with(True, "item", index=1, mix_title="title")

    async def test_saved_folder_selection_by_number_name_and_all(self):
        class Extractor:
            @staticmethod
            def extract_collects_info(_):
                return [{"name": "A", "id": "1"}, {"name": "B", "id": "2"}]

        fake = type("Fake", (), {})()
        setattr(fake, "_TikTok__get_collects_list", AsyncMock(return_value=[{"raw": True}]))
        fake.extractor = Extractor()
        fake._deal_collects_data = AsyncMock()
        opts = {"selectors": ["2", "A"]}
        await dc.run_worker_mode(fake, "saved-folders", [], opts, Path("."))
        self.assertEqual(fake._deal_collects_data.await_count, 2)

        fake._deal_collects_data.reset_mock()
        await dc.run_worker_mode(fake, "saved-folders", [], {"selectors": ["all"]}, Path("."))
        self.assertEqual(fake._deal_collects_data.await_count, 2)

    async def test_live_waits_for_ffmpeg_completion(self):
        class Extractor:
            async def run(self, *_):
                return [{
                    "status": 2, "title": "title", "nickname": "host",
                    "flv_pull_url": {"FULL_HD1": "https://stream.example/live.flv"},
                    "hls_pull_url_map": {},
                }]

        class Process:
            def __init__(self):
                self.waited = False

            async def wait(self):
                self.waited = True
                return 0

        process = Process()
        fake = type("Fake", (), {})()
        fake.links = type("Links", (), {"run": AsyncMock(return_value=["rid"])})()
        fake.get_live_data = AsyncMock(return_value={"raw": True})
        fake.extractor = Extractor()
        fake.parameter = type("P", (), {"headers_download": {"User-Agent": "UA"}})()
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(dc.shutil, "which", return_value="ffmpeg"), \
             patch.object(dc.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)):
            await dc.record_live(fake, ["url"], "1", Path(temp))
        self.assertTrue(process.waited)


class JobLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"CODEX_HOME": self.temp.name})
        self.env.start()
        self.quiet = patch.object(dc, "emit")
        self.quiet.start()

    def tearDown(self):
        self.quiet.stop()
        self.env.stop()
        self.temp.cleanup()

    def make_job(self, job_id="abcdef123456", requested=None, keep_local=False):
        requested = requested or ["quark", "baidu"]
        job = dc.job_path(job_id)
        payload = job / "payload"
        payload.mkdir(parents=True)
        (payload / "video.mp4").write_bytes(b"1234")
        manifest = {
            "job_id": job_id, "status": "downloaded", "payload_path": str(payload),
            "requested_destinations": requested,
            "uploads": {drive: {"status": "pending"} for drive in requested},
            "keep_local": keep_local,
        }
        dc.atomic_json(dc.manifest_path(job_id), manifest)
        return job

    def mark(self, drive, status, job="abcdef123456", message=None):
        return dc.mark_upload(argparse.Namespace(
            job=job, drive=drive, status=status, remote_path=f"remote/{drive}", message=message,
        ))

    def test_partial_failure_retains_payload_and_retry_finishes(self):
        job = self.make_job()
        self.mark("quark", "success")
        self.mark("baidu", "failed", message="access_token=secret temporary")
        with self.assertRaisesRegex(dc.SkillError, "All requested"):
            dc.finalize(argparse.Namespace(job="abcdef123456"))
        self.assertTrue(job.exists())
        manifest = dc.load_manifest("abcdef123456")
        self.assertNotIn("secret", manifest["uploads"]["baidu"]["message"])

        self.mark("baidu", "success")
        dc.finalize(argparse.Namespace(job="abcdef123456"))
        self.assertFalse(job.exists())
        receipt = dc.load_manifest("abcdef123456")
        self.assertEqual(receipt["status"], "complete")
        self.assertTrue(receipt["local_files_removed"])

    def test_keep_local(self):
        job = self.make_job(requested=["quark"], keep_local=True)
        self.mark("quark", "success")
        dc.finalize(argparse.Namespace(job="abcdef123456"))
        self.assertTrue(job.exists())

    def test_job_id_path_traversal_rejected(self):
        with self.assertRaises(dc.SkillError):
            dc.job_path("../../bad")


if __name__ == "__main__":
    unittest.main()
