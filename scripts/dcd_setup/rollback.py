from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterable


RELEASE_DIR = "releases"
CURRENT_RELEASE = "current-release.json"
MUTABLE_BY_SKILL = {
    "quarkclouddrive": ("codex",),
    "baidu-drive": ("codex", ".config", "config.json", "storage", "data"),
    "douyin-cloud-download": (),
}
RUNTIME_SNAPSHOT_EXCLUDES = {"Volume", "encipher.py", ".venv"}
RUNTIME_PRESERVE = ("Volume", "encipher.py")


def product_state(home: Path) -> Path:
    return home / "state" / "douyin-cloud-download"


def current_release_path(home: Path) -> Path:
    return product_state(home) / CURRENT_RELEASE


def _runtime_for_release(home: Path, release: dict[str, Any] | None) -> Path | None:
    if not isinstance(release, dict):
        return None
    try:
        commit = str(release["upstreams"]["douk"]["commit"])
    except (KeyError, TypeError):
        return None
    if len(commit) != 40:
        return None
    return product_state(home) / "upstream" / commit[:12]


def read_current_release(home: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(current_release_path(home).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def write_current_release(home: Path, metadata: dict[str, Any]) -> None:
    path = current_release_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _ignore_mutable(name: str):
    mutable = set(MUTABLE_BY_SKILL.get(name, ()))

    def ignore(directory: str, entries: list[str]) -> set[str]:
        if Path(directory).name == name:
            return {entry for entry in entries if entry in mutable}
        return set()

    return ignore


def snapshot_current_release(home: Path) -> dict[str, Any] | None:
    skills_root = home / "skills"
    installed = [name for name in MUTABLE_BY_SKILL if (skills_root / name).is_dir()]
    if not installed:
        return None
    state = product_state(home)
    release_root = state / RELEASE_DIR
    release_root.mkdir(parents=True, exist_ok=True)
    current = read_current_release(home) or {
        "schema_version": 1,
        "product_version": "legacy-unversioned",
        "captured_from_legacy_install": True,
    }
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_id = f"{stamp}-{str(current.get('product_version', 'unknown')).replace('/', '_')}"
    target = release_root / snapshot_id
    suffix = 2
    while target.exists():
        target = release_root / f"{snapshot_id}-{suffix}"
        suffix += 1
    target.mkdir()
    copied: list[str] = []
    for name in installed:
        source = skills_root / name
        shutil.copytree(source, target / "skills" / name, ignore=_ignore_mutable(name))
        copied.append(name)
    runtime = _runtime_for_release(home, current)
    runtime_commit: str | None = None
    if runtime and runtime.is_dir():
        runtime_commit = str(current["upstreams"]["douk"]["commit"])

        def ignore_runtime(directory: str, entries: list[str]) -> set[str]:
            return {entry for entry in entries if entry in RUNTIME_SNAPSHOT_EXCLUDES} if Path(directory) == runtime else set()

        shutil.copytree(runtime, target / "runtime", ignore=ignore_runtime)
    metadata = {
        "schema_version": 1,
        "snapshot_id": target.name,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "release": current,
        "skills": copied,
        "runtime_commit": runtime_commit,
    }
    (target / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return metadata


def _copy_path(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    elif src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _replace_skill(source: Path, destination: Path, preserve: Iterable[str]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage_parent = Path(tempfile.mkdtemp(prefix=f".{destination.name}-rollback-", dir=destination.parent))
    stage = stage_parent / "payload"
    backup: Path | None = None
    try:
        shutil.copytree(source, stage)
        for relative in preserve:
            live = destination / relative
            if live.exists():
                target = stage / relative
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True) if target.is_dir() else target.unlink()
                _copy_path(live, target)
        if destination.exists():
            backup = destination.with_name(f"{destination.name}.rollback-backup-{uuid.uuid4().hex[:8]}")
            os.replace(destination, backup)
        os.replace(stage, destination)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        if backup and backup.exists():
            os.replace(backup, destination)
        raise
    finally:
        if backup:
            shutil.rmtree(backup, ignore_errors=True)
        shutil.rmtree(stage_parent, ignore_errors=True)


def _replace_runtime(source: Path, destination: Path, preserve_source: Path | None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage_parent = Path(tempfile.mkdtemp(prefix=".runtime-rollback-", dir=destination.parent))
    stage = stage_parent / "payload"
    backup: Path | None = None
    try:
        shutil.copytree(source, stage)
        if preserve_source and preserve_source.is_dir():
            for relative in RUNTIME_PRESERVE:
                live = preserve_source / relative
                if not live.exists():
                    continue
                target = stage / relative
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True) if target.is_dir() else target.unlink()
                _copy_path(live, target)
        if destination.exists():
            backup = destination.with_name(f"{destination.name}.rollback-backup-{uuid.uuid4().hex[:8]}")
            os.replace(destination, backup)
        os.replace(stage, destination)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        if backup and backup.exists():
            os.replace(backup, destination)
        raise
    finally:
        if backup:
            shutil.rmtree(backup, ignore_errors=True)
        shutil.rmtree(stage_parent, ignore_errors=True)


def list_versions(home: Path) -> list[dict[str, Any]]:
    root = product_state(home) / RELEASE_DIR
    items: list[dict[str, Any]] = []
    if not root.is_dir():
        return items
    for path in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        try:
            metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(metadata, dict):
            items.append(metadata)
    return items


def rollback(home: Path, snapshot_id: str | None = None) -> dict[str, Any]:
    versions = list_versions(home)
    if not versions:
        raise RuntimeError("no rollback snapshots are available")
    selected = next((item for item in versions if item.get("snapshot_id") == snapshot_id), None) if snapshot_id else versions[0]
    if selected is None:
        raise RuntimeError(f"rollback snapshot not found: {snapshot_id}")
    root = product_state(home) / RELEASE_DIR / str(selected["snapshot_id"])
    live_release = read_current_release(home)
    live_runtime = _runtime_for_release(home, live_release)
    before = snapshot_current_release(home)
    for name in selected.get("skills", []):
        source = root / "skills" / str(name)
        if not source.is_dir():
            raise RuntimeError(f"rollback snapshot is incomplete: {name}")
        _replace_skill(source, home / "skills" / str(name), MUTABLE_BY_SKILL.get(str(name), ()))
    release = selected.get("release")
    runtime_commit = selected.get("runtime_commit")
    runtime_source = root / "runtime"
    if runtime_commit:
        if not runtime_source.is_dir():
            raise RuntimeError("rollback snapshot is incomplete: runtime")
        runtime_destination = product_state(home) / "upstream" / str(runtime_commit)[:12]
        _replace_runtime(runtime_source, runtime_destination, live_runtime)
    if isinstance(release, dict):
        write_current_release(home, release)
    return {"ok": True, "rolled_back_to": selected["snapshot_id"], "safety_snapshot": before}


def cleanup_old_versions(home: Path, keep: int = 2) -> dict[str, Any]:
    if keep < 0:
        raise RuntimeError("keep must be >= 0")
    versions = list_versions(home)
    removed: list[str] = []
    root = product_state(home) / RELEASE_DIR
    for metadata in versions[keep:]:
        snapshot_id = str(metadata.get("snapshot_id", ""))
        target = root / snapshot_id
        if snapshot_id and target.is_dir() and target.parent == root:
            shutil.rmtree(target)
            removed.append(snapshot_id)
    return {"ok": True, "kept": min(keep, len(versions)), "removed": removed}
