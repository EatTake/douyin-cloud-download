#!/usr/bin/env python3
"""Pinned DouK-Downloader adapter and resumable cloud-upload job ledger."""

from __future__ import annotations

import argparse
import ast
import asyncio
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlparse


UPSTREAM_URL = "https://github.com/JoeanAmier/TikTokDownloader.git"
PINNED_COMMIT = "d3806386b392da7341397e18522acdd5283f2c81"
RUNTIME_COMMIT_FILE = ".douyin-cloud-download-upstream-commit"
JOB_RE = re.compile(r"^[0-9a-f]{12}$")
MEDIA_SUFFIXES = {
    ".mp4", ".mov", ".mkv", ".webm", ".flv", ".m4v",
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic",
    ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg",
}
SECRET_RE = re.compile(
    r"(?i)(cookie|authorization|access[_-]?token|refresh[_-]?token|bduss|stoken)"
    r"\s*[:=]\s*([^\s,;]+)"
)
URL_RE = re.compile(r"https?://[^\s<>\"]+")
FILENAME_SEPARATOR = "__"
UNKNOWN_AUTHOR = "未知作者"
DEFAULT_CLOUD_ROOT = "抖音下载"
DEFAULT_CLOUD_LAYOUT = f"./{DEFAULT_CLOUD_ROOT}/[作者]"


class SkillError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def codex_root() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()


def state_root() -> Path:
    return codex_root() / "state" / "douyin-cloud-download"


def runtime_root() -> Path:
    return state_root() / "upstream" / PINNED_COMMIT[:12]


def jobs_root() -> Path:
    return state_root() / "jobs"


def history_root() -> Path:
    return state_root() / "history"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def emit(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))


def fail(code: str, message: str, *, details: Any = None) -> int:
    result: dict[str, Any] = {"ok": False, "error": code, "message": message}
    if details is not None:
        result["details"] = details
    emit(result)
    return 2


def run_checked(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise SkillError("missing_executable", f"Required executable is unavailable: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise SkillError("command_failed", f"Command failed with exit code {exc.returncode}: {args[0]}") from exc


def git_head(repo: Path) -> str | None:
    if not (repo / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout.strip() if result.returncode == 0 else None


def runtime_commit(repo: Path) -> str | None:
    """Return the pinned upstream revision for a Git checkout or vendored runtime."""
    head = git_head(repo)
    if head:
        return head
    marker = repo / RUNTIME_COMMIT_FILE
    try:
        value = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def verify_runtime() -> Path:
    repo = runtime_root()
    if not repo.exists():
        raise SkillError("runtime_missing", "Pinned DouK-Downloader runtime is not installed; run bootstrap.")
    commit = runtime_commit(repo)
    if commit != PINNED_COMMIT:
        raise SkillError(
            "runtime_commit_mismatch",
            f"Runtime commit is {commit or 'unreadable'}, expected {PINNED_COMMIT}; it will not be overwritten.",
        )
    return repo


def bootstrap(_: argparse.Namespace) -> int:
    root = state_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "upstream").mkdir(exist_ok=True)
    jobs_root().mkdir(exist_ok=True)
    history_root().mkdir(exist_ok=True)
    repo = runtime_root()
    if repo.exists():
        verify_runtime()
    else:
        temp_parent = Path(tempfile.mkdtemp(prefix="bootstrap-", dir=root))
        candidate = temp_parent / "repo"
        try:
            run_checked(["git", "clone", "--filter=blob:none", "--no-checkout", UPSTREAM_URL, str(candidate)])
            run_checked(["git", "checkout", "--detach", PINNED_COMMIT], cwd=candidate)
            if git_head(candidate) != PINNED_COMMIT:
                raise SkillError("runtime_commit_mismatch", "Cloned runtime did not resolve to the pinned commit.")
            candidate.replace(repo)
        finally:
            shutil.rmtree(temp_parent, ignore_errors=True)
    run_checked(["uv", "sync", "--locked", "--python", "3.12", "--no-dev"], cwd=repo)
    contract_check(repo)
    emit({"ok": True, "status": "ready", "runtime": str(repo), "commit": PINNED_COMMIT})
    return 0


def configure(_: argparse.Namespace) -> int:
    repo = verify_runtime()
    print("DouK-Downloader will open interactively. Read/accept its disclaimer and enter Cookie only in this terminal.")
    completed = subprocess.run(["uv", "run", "--project", str(repo), "python", "main.py"], cwd=repo)
    status = doctor_data()
    status["configure_exit_code"] = completed.returncode
    emit(status)
    return 0 if status["ready"] else 2


def read_settings(repo: Path) -> dict[str, Any]:
    path = repo / "Volume" / "settings.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def disclaimer_accepted(repo: Path) -> bool:
    db = repo / "Volume" / "DouK-Downloader.db"
    if not db.exists():
        return False
    try:
        with sqlite3.connect(db) as con:
            row = con.execute("SELECT VALUE FROM config_data WHERE NAME='Disclaimer'").fetchone()
        return bool(row and row[0] == 1)
    except sqlite3.Error:
        return False


def doctor_data() -> dict[str, Any]:
    repo = runtime_root()
    commit = runtime_commit(repo)
    settings = read_settings(repo) if commit == PINNED_COMMIT else {}
    checks = {
        "git": shutil.which("git") is not None,
        "uv": shutil.which("uv") is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "runtime_present": repo.exists(),
        "runtime_commit": commit == PINNED_COMMIT,
        "disclaimer_accepted": disclaimer_accepted(repo) if commit == PINNED_COMMIT else False,
        "douyin_cookie": bool(str(settings.get("cookie", "")).strip()),
        "encipher": (repo / "encipher.py").is_file() if head == PINNED_COMMIT else False,
    }
    required = ("git", "uv", "runtime_present", "runtime_commit", "disclaimer_accepted", "douyin_cookie")
    return {
        "ok": all(checks[k] for k in required),
        "ready": all(checks[k] for k in required),
        "commit": PINNED_COMMIT,
        "runtime": str(repo),
        "checks": checks,
    }


def doctor(args: argparse.Namespace) -> int:
    data = doctor_data()
    if args.json:
        emit(data)
    else:
        for key, value in data["checks"].items():
            print(f"{key}: {'ok' if value else 'missing'}")
        print(f"ready: {data['ready']}")
    return 0 if data["ready"] else 2


def contract_check(repo: Path | None = None) -> None:
    root = repo or verify_runtime()
    required = {
        "src/application/TikTokDownloader.py": (
            "class TikTokDownloader", "async def check_settings", "def check_config",
        ),
        "src/application/main_terminal.py": (
            "class TikTok", "async def _handle_detail", "async def deal_account_detail",
            "async def deal_mix_detail", "async def _check_mix_id",
            "async def __get_collects_list", "async def __handle_collection_music",
            "async def _deal_collection_data", "async def _deal_collects_data",
            "async def get_live_data",
        ),
        "src/config/settings.py": ("class Settings",),
        "src/downloader/download.py": (
            "async def run", "async def run_live", "async def download_image",
            "async def download_video", "def download_music", "def download_cover",
        ),
        "uv.lock": (),
    }
    missing: list[str] = []
    for relative, needles in required.items():
        path = root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace") if needles else ""
        missing.extend(f"{relative}:{needle}" for needle in needles if needle not in text)
    if missing:
        raise SkillError("upstream_contract_changed", "Pinned upstream contract check failed: " + ", ".join(missing))


def install_encipher(args: argparse.Namespace) -> int:
    if not args.i_understand_this_executes_code:
        raise SkillError("consent_required", "Explicit execution consent is required for external encipher.py.")
    repo = verify_runtime()
    source = Path(args.file).expanduser().resolve()
    if not source.is_file() or source.name.lower() != "encipher.py":
        raise SkillError("invalid_encipher", "Provide an existing file named encipher.py.")
    try:
        tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=str(source))
    except (OSError, SyntaxError) as exc:
        raise SkillError("invalid_encipher", f"encipher.py could not be parsed: {exc}") from exc
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    needed = {"ABogus", "XBogus", "XGnarly"}
    if not needed.issubset(classes):
        raise SkillError("invalid_encipher", "encipher.py must define ABogus, XBogus, and XGnarly.")
    target = repo / "encipher.py"
    shutil.copy2(source, target)
    emit({
        "ok": True,
        "status": "installed",
        "path": str(target),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "warning": "This external code will be imported and executed by DouK-Downloader.",
    })
    return 0


class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            raise SkillError("download_in_progress", "Another Douyin download job currently holds the runtime lock.") from exc
        return self

    def __exit__(self, *_: Any) -> None:
        if not self.handle:
            return
        with contextlib.suppress(OSError):
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def validate_url(value: str) -> str:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (host == "douyin.com" or host.endswith(".douyin.com")):
        raise argparse.ArgumentTypeError("Only http(s) Douyin URLs are supported.")
    return value.strip()


def iso_date(value: str) -> str:
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Date must use YYYY-MM-DD.") from exc


def destinations(value: str) -> list[str]:
    return ["quark", "baidu"] if value == "both" else [value]


def classify_url(url: str) -> str:
    parsed = urlparse(url)
    host, path, query = (parsed.hostname or "").lower(), parsed.path.lower(), parsed.query.lower()
    if host.startswith("live.") or "web_rid=" in query:
        return "live"
    if "/collection/" in path or "/mix/" in path:
        return "mix"
    if "/user/" in path and "modal_id=" not in query:
        return "account"
    return "works"


def grouped_urls(mode: str, urls: list[str]) -> dict[str, list[str]]:
    if mode != "auto":
        return {mode: list(dict.fromkeys(urls))}
    groups: dict[str, list[str]] = {}
    for url in urls:
        groups.setdefault(classify_url(url), [])
        if url not in groups[classify_url(url)]:
            groups[classify_url(url)].append(url)
    return groups


def job_path(job_id: str) -> Path:
    if not JOB_RE.fullmatch(job_id):
        raise SkillError("invalid_job_id", "Job ID must be exactly 12 lowercase hexadecimal characters.")
    return jobs_root() / job_id


def manifest_path(job_id: str) -> Path:
    return job_path(job_id) / "manifest.json"


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def load_manifest(job_id: str) -> dict[str, Any]:
    path = manifest_path(job_id)
    if not path.is_file():
        history = history_root() / f"{job_id}.json"
        if history.is_file():
            return json.loads(history.read_text(encoding="utf-8"))
        raise SkillError("job_not_found", f"No job exists with ID {job_id}.")
    return json.loads(path.read_text(encoding="utf-8"))


def media_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    lower_parts = [part.lower() for part in path.parts]
    if "live" in lower_parts:
        return "live"
    if suffix in {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg"}:
        return "music"
    if "cover" in path.stem.lower() or "封面" in path.stem:
        return "cover"
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}:
        return "image"
    return "video"


def inventory(payload: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    if not payload.exists():
        return files
    for path in sorted(p for p in payload.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES):
        files.append({
            "path": path.relative_to(payload).as_posix(),
            "size": path.stat().st_size,
            "media_type": media_kind(path.relative_to(payload)),
        })
    return files


def safe_author(value: str) -> str:
    value = re.sub(r"[<>:\"/\\\\|?*\x00-\x1f]", "_", value).strip(" .")
    return value[:80] or UNKNOWN_AUTHOR


def author_from_media(path: Path) -> str:
    """Infer the author from the temporary, adapter-controlled media name."""
    parts = path.stem.split(FILENAME_SEPARATOR)
    if len(parts) >= 4 and re.match(r"^\d{4}-\d{2}-\d{2}", parts[0]):
        return safe_author(parts[2])
    if path.parent.name == "Live" and len(parts) >= 3:
        return safe_author(parts[0])
    if media_kind(path) == "music" and len(parts) >= 3:
        return safe_author(parts[0])
    return UNKNOWN_AUTHOR


def available_media_path(folder: Path, filename: str) -> Path:
    target = folder / filename
    index = 2
    while target.exists():
        target = folder / f"{Path(filename).stem}_{index}{Path(filename).suffix}"
        index += 1
    return target


def organize_by_author(payload: Path) -> None:
    """Flatten upstream staging folders into one direct folder per author."""
    media = [path for path in payload.rglob("*") if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES]
    for source in sorted(media):
        author = author_from_media(source.relative_to(payload))
        target_folder = payload / author
        target_folder.mkdir(exist_ok=True)
        if source.parent == target_folder:
            continue
        source.replace(available_media_path(target_folder, source.name))
    for folder in sorted((path for path in payload.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
        with contextlib.suppress(OSError):
            folder.rmdir()


def author_folders(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in files:
        parts = PurePosixPath(item["path"]).parts
        if len(parts) < 2:
            continue
        group = grouped.setdefault(parts[0], {"author": parts[0], "files": [], "file_count": 0, "total_size": 0})
        group["files"].append(item)
        group["file_count"] += 1
        group["total_size"] += item["size"]
    return [grouped[name] for name in sorted(grouped)]


def sanitize_message(value: str) -> str:
    value = URL_RE.sub("[REDACTED_URL]", value)
    value = SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)
    return value[:1000]


def validate_download_args(args: argparse.Namespace) -> None:
    needs_urls = {"auto", "works", "account", "mix", "saved-works", "live"}
    if args.mode in needs_urls and not args.url:
        raise SkillError("urls_required", f"Mode {args.mode} requires at least one --url.")
    if args.mode == "saved-folders" and not args.selector:
        raise SkillError("saved_folder_scope_required", "Select a saved folder by name/number or use --selector all.")
    if args.earliest and args.latest and args.earliest > args.latest:
        raise SkillError("invalid_date_range", "--earliest cannot be after --latest.")
    if args.mode not in {"account", "auto"} and (args.earliest or args.latest or args.pages or args.account_tab != "post"):
        raise SkillError("account_options_invalid", "Account tab/date/page options are valid only for account or auto mode.")


def new_manifest(args: argparse.Namespace, job_id: str, payload: Path) -> dict[str, Any]:
    requested = destinations(args.destination)
    return {
        "schema_version": 1,
        "job_id": job_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "status": "downloading",
        "mode": args.mode,
        "source_urls": list(dict.fromkeys(args.url or [])),
        "options": {
            "artifacts": sorted(set(args.artifact or [])),
            "account_tab": args.account_tab,
            "earliest": args.earliest or "",
            "latest": args.latest or "",
            "pages": args.pages,
            "selectors": args.selector or [],
            "live_quality": args.live_quality,
        },
        "payload_path": str(payload),
        "cloud_root": DEFAULT_CLOUD_ROOT,
        "cloud_layout": DEFAULT_CLOUD_LAYOUT,
        "author_folders": [],
        "requested_destinations": requested,
        "files": [],
        "file_count": 0,
        "total_size": 0,
        "uploads": {drive: {"status": "pending"} for drive in requested},
        "keep_local": bool(args.keep_local),
        "error": None,
    }


def download(args: argparse.Namespace) -> int:
    validate_download_args(args)
    repo = verify_runtime()
    contract_check(repo)
    status = doctor_data()
    if not status["checks"]["disclaimer_accepted"]:
        raise SkillError("disclaimer_not_accepted", "Run configure and accept the upstream disclaimer after reading it.")
    if not status["checks"]["douyin_cookie"]:
        raise SkillError("douyin_cookie_missing", "Run configure and enter a valid Douyin Cookie in the terminal.")
    contains_live = args.mode == "live" or (args.mode == "auto" and any(classify_url(url) == "live" for url in args.url))
    if contains_live and not status["checks"]["ffmpeg"]:
        raise SkillError("ffmpeg_missing", "ffmpeg is required for live recording.")

    state_root().mkdir(parents=True, exist_ok=True)
    with FileLock(state_root() / "download.lock"):
        job_id = uuid.uuid4().hex[:12]
        job = job_path(job_id)
        payload = job / "payload"
        payload.mkdir(parents=True)
        manifest = new_manifest(args, job_id, payload)
        atomic_json(manifest_path(job_id), manifest)
        worker_args = [
            "uv", "run", "--project", str(repo), "python", str(Path(__file__).resolve()),
            "_worker", "--job", job_id,
        ]
        interrupted = False
        try:
            completed = subprocess.run(worker_args, cwd=repo)
            return_code = completed.returncode
        except KeyboardInterrupt:
            interrupted = True
            return_code = 130

        manifest = load_manifest(job_id)
        organize_by_author(payload)
        files = inventory(payload)
        manifest["files"] = files
        manifest["author_folders"] = author_folders(files)
        manifest["file_count"] = len(files)
        manifest["total_size"] = sum(item["size"] for item in files)
        manifest["updated_at"] = utc_now()
        if interrupted or return_code == 130:
            manifest["status"] = "interrupted"
            manifest["error"] = {"code": "interrupted", "message": "Download interrupted; partial files retained and must not be auto-uploaded."}
        elif return_code != 0:
            manifest["status"] = "failed"
            manifest["error"] = manifest.get("error") or {"code": "upstream_failed", "message": f"Pinned downloader exited with code {return_code}."}
        elif not files:
            manifest["status"] = "failed"
            manifest["error"] = {"code": "no_media_downloaded", "message": "No media was created; check Cookie, access, and upstream encryption compatibility."}
        else:
            manifest["status"] = "downloaded"
            manifest["error"] = None
        atomic_json(manifest_path(job_id), manifest)
        emit(manifest)
        return 0 if manifest["status"] == "downloaded" else (130 if manifest["status"] == "interrupted" else 2)


@contextlib.contextmanager
def temporary_settings(repo: Path, payload: Path, options: dict[str, Any]):
    settings_path = repo / "Volume" / "settings.json"
    original = settings_path.read_bytes()
    settings = json.loads(original.decode("utf-8-sig"))
    artifacts = set(options["artifacts"])
    settings.update({
        "root": str(payload),
        "folder_name": "_staging",
        "name_format": "create_time type nickname desc",
        "split": FILENAME_SEPARATOR,
        "folder_mode": False,
        "download": True,
        "storage_format": "",
        "music": "music" in artifacts,
        "static_cover": "static-cover" in artifacts,
        "dynamic_cover": "dynamic-cover" in artifacts,
        "run_command": "",
        "live_qualities": str(options["live_quality"]),
        "douyin_platform": True,
        "tiktok_platform": False,
    })
    settings_path.write_text(json.dumps(settings, indent=4, ensure_ascii=False), encoding="utf-8-sig")
    try:
        yield
    finally:
        settings_path.write_bytes(original)


async def run_worker_mode(tik: Any, mode: str, urls: list[str], options: dict[str, Any], payload: Path) -> None:
    if mode == "works":
        ids: list[str] = []
        for url in urls:
            ids.extend(await tik.links.run(url))
        ids = list(dict.fromkeys(str(item) for item in ids if item))
        if not ids:
            raise SkillError("invalid_works_urls", "No Douyin work IDs could be extracted.")
        root, params, logger = tik.record.run(tik.parameter)
        async with logger(root, console=tik.console, **params) as record:
            await tik._handle_detail(ids, False, record)
        return

    if mode == "account":
        for index, url in enumerate(urls, start=1):
            sec_uid = await tik.check_sec_user_id(url)
            if not sec_uid:
                raise SkillError("invalid_account_url", f"Could not resolve account URL #{index}.")
            result = await tik.deal_account_detail(
                index, sec_uid, tab=options["account_tab"], earliest=options["earliest"],
                latest=options["latest"], pages=options["pages"],
            )
            if result is None and options["account_tab"] in {"favorite", "collection"}:
                raise SkillError("account_access_failed", f"Account tab access failed for URL #{index}; verify login and permissions.")
        return

    if mode == "mix":
        for index, url in enumerate(urls, start=1):
            mix_id, item_id, title = await tik._check_mix_id(url, False)
            if not item_id:
                raise SkillError("invalid_mix_url", f"Could not resolve collection URL #{index}.")
            result = await tik.deal_mix_detail(mix_id, item_id, index=index, mix_title=title)
            if not result:
                raise SkillError("mix_download_failed", f"Collection download failed for URL #{index}.")
        return

    if mode == "saved-works":
        for index, url in enumerate(urls, start=1):
            sec_uid = await tik.check_sec_user_id(url)
            if not sec_uid:
                raise SkillError("invalid_owner_url", f"Could not resolve owner account URL #{index}.")
            result = await tik._deal_collection_data(sec_uid)
            if result is None:
                # The upstream returns None after successful downloads too; final inventory is authoritative.
                continue
        return

    if mode == "saved-folders":
        raw = await tik._TikTok__get_collects_list(source=True)
        if not raw:
            raise SkillError("saved_folders_unavailable", "Could not list saved folders; verify Cookie and account access.")
        items = tik.extractor.extract_collects_info(raw)
        selectors = options["selectors"]
        selected: list[dict[str, Any]] = []
        if any(str(value).lower() == "all" for value in selectors):
            selected = list(items)
        else:
            by_name = {str(item.get("name", "")): item for item in items}
            for selector in selectors:
                text = str(selector)
                if text.isdigit() and 1 <= int(text) <= len(items):
                    item = items[int(text) - 1]
                elif text in by_name:
                    item = by_name[text]
                else:
                    raise SkillError("saved_folder_not_found", f"Saved-folder selector did not match: {text}")
                if item not in selected:
                    selected.append(item)
        for item in selected:
            await tik._deal_collects_data(str(item["name"]), str(item["id"]))
        return

    if mode == "saved-music":
        data = await tik._TikTok__handle_collection_music()
        if not data:
            raise SkillError("saved_music_unavailable", "Could not read saved music; verify Cookie and account access.")
        extracted = await tik.extractor.run(data, None, "music")
        await tik.downloader.run(extracted, type_="music")
        return

    if mode == "live":
        await record_live(tik, urls, options["live_quality"], payload)
        return

    raise SkillError("unsupported_mode", f"Unsupported worker mode: {mode}")


def safe_live_name(value: str) -> str:
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", value).strip(" .")
    return (value[:100] or "douyin-live")


def choose_quality(flv: dict[str, str], hls: dict[str, str], quality: str) -> str | None:
    if quality in hls and hls[quality]:
        return hls[quality]
    if quality in flv and flv[quality]:
        return flv[quality]
    try:
        index = int(quality) - 1
    except ValueError:
        return None
    hls_values = [value for value in hls.values() if value]
    flv_values = [value for value in flv.values() if value]
    if 0 <= index < len(hls_values):
        return hls_values[index]
    return flv_values[index] if 0 <= index < len(flv_values) else None


async def record_live(tik: Any, urls: list[str], quality: str, payload: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SkillError("ffmpeg_missing", "ffmpeg is required for live recording.")
    target_root = payload / "Live"
    target_root.mkdir(exist_ok=True)
    for index, url in enumerate(urls, start=1):
        ids = await tik.links.run(url, type_="live")
        if not ids:
            raise SkillError("invalid_live_url", f"Could not resolve live URL #{index}.")
        raw = [await tik.get_live_data(item) for item in ids]
        extracted = await tik.extractor.run(raw, None, "live")
        active = [item for item in extracted if item and item.get("status") != 4]
        if not active:
            raise SkillError("live_not_active", f"Live URL #{index} is offline or unavailable.")
        for item in active:
            stream = choose_quality(item.get("flv_pull_url", {}), item.get("hls_pull_url_map", {}), str(quality))
            if not stream:
                raise SkillError("live_quality_invalid", f"Live quality is unavailable: {quality}")
            filename = safe_live_name(
                f"{item.get('nickname', 'host')}{FILENAME_SEPARATOR}live{FILENAME_SEPARATOR}{dt.datetime.now():%Y-%m-%d %H.%M.%S}.mp4"
            )
            target = target_root / filename
            command = [
                ffmpeg, "-hide_banner", "-rw_timeout", "30000000", "-loglevel", "warning",
                "-protocol_whitelist", "rtmp,crypto,file,http,https,tcp,tls,udp,rtp,httpproxy",
                "-analyzeduration", "10000000", "-probesize", "10000000", "-fflags", "+discardcorrupt",
                "-user_agent", str(tik.parameter.headers_download.get("User-Agent", "Mozilla/5.0")),
                "-i", stream, "-bufsize", "10240k", "-map", "0", "-c:v", "copy", "-c:a", "copy",
                "-sn", "-dn", "-reconnect_delay_max", "60", "-reconnect_streamed", "1",
                "-reconnect_at_eof", "1", "-max_muxing_queue_size", "128", "-correct_ts_overflow", "1",
                "-f", "mp4", str(target),
            ]
            process = await asyncio.create_subprocess_exec(*command)
            try:
                code = await process.wait()
            except BaseException:
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()
                with contextlib.suppress(Exception):
                    await process.wait()
                raise
            if code != 0:
                raise SkillError("live_recording_failed", f"ffmpeg exited with code {code}; partial file retained.")


async def worker_async(manifest: dict[str, Any]) -> None:
    repo = verify_runtime()
    payload = Path(manifest["payload_path"]).resolve()
    expected_job = job_path(manifest["job_id"]).resolve()
    if expected_job not in payload.parents:
        raise SkillError("invalid_payload_path", "Payload path is outside its validated job directory.")
    sys.path.insert(0, str(repo))
    os.chdir(repo)
    from src.application.TikTokDownloader import TikTokDownloader  # type: ignore
    from src.application.main_terminal import TikTok  # type: ignore

    with temporary_settings(repo, payload, manifest["options"]):
        async with TikTokDownloader() as app:
            app.config["Record"] = 1
            app.config["Logger"] = 0
            app.check_config()
            await app.check_settings(False)
            tik = TikTok(app.parameter, app.database)
            # Use the upstream recorder only as an intra-job ID set. Clear it on both
            # sides so prior jobs never suppress a requested download.
            await app.database.delete_all_download_data()
            try:
                for mode, urls in grouped_urls(manifest["mode"], manifest["source_urls"]).items():
                    await run_worker_mode(tik, mode, urls, manifest["options"], payload)
            finally:
                await app.database.delete_all_download_data()


def worker(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.job)
    try:
        asyncio.run(worker_async(manifest))
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        if isinstance(exc, SkillError):
            code, message = exc.code, str(exc)
        else:
            code, message = "upstream_exception", f"{type(exc).__name__}: {exc}"
        manifest = load_manifest(args.job)
        manifest["error"] = {"code": code, "message": sanitize_message(message)}
        manifest["updated_at"] = utc_now()
        atomic_json(manifest_path(args.job), manifest)
        print(f"douyin-cloud-download: {code}: {sanitize_message(message)}", file=sys.stderr)
        return 2


def show_job(args: argparse.Namespace) -> int:
    emit(load_manifest(args.job))
    return 0


def mark_upload(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.job)
    if args.drive not in manifest.get("requested_destinations", []):
        raise SkillError("drive_not_requested", f"{args.drive} was not requested for this job.")
    if manifest.get("status") not in {"downloaded", "uploading", "upload_failed"}:
        raise SkillError("job_not_uploadable", f"Job status {manifest.get('status')} is not uploadable.")
    entry: dict[str, Any] = {"status": args.status, "updated_at": utc_now()}
    if args.remote_path:
        if urlparse(args.remote_path).scheme:
            raise SkillError("invalid_remote_path", "Upload receipt remote path cannot be a URL.")
        entry["remote_path"] = sanitize_message(args.remote_path)
    if args.message:
        entry["message"] = sanitize_message(args.message)
    manifest["uploads"][args.drive] = entry
    statuses = [item["status"] for item in manifest["uploads"].values()]
    manifest["status"] = "uploaded" if all(value == "success" for value in statuses) else (
        "upload_failed" if "failed" in statuses else "uploading"
    )
    manifest["updated_at"] = utc_now()
    atomic_json(manifest_path(args.job), manifest)
    emit(manifest)
    return 0


def finalize(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.job)
    if not manifest.get("uploads") or not all(
        item.get("status") == "success" for item in manifest["uploads"].values()
    ):
        raise SkillError("uploads_incomplete", "All requested cloud uploads must be verified successful before finalization.")
    manifest["status"] = "complete"
    manifest["completed_at"] = utc_now()
    manifest["updated_at"] = utc_now()
    if manifest.get("keep_local"):
        atomic_json(manifest_path(args.job), manifest)
        emit(manifest)
        return 0
    job = job_path(args.job).resolve()
    root = jobs_root().resolve()
    if job.parent != root or not job.is_dir():
        raise SkillError("unsafe_cleanup_target", "Refusing to remove an unverified job directory.")
    receipt = dict(manifest)
    receipt["payload_path"] = None
    receipt["local_files_removed"] = True
    history_root().mkdir(parents=True, exist_ok=True)
    atomic_json(history_root() / f"{args.job}.json", receipt)
    shutil.rmtree(job)
    emit(receipt)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download authorized Douyin media and stage it for cloud-drive skills.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="Install and verify the pinned DouK-Downloader runtime.").set_defaults(func=bootstrap)
    sub.add_parser("configure", help="Open the upstream disclaimer and Cookie setup flow.").set_defaults(func=configure)
    doctor_parser = sub.add_parser("doctor", help="Check runtime and one-time setup status.")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=doctor)

    encipher = sub.add_parser("install-encipher", help="Install an explicitly supplied external encipher.py.")
    encipher.add_argument("--file", required=True)
    encipher.add_argument("--i-understand-this-executes-code", action="store_true")
    encipher.set_defaults(func=install_encipher)

    dl = sub.add_parser("download", help="Create a download job and local upload payload.")
    dl.add_argument("--mode", choices=("auto", "works", "account", "mix", "saved-works", "saved-folders", "saved-music", "live"), default="auto")
    dl.add_argument("--url", action="append", type=validate_url, default=[])
    dl.add_argument("--destination", choices=("quark", "baidu", "both"), default="quark")
    dl.add_argument("--artifact", action="append", choices=("music", "static-cover", "dynamic-cover"), default=[])
    dl.add_argument("--account-tab", choices=("post", "favorite", "collection"), default="post")
    dl.add_argument("--earliest", type=iso_date)
    dl.add_argument("--latest", type=iso_date)
    dl.add_argument("--pages", type=int)
    dl.add_argument("--selector", action="append", default=[])
    dl.add_argument("--live-quality", default="1")
    dl.add_argument("--keep-local", action="store_true")
    dl.set_defaults(func=download)

    show = sub.add_parser("show-job", help="Show a job or finalized receipt.")
    show.add_argument("--job", required=True)
    show.set_defaults(func=show_job)

    mark = sub.add_parser("mark-upload", help="Record a verified cloud upload result.")
    mark.add_argument("--job", required=True)
    mark.add_argument("--drive", choices=("quark", "baidu"), required=True)
    mark.add_argument("--status", choices=("success", "failed"), required=True)
    mark.add_argument("--remote-path")
    mark.add_argument("--message")
    mark.set_defaults(func=mark_upload)

    done = sub.add_parser("finalize", help="Clean staging only after every requested upload succeeded.")
    done.add_argument("--job", required=True)
    done.set_defaults(func=finalize)

    hidden = sub.add_parser("_worker", help=argparse.SUPPRESS)
    hidden.add_argument("--job", required=True)
    hidden.set_defaults(func=worker)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if getattr(args, "pages", None) is not None and args.pages < 1:
            raise SkillError("invalid_pages", "--pages must be a positive integer.")
        return int(args.func(args))
    except SkillError as exc:
        return fail(exc.code, str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
