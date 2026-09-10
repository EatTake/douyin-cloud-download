from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import error_payload


CURRENT_JOB_SCHEMA = 3


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False,
    )
    temp = Path(handle.name)
    try:
        with handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        with contextlib.suppress(OSError):
            temp.unlink()


def migrate_job_manifest(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    migrated = dict(data)
    version = int(migrated.get("schema_version") or 1)
    if version > CURRENT_JOB_SCHEMA:
        raise RuntimeError(f"job schema {version} is newer than supported schema {CURRENT_JOB_SCHEMA}")
    changed = version != CURRENT_JOB_SCHEMA
    if version < 2:
        migrated.setdefault("state", migrated.get("status", "created"))
        migrated.setdefault("download_attempts", 0)
        migrated.setdefault("files", [])
        migrated.setdefault("file_count", len(migrated.get("files", [])))
        migrated.setdefault("total_size", 0)
        migrated.setdefault("author_folders", [])
    if version < 3:
        error = migrated.get("error")
        if isinstance(error, dict) and not str(error.get("code", "")).startswith("DCD-"):
            legacy_name = str(error.get("name") or error.get("code") or "unknown")
            migrated["error"] = error_payload(legacy_name, str(error.get("message") or legacy_name))
        migrated.setdefault("local_files_removed", False)
    migrated["schema_version"] = CURRENT_JOB_SCHEMA
    requested = [str(item) for item in migrated.get("requested_destinations", [])]
    uploads = migrated.get("uploads")
    if not isinstance(uploads, dict):
        uploads = {}
        changed = True
    for drive in requested:
        if drive not in uploads:
            uploads[drive] = {"status": "pending"}
            changed = True
    migrated["uploads"] = uploads
    return migrated, changed


def load_and_migrate(path: Path, *, write_back: bool = True) -> tuple[dict[str, Any], bool]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"manifest must contain an object: {path}")
    migrated, changed = migrate_job_manifest(raw)
    if changed and write_back:
        atomic_json(path, migrated)
    return migrated, changed


def migrate_all_manifests(state_root: Path) -> dict[str, Any]:
    scanned = 0
    migrated_count = 0
    paths = list((state_root / "jobs").glob("*/manifest.json")) + list((state_root / "history").glob("*.json"))
    for path in paths:
        scanned += 1
        _, changed = load_and_migrate(path)
        migrated_count += int(changed)
    atomic_json(state_root / "state-schema.json", {"schema_version": 1, "job_manifest_schema": CURRENT_JOB_SCHEMA})
    return {"ok": True, "scanned": scanned, "migrated": migrated_count, "job_manifest_schema": CURRENT_JOB_SCHEMA}
