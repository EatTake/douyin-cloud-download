#!/usr/bin/env python3
"""Cross-platform installer and maintenance controller for douyin-cloud-download."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from dcd_setup.migrations import migrate_with_project_adapter, migration_backup
from dcd_setup.release import load_release_config, release_metadata
from dcd_setup.rollback import (
    cleanup_old_versions, list_versions, read_current_release, rollback as rollback_release,
    snapshot_current_release, write_current_release,
)


_REPO_ROOT = SCRIPT_DIR.parent
RELEASE_CONFIG = load_release_config(_REPO_ROOT)
PRODUCT_VERSION = RELEASE_CONFIG.product_version
PINNED_COMMIT = RELEASE_CONFIG.douk_commit
QUARK_VERSION = RELEASE_CONFIG.quark_version
QUARK_SHA256 = RELEASE_CONFIG.quark_sha256
BAIDU_SKILL_VERSION = RELEASE_CONFIG.baidu_skill_version
QUARK_CONFIG_URL = RELEASE_CONFIG.quark_config_url
BAIDU_VERSION_URL = RELEASE_CONFIG.baidu_version_url
QUARK_ALLOWED_HOSTS = set(RELEASE_CONFIG.quark_allowed_hosts)
RUNTIME_MARKER = ".douyin-cloud-download-upstream-commit"
RECEIPT_NAME = ".douyin-cloud-download-receipt.json"
MUTABLE_SKILL_PATHS = ("codex", ".config", "config.json", "storage", "data")
MUTABLE_RUNTIME_PATHS = ("Volume", "encipher.py")


def repo_root() -> Path:
    return _REPO_ROOT


def codex_home(explicit: str | None = None) -> Path:
    value = explicit or os.environ.get("CODEX_HOME")
    return Path(value).expanduser().resolve() if value else (Path.home() / ".codex").resolve()


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, capture: bool = False,
        env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd) if cwd else None,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "env": env,
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    result = subprocess.run(args, **kwargs)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() if capture else ""
        raise RuntimeError(f"command failed ({result.returncode}): {args[0]}" + (f": {detail}" if detail else ""))
    return result


def command_version(name: str, args: Iterable[str]) -> str | None:
    path = shutil.which(name)
    if not path:
        return None
    try:
        out = run([path, *args], capture=True, check=False)
    except OSError:
        return None
    text = (out.stdout or out.stderr or "").strip().splitlines()
    return text[0] if text else "present"


def find_bash() -> Path | None:
    candidates: list[Path] = []
    first = shutil.which("bash")
    if first:
        candidates.append(Path(first))
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            git_path = Path(git).resolve()
            candidates.extend([
                git_path.parent.parent / "bin" / "bash.exe",
                git_path.parent.parent / "usr" / "bin" / "bash.exe",
            ])
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env_name)
            if base:
                candidates.extend([
                    Path(base) / "Git" / "bin" / "bash.exe",
                    Path(base) / "Git" / "usr" / "bin" / "bash.exe",
                ])
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        if candidate in seen or not candidate.is_file():
            continue
        seen.add(candidate)
        result = run([str(candidate), "-lc", "uname -s"], capture=True, check=False)
        uname = (result.stdout or "").strip().splitlines()
        value = uname[0] if uname else ""
        if os.name == "nt":
            if value.startswith(("MINGW", "MSYS", "CYGWIN")):
                return candidate
        elif value.startswith("Linux"):
            return candidate
    return None


def bash_kind() -> tuple[bool, str]:
    bash = find_bash()
    if not bash:
        first = shutil.which("bash")
        if os.name == "nt" and first:
            probe = run([first, "-lc", "uname -s"], capture=True, check=False)
            uname = (probe.stdout or "").strip()
            if uname.startswith("Linux"):
                return False, "WSL/Linux Bash detected; install Git for Windows and use Git Bash"
        return False, "compatible Bash not found"
    result = run([str(bash), "-lc", "uname -s"], capture=True, check=False)
    uname = (result.stdout or "").strip().splitlines()[0]
    label = "Windows-host Bash" if os.name == "nt" else "Bash"
    return True, f"{label} ({uname}; {bash})"


def preflight() -> dict[str, Any]:
    machine = platform.machine().lower()
    supported_arch = machine in {"x86_64", "amd64"}
    py_ok = sys.version_info[:2] == (3, 12)
    bash_ok, bash_detail = bash_kind()
    checks = {
        "python_3_12": {"ok": py_ok, "value": platform.python_version()},
        "architecture_x86_64": {"ok": supported_arch, "value": machine},
        "uv": {"ok": shutil.which("uv") is not None, "value": command_version("uv", ["--version"])},
        "git": {"ok": shutil.which("git") is not None, "value": command_version("git", ["--version"])},
        "bash": {"ok": bash_ok, "value": bash_detail},
        "node": {"ok": shutil.which("node") is not None, "value": command_version("node", ["--version"])},
        "ffmpeg_optional": {"ok": shutil.which("ffmpeg") is not None, "value": command_version("ffmpeg", ["-version"])},
    }
    checks["base_ready"] = {"ok": all(checks[k]["ok"] for k in ("python_3_12", "architecture_x86_64", "uv", "git", "bash", "node"))}
    return checks


def ensure_preflight() -> None:
    checks = preflight()
    failed = [k for k, v in checks.items() if k != "ffmpeg_optional" and isinstance(v, dict) and not v.get("ok")]
    if failed:
        raise RuntimeError("preflight failed: " + ", ".join(failed))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_path(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    elif src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def atomic_replace_dir(candidate: Path, destination: Path, preserve: Iterable[str] = ()) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if destination.exists():
        backup = destination.with_name(destination.name + f".backup-{uuid.uuid4().hex[:8]}")
        os.replace(destination, backup)
    try:
        os.replace(candidate, destination)
        if backup:
            for relative in preserve:
                old = backup / relative
                if old.exists():
                    new = destination / relative
                    if new.exists():
                        if new.is_dir():
                            shutil.rmtree(new)
                        else:
                            new.unlink()
                    copy_path(old, new)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        if backup and backup.exists():
            os.replace(backup, destination)
        raise
    if backup:
        shutil.rmtree(backup, ignore_errors=True)


def staged_copy(source: Path, parent: Path, prefix: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=prefix, dir=parent)) / "payload"
    shutil.copytree(source, stage)
    return stage


def load_adapter(path: Path):
    spec = importlib.util.spec_from_file_location("douyin_cloud_installer_adapter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load douyin adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_bundled_skills(home: Path) -> None:
    skills = home / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    for name, preserve in (("douyin-cloud-download", ()), ("baidu-drive", MUTABLE_SKILL_PATHS)):
        source = repo_root() / "skills" / name
        stage = staged_copy(source, skills, f".{name}-stage-")
        if name == "douyin-cloud-download":
            shutil.copy2(repo_root() / "UPSTREAMS.lock.json", stage / "UPSTREAMS.lock.json")
            shutil.copy2(repo_root() / "VERSION", stage / "PRODUCT_VERSION")
        atomic_replace_dir(stage, skills / name, preserve)
        shutil.rmtree(stage.parent, ignore_errors=True)


def build_runtime(home: Path) -> None:
    state = home / "state" / "douyin-cloud-download"
    upstream = state / "upstream"
    destination = upstream / PINNED_COMMIT[:12]
    stage = staged_copy(repo_root() / "vendor" / "TikTokDownloader", upstream, ".runtime-stage-")
    try:
        migration_source: Path | None = destination if destination.is_dir() else None
        if migration_source is None and upstream.is_dir():
            older = [p for p in upstream.iterdir() if p.is_dir() and not p.name.startswith(".runtime-stage-") and (p / "Volume").exists()]
            if older:
                migration_source = max(older, key=lambda p: p.stat().st_mtime)
        if migration_source is not None:
            for relative in MUTABLE_RUNTIME_PATHS:
                old = migration_source / relative
                if old.exists():
                    new = stage / relative
                    if new.exists():
                        if new.is_dir():
                            shutil.rmtree(new)
                        else:
                            new.unlink()
                    copy_path(old, new)
        (stage / RUNTIME_MARKER).write_text(PINNED_COMMIT, encoding="utf-8")
        run(["uv", "sync", "--locked", "--python", "3.12", "--no-dev"], cwd=stage)
        adapter = load_adapter(repo_root() / "skills" / "douyin-cloud-download" / "scripts" / "douyin_cloud.py")
        adapter.contract_check(stage)
        adapter.write_runtime_manifest(stage)
        ok, error = adapter.runtime_integrity(stage)
        if not ok:
            raise RuntimeError(error or "runtime integrity verification failed")
        atomic_replace_dir(stage, destination)
    finally:
        shutil.rmtree(stage.parent, ignore_errors=True)
    (state / "jobs").mkdir(parents=True, exist_ok=True)
    (state / "history").mkdir(parents=True, exist_ok=True)


def parse_skill_version(skill_file: Path) -> str | None:
    try:
        text = skill_file.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    match = re.search(r"(?m)^version:\s*([0-9]+(?:\.[0-9]+){2})\s*$", text)
    return match.group(1) if match else None


def official_quark_config(timeout: int = 30) -> tuple[str, str]:
    req_id = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    url = f"{QUARK_CONFIG_URL}?req_id={req_id}"
    request = urllib.request.Request(url, headers={"User-Agent": "douyin-cloud-download-installer/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    candidates = []
    if isinstance(data, dict):
        candidates.extend([data.get("data", {}).get("config") if isinstance(data.get("data"), dict) else None,
                           data.get("config"), data.get("data"), data])
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("qkPan"):
            return str(candidate.get("qkPanVersion") or ""), str(candidate["qkPan"])
    raise RuntimeError("Quark skill_config did not return qkPanVersion/qkPan")


def official_baidu_skill_version(timeout: int = 30) -> str:
    request = urllib.request.Request(BAIDU_VERSION_URL, headers={"User-Agent": "douyin-cloud-download-installer/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        value = response.read().decode("utf-8-sig").strip()
    if not re.fullmatch(r"v[0-9]+(?:\.[0-9]+){2}", value):
        raise RuntimeError(f"Baidu upstream VERSION is invalid: {value!r}")
    return value


def validate_official_https(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise RuntimeError("Quark package URL must use HTTPS")
    if host not in QUARK_ALLOWED_HOSTS:
        raise RuntimeError(f"Quark package host is outside the official allowlist: {host}")


def locate_quark_root(extract_root: Path) -> Path:
    candidates = [extract_root]
    candidates.extend(p.parent for p in extract_root.rglob("SKILL.md"))
    seen: set[Path] = set()
    for root in candidates:
        root = root.resolve()
        if root in seen:
            continue
        seen.add(root)
        required = [root / "SKILL.md", root / "scripts" / "install.sh", root / "scripts" / "quark-drive.cjs"]
        if all(p.is_file() for p in required):
            return root
    raise RuntimeError("Quark package is missing SKILL.md/scripts/install.sh/scripts/quark-drive.cjs")


def install_quark(home: Path) -> dict[str, Any]:
    version, package_url = official_quark_config()
    if version != QUARK_VERSION:
        raise RuntimeError(f"Quark advertised version is {version or 'unknown'}, expected fixed {QUARK_VERSION}; review upstream before changing the pin")
    validate_official_https(package_url)
    skills = home / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".quark-download-", dir=skills))
    archive = temp_root / "skill.zip"
    extract = temp_root / "extract"
    try:
        request = urllib.request.Request(package_url, headers={"User-Agent": "douyin-cloud-download-installer/1"})
        with urllib.request.urlopen(request, timeout=120) as response, archive.open("wb") as out:
            shutil.copyfileobj(response, out)
        digest = sha256(archive)
        if digest != QUARK_SHA256:
            raise RuntimeError(
                f"Quark package SHA256 does not match the reviewed lock: expected {QUARK_SHA256}, got {digest}"
            )
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract)
        root = locate_quark_root(extract)
        if parse_skill_version(root / "SKILL.md") != QUARK_VERSION:
            raise RuntimeError("Quark package SKILL.md version does not match the fixed version")
        cli = run(["node", str(root / "scripts" / "quark-drive.cjs"), "--version"], capture=True, check=False)
        cli_text = ((cli.stdout or "") + "\n" + (cli.stderr or "")).strip()
        if cli.returncode != 0 or QUARK_VERSION not in cli_text:
            raise RuntimeError(f"Quark CLI version check failed: {cli_text or 'no output'}")
        syntax = run([str(find_bash() or "bash"), "-n", str(root / "scripts" / "install.sh")], capture=True, check=False)
        if syntax.returncode != 0:
            raise RuntimeError("Quark install.sh syntax check failed")
        candidate = temp_root / "candidate"
        shutil.copytree(root, candidate)
        receipt = {
            "schema_version": 2,
            "provider": "quark",
            "version": QUARK_VERSION,
            "sha256": digest,
            "trusted_sha256": QUARK_SHA256,
            "product_version": PRODUCT_VERSION,
            "source_url": package_url,
            "installed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
        (candidate / RECEIPT_NAME).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        atomic_replace_dir(candidate, skills / "quarkclouddrive", ("codex",))
        return receipt
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def adapter_path(home: Path) -> Path:
    return home / "skills" / "douyin-cloud-download" / "scripts" / "douyin_cloud.py"


def runtime_path(home: Path) -> Path:
    return home / "state" / "douyin-cloud-download" / "upstream" / PINNED_COMMIT[:12]


def adapter_doctor(home: Path, bundle: str | None = None) -> dict[str, Any]:
    path = adapter_path(home)
    if not path.is_file():
        return {"ready": False, "error": "adapter_missing"}
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    command = [sys.executable, str(path), "doctor", "--json"]
    if bundle is not None:
        command.append("--bundle")
        if bundle:
            command.append(bundle)
    result = run(command, capture=True, check=False, env=env)
    lines = [line for line in (result.stdout or "").splitlines() if line.strip().startswith("{")]
    if not lines:
        return {"ready": False, "error": (result.stderr or "doctor_failed").strip()}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"ready": False, "error": "doctor_invalid_json"}


def quark_state(home: Path) -> dict[str, Any]:
    root = home / "skills" / "quarkclouddrive"
    version = parse_skill_version(root / "SKILL.md")
    receipt = None
    try:
        receipt = json.loads((root / RECEIPT_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    cli_ok = False
    cli_version = None
    cli = root / "scripts" / "quark-drive.cjs"
    if cli.is_file() and shutil.which("node"):
        result = run(["node", str(cli), "--version"], capture=True, check=False)
        text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        cli_version = text.splitlines()[0] if text else None
        cli_ok = result.returncode == 0 and QUARK_VERSION in text
    receipt_integrity = bool(
        isinstance(receipt, dict)
        and receipt.get("version") == QUARK_VERSION
        and receipt.get("sha256") == QUARK_SHA256
    )
    return {"installed": root.is_dir(), "version": version, "version_ok": version == QUARK_VERSION,
            "cli_ok": cli_ok, "cli_version": cli_version, "integrity_ok": receipt_integrity, "receipt": receipt}


def baidu_state(home: Path) -> dict[str, Any]:
    root = home / "skills" / "baidu-drive"
    try:
        version = (root / "VERSION").read_text(encoding="utf-8-sig").strip()
    except OSError:
        version = None
    return {"installed": root.is_dir(), "version": version, "version_ok": version == BAIDU_SKILL_VERSION,
            "bdpan": command_version("bdpan", ["version"])}


def doctor(home: Path, bundle: str | None = None) -> dict[str, Any]:
    douyin = adapter_doctor(home, bundle)
    quark = quark_state(home)
    baidu = baidu_state(home)
    return {
        "ok": preflight()["base_ready"]["ok"] and bool(douyin.get("checks", {}).get("runtime_integrity")) and quark["version_ok"] and quark["integrity_ok"] and baidu["version_ok"],
        "product_version": PRODUCT_VERSION,
        "current_release": read_current_release(home),
        "codex_home": str(home),
        "preflight": preflight(),
        "douyin": douyin,
        "quark": quark,
        "baidu": baidu,
    }


def install_all(home: Path, *, include_baidu_cli: bool = False) -> dict[str, Any]:
    ensure_preflight()
    install_bundled_skills(home)
    build_runtime(home)
    quark_receipt = install_quark(home)
    if include_baidu_cli:
        run([str(find_bash() or "bash"), "./scripts/install.sh", "--yes"], cwd=home / "skills" / "baidu-drive")
    installed_release = release_metadata(RELEASE_CONFIG)
    installed_release["installed_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    write_current_release(home, installed_release)
    return {"ok": True, "product_version": PRODUCT_VERSION, "quark_receipt": quark_receipt, "doctor": doctor(home)}


def repair_all(home: Path) -> dict[str, Any]:
    ensure_preflight()
    backup = migration_backup(home)
    snapshot = snapshot_current_release(home)
    try:
        result = install_all(home, include_baidu_cli=False)
    except Exception:
        if snapshot:
            rollback_release(home, str(snapshot["snapshot_id"]))
        raise
    cleanup = cleanup_old_versions(home, keep=2)
    result["migration_backup"] = str(backup)
    result["rollback_snapshot"] = snapshot
    result["snapshot_cleanup"] = cleanup
    return result


def upgrade_all(home: Path) -> dict[str, Any]:
    ensure_preflight()
    backup = migration_backup(home)
    snapshot = snapshot_current_release(home)
    project_adapter = repo_root() / "skills" / "douyin-cloud-download" / "scripts" / "douyin_cloud.py"
    migrations = migrate_with_project_adapter(home, load_adapter, project_adapter)
    try:
        result = install_all(home, include_baidu_cli=False)
    except Exception:
        if snapshot:
            rollback_release(home, str(snapshot["snapshot_id"]))
        raise
    cleanup = cleanup_old_versions(home, keep=2)
    result["migration_backup"] = str(backup)
    result["migrations"] = migrations
    result["rollback_snapshot"] = snapshot
    result["snapshot_cleanup"] = cleanup
    return result


def check_upstreams() -> dict[str, Any]:
    result: dict[str, Any] = {"ok": True}
    git = run(["git", "ls-remote", "https://github.com/JoeanAmier/TikTokDownloader.git", "refs/heads/master"], capture=True, check=False)
    remote = (git.stdout or "").split("\t", 1)[0].strip() if git.returncode == 0 else None
    result["douk"] = {"fixed": PINNED_COMMIT, "remote_master": remote, "newer_than_fixed": bool(remote and remote != PINNED_COMMIT)}
    try:
        qver, qurl = official_quark_config()
        validate_official_https(qurl)
        result["quark"] = {"fixed": QUARK_VERSION, "advertised": qver, "newer_than_fixed": qver != QUARK_VERSION,
                           "package_host": urllib.parse.urlparse(qurl).hostname}
    except Exception as exc:
        result["quark"] = {"fixed": QUARK_VERSION, "check_error": str(exc)}
        result["ok"] = False
    baidu_install = repo_root() / "skills" / "baidu-drive" / "scripts" / "install.sh"
    text = baidu_install.read_text(encoding="utf-8-sig", errors="replace")
    cli_match = re.search(r'(?m)^VERSION="([^"]+)"', text)
    bundled_baidu = (repo_root() / "skills" / "baidu-drive" / "VERSION").read_text(encoding="utf-8-sig").strip()
    try:
        upstream_baidu = official_baidu_skill_version()
        result["baidu"] = {"fixed_skill": BAIDU_SKILL_VERSION, "bundled_skill": bundled_baidu,
                           "upstream_skill": upstream_baidu, "newer_than_fixed": upstream_baidu != BAIDU_SKILL_VERSION,
                           "installer_cli": cli_match.group(1) if cli_match else None}
    except Exception as exc:
        result["baidu"] = {"fixed_skill": BAIDU_SKILL_VERSION, "bundled_skill": bundled_baidu,
                           "installer_cli": cli_match.group(1) if cli_match else None, "check_error": str(exc)}
        result["ok"] = False
    return result


def choose_drive(requested: str, quick: bool) -> str:
    if requested != "ask":
        return requested
    if quick:
        return "quark"
    print("选择首次要授权的网盘：1=夸克 2=百度 3=两个 4=跳过")
    return {"2": "baidu", "3": "both", "4": "skip"}.get(input("输入 1-4: ").strip(), "quark")


def confirm(prompt: str, quick: bool, dry_run: bool) -> bool:
    if dry_run:
        return False
    if quick:
        return True
    answer = input(f"{prompt} [Y/n] ").strip().lower()
    return answer in {"", "y", "yes"}


def onboard(home: Path, drive: str, quick: bool, dry_run: bool) -> int:
    ensure_preflight()
    selected = choose_drive(drive, quick)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    douyin_ready = False
    if confirm("现在配置抖音 Cookie？", quick, dry_run):
        result = run([sys.executable, str(adapter_path(home)), "configure"], env=env, check=False)
        douyin_ready = result.returncode == 0 and bool(adapter_doctor(home).get("ready"))
    else:
        douyin_ready = bool(adapter_doctor(home).get("ready"))

    quark_ready = selected not in {"quark", "both"}
    if selected in {"quark", "both"}:
        qroot = home / "skills" / "quarkclouddrive"
        if confirm("现在授权夸克网盘？", quick, dry_run):
            q = run(["node", str(qroot / "scripts" / "quark-drive.cjs"), "login"], cwd=qroot, check=False)
            quark_ready = q.returncode == 0
        elif dry_run:
            quark_ready = False

    baidu_ready = selected not in {"baidu", "both"}
    if selected in {"baidu", "both"}:
        broot = home / "skills" / "baidu-drive"
        if confirm("现在授权百度网盘？", quick, dry_run):
            if not shutil.which("bdpan"):
                run([str(find_bash() or "bash"), "./scripts/install.sh", "--yes"], cwd=broot)
            login = run(
                [str(find_bash() or "bash"), "./scripts/login.sh", "--continue-task", "--quiet", "--no-welcome"],
                cwd=broot,
                check=False,
            )
            who = run(["bdpan", "whoami"], capture=True, check=False) if login.returncode == 0 else None
            baidu_ready = bool(who and who.returncode == 0)
        elif dry_run:
            baidu_ready = False

    required_cloud = ((selected == "skip") or (selected == "quark" and quark_ready) or
                      (selected == "baidu" and baidu_ready) or (selected == "both" and quark_ready and baidu_ready))
    payload = {"ok": douyin_ready and required_cloud, "drive": selected, "douyin_ready": douyin_ready,
               "quark_ready": quark_ready if selected in {"quark", "both"} else None,
               "baidu_ready": baidu_ready if selected in {"baidu", "both"} else None}
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["ok"] else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home")
    sub = parser.add_subparsers(dest="command", required=True)
    install_p = sub.add_parser("install")
    install_p.add_argument("--install-baidu-cli", action="store_true")
    onboard_p = sub.add_parser("onboard")
    onboard_p.add_argument("--drive", choices=("ask", "quark", "baidu", "both", "skip"), default="ask")
    onboard_p.add_argument("--quick-start", action="store_true")
    onboard_p.add_argument("--dry-run", action="store_true")
    doctor_p = sub.add_parser("doctor")
    doctor_p.add_argument("--bundle", nargs="?", const="")
    sub.add_parser("repair")
    sub.add_parser("upgrade")
    sub.add_parser("check-upstreams")
    sub.add_parser("versions")
    rollback_p = sub.add_parser("rollback")
    rollback_p.add_argument("snapshot_id", nargs="?")
    cleanup_p = sub.add_parser("cleanup-old-versions")
    cleanup_p.add_argument("--keep", type=int, default=2)
    args = parser.parse_args()
    home = codex_home(args.codex_home)
    try:
        if args.command == "install":
            data = install_all(home, include_baidu_cli=args.install_baidu_cli)
        elif args.command == "repair":
            data = repair_all(home)
        elif args.command == "upgrade":
            data = upgrade_all(home)
        elif args.command == "doctor":
            data = doctor(home, args.bundle)
        elif args.command == "check-upstreams":
            data = check_upstreams()
        elif args.command == "versions":
            data = {"ok": True, "current_release": read_current_release(home), "versions": list_versions(home)}
        elif args.command == "rollback":
            data = rollback_release(home, args.snapshot_id)
        elif args.command == "cleanup-old-versions":
            data = cleanup_old_versions(home, keep=args.keep)
        elif args.command == "onboard":
            return onboard(home, args.drive, args.quick_start, args.dry_run)
        else:
            raise AssertionError(args.command)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if data.get("ok", False) else 2
    except (RuntimeError, OSError, urllib.error.URLError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
