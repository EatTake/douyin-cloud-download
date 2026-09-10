from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any


HEADER_SECRET_RE = re.compile(r"(?im)\b(cookie|authorization)\s*[:=]\s*[^\r\n]+")
TOKEN_SECRET_RE = re.compile(r"(?i)\b(access[_-]?token|refresh[_-]?token|bduss|stoken)\s*[:=]\s*([^\s,;]+)")
URL_RE = re.compile(r"https?://[^\s<>\"]+")
RUN_ID = uuid.uuid4().hex[:12]
MAX_LOG_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 3


def sanitize_message(value: str) -> str:
    value = URL_RE.sub("[REDACTED_URL]", value)
    value = HEADER_SECRET_RE.sub(lambda m: f"{m.group(1)}: [REDACTED]", value)
    value = TOKEN_SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)
    return value[:4000]


def sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_message(value)
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in {"cookie", "authorization", "access_token", "refresh_token", "bduss", "stoken"}:
                clean[str(key)] = "[REDACTED]"
            else:
                clean[str(key)] = sanitize_value(item)
        return clean
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    return value


def _rotate(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < MAX_LOG_BYTES:
        return
    path.with_suffix(path.suffix + f".{LOG_BACKUPS}").unlink(missing_ok=True)
    for index in range(LOG_BACKUPS - 1, 0, -1):
        source = path.with_suffix(path.suffix + f".{index}")
        if source.exists():
            os.replace(source, path.with_suffix(path.suffix + f".{index + 1}"))
    os.replace(path, path.with_suffix(path.suffix + ".1"))


def log_event(state_root: Path, event: str, *, job_id: str | None = None, **fields: Any) -> None:
    logs = state_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "douyin-cloud-download.jsonl"
    _rotate(path)
    record = {
        "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "correlation_id": RUN_ID, "run_id": RUN_ID, "job_id": job_id, "event": event, **sanitize_value(fields),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def create_diagnostic_bundle(state_root: Path, doctor: dict[str, Any], output: str | None = None) -> Path:
    diagnostics = state_root / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    if output:
        target = Path(output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = diagnostics / f"diagnostics-{stamp}.zip"
    temp_root = Path(tempfile.mkdtemp(prefix="dcd-diagnostics-"))
    try:
        system = {
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "platform": platform.platform(), "python": platform.python_version(),
            "correlation_id": RUN_ID,
            "doctor": sanitize_value(doctor),
        }
        (temp_root / "system.json").write_text(json.dumps(system, ensure_ascii=False, indent=2), encoding="utf-8")
        logs = state_root / "logs"
        if logs.is_dir():
            for path in logs.glob("douyin-cloud-download.jsonl*"):
                lines: list[str] = []
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        lines.append(json.dumps(sanitize_value(json.loads(line)), ensure_ascii=False, sort_keys=True))
                    except json.JSONDecodeError:
                        lines.append(sanitize_message(line))
                (temp_root / path.name).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        manifests = temp_root / "manifests"
        manifests.mkdir()
        paths = list((state_root / "jobs").glob("*/manifest.json")) + list((state_root / "history").glob("*.json"))
        for path in paths:
            try:
                data = sanitize_value(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
            name = f"{path.parent.name}-manifest.json" if path.name == "manifest.json" else path.name
            (manifests / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        codex_home = state_root.parent.parent
        metadata_dir = temp_root / "release"
        metadata_dir.mkdir()
        for name, source in {
            "current-release.json": state_root / "current-release.json",
            "state-schema.json": state_root / "state-schema.json",
            "PRODUCT_VERSION": codex_home / "skills" / "douyin-cloud-download" / "PRODUCT_VERSION",
            "UPSTREAMS.lock.json": codex_home / "skills" / "douyin-cloud-download" / "UPSTREAMS.lock.json",
        }.items():
            if not source.is_file():
                continue
            text = source.read_text(encoding="utf-8-sig", errors="replace")
            try:
                text = json.dumps(sanitize_value(json.loads(text)), ensure_ascii=False, indent=2, sort_keys=True)
            except json.JSONDecodeError:
                text = sanitize_message(text)
            (metadata_dir / name).write_text(text, encoding="utf-8")
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in temp_root.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(temp_root).as_posix())
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    if os.name != "nt":
        target.chmod(0o600)
    return target
