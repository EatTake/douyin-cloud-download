from __future__ import annotations

import datetime as dt
import json
import os
import zipfile
from pathlib import Path
from typing import Any, Callable


def migration_backup(home: Path) -> Path:
    """Back up schema-bearing metadata before an upgrade without copying media payloads."""
    state = home / "state" / "douyin-cloud-download"
    root = state / "migration-backups"
    root.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / f"metadata-{stamp}.zip"
    suffix = 2
    while target.exists():
        target = root / f"metadata-{stamp}-{suffix}.zip"
        suffix += 1
    candidates: list[tuple[Path, str]] = []
    for manifest in (state / "jobs").glob("*/manifest.json") if (state / "jobs").is_dir() else ():
        candidates.append((manifest, f"state/jobs/{manifest.parent.name}/manifest.json"))
    for receipt in (state / "history").glob("*.json") if (state / "history").is_dir() else ():
        candidates.append((receipt, f"state/history/{receipt.name}"))
    current = state / "current-release.json"
    if current.is_file():
        candidates.append((current, "state/current-release.json"))
    for relative in (
        "skills/quarkclouddrive/.douyin-cloud-download-receipt.json",
        "skills/baidu-drive/VERSION",
    ):
        path = home / relative
        if path.is_file():
            candidates.append((path, relative))
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for source, archive_name in candidates:
            zf.write(source, archive_name)
        zf.writestr("backup.json", json.dumps({
            "schema_version": 1,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "file_count": len(candidates),
        }, indent=2))
    if os.name != "nt":
        target.chmod(0o600)
    return target


def migrate_with_project_adapter(home: Path, adapter_loader: Callable[[Path], Any], adapter_path: Path) -> dict[str, Any]:
    adapter = adapter_loader(adapter_path)
    if not hasattr(adapter, "migrate_all_manifests"):
        raise RuntimeError("project adapter does not expose migrate_all_manifests")
    return dict(adapter.migrate_all_manifests(home / "state" / "douyin-cloud-download"))
