from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ReleaseConfig:
    product_version: str
    douk_commit: str
    douk_repository: str
    quark_version: str
    quark_config_url: str
    quark_allowed_hosts: frozenset[str]
    quark_sha256: str
    baidu_skill_version: str
    baidu_repository: str
    baidu_version_url: str
    baidu_installer_sha256: dict[str, str]
    reviewed_at: str
    raw_lock: dict[str, Any]


def _https(value: str, field: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError(f"{field} must be an absolute HTTPS URL")
    return value


def _sha256(value: str, field: str) -> str:
    value = value.lower()
    if not SHA256_RE.fullmatch(value):
        raise RuntimeError(f"{field} must be a lowercase SHA256 digest")
    return value


def load_release_config(root: Path) -> ReleaseConfig:
    version = (root / "VERSION").read_text(encoding="utf-8-sig").strip()
    if not SEMVER_RE.fullmatch(version):
        raise RuntimeError(f"VERSION is not semantic x.y.z: {version!r}")
    raw = json.loads((root / "UPSTREAMS.lock.json").read_text(encoding="utf-8-sig"))
    if raw.get("schema_version") != 1:
        raise RuntimeError("unsupported UPSTREAMS.lock.json schema_version")
    try:
        douk = raw["douk"]
        quark = raw["quark"]
        baidu = raw["baidu"]
        commit = str(douk["commit"]).lower()
        if not GIT_SHA_RE.fullmatch(commit):
            raise RuntimeError("douk.commit must be a full 40-character Git SHA")
        quark_version = str(quark["version"])
        if not SEMVER_RE.fullmatch(quark_version):
            raise RuntimeError("quark.version must use x.y.z")
        baidu_version = str(baidu["skill_version"])
        if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", baidu_version):
            raise RuntimeError("baidu.skill_version must use vx.y.z")
        hosts = frozenset(str(host).lower() for host in quark["allowed_hosts"])
        if not hosts:
            raise RuntimeError("quark.allowed_hosts cannot be empty")
        installer_hashes = {
            str(platform): _sha256(str(digest), f"baidu.installer_sha256.{platform}")
            for platform, digest in dict(baidu["installer_sha256"]).items()
        }
        return ReleaseConfig(
            product_version=version,
            douk_commit=commit,
            douk_repository=_https(str(douk["repository"]), "douk.repository"),
            quark_version=quark_version,
            quark_config_url=_https(str(quark["config_url"]), "quark.config_url"),
            quark_allowed_hosts=hosts,
            quark_sha256=_sha256(str(quark["sha256"]), "quark.sha256"),
            baidu_skill_version=baidu_version,
            baidu_repository=_https(str(baidu["repository"]), "baidu.repository"),
            baidu_version_url=_https(str(baidu["version_url"]), "baidu.version_url"),
            baidu_installer_sha256=installer_hashes,
            reviewed_at=str(raw["reviewed_at"]),
            raw_lock=raw,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid UPSTREAMS.lock.json: {exc}") from exc


def release_metadata(config: ReleaseConfig) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "product_version": config.product_version,
        "reviewed_at": config.reviewed_at,
        "upstreams": config.raw_lock,
    }
