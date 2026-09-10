from __future__ import annotations

from typing import Any, TypedDict


class ErrorState(TypedDict):
    code: str
    name: str
    message: str
    cause: str
    retryable: bool
    recovery: str


class UploadState(TypedDict, total=False):
    status: str
    remote_path: str
    message: str
    updated_at: str


class JobManifest(TypedDict, total=False):
    schema_version: int
    job_id: str
    created_at: str
    updated_at: str
    completed_at: str
    state: str
    status: str
    download_attempts: int
    mode: str
    source_urls: list[str]
    options: dict[str, Any]
    payload_path: str
    cloud_root: str
    cloud_layout: str
    author_folders: list[dict[str, Any]]
    requested_destinations: list[str]
    files: list[dict[str, Any]]
    file_count: int
    total_size: int
    uploads: dict[str, UploadState]
    keep_local: bool
    local_files_removed: bool
    error: ErrorState | None


class RuntimeReceipt(TypedDict):
    schema_version: int
    commit: str
    generated_at: str
    files: dict[str, str]
