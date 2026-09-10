from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    cause: str
    retryable: bool
    recovery: str


ERROR_CODES = {
    "missing_executable": "DCD-ENV-001", "command_failed": "DCD-ENV-002",
    "runtime_missing": "DCD-RUNTIME-001", "runtime_commit_mismatch": "DCD-RUNTIME-002",
    "runtime_integrity_failed": "DCD-RUNTIME-003", "upstream_contract_changed": "DCD-RUNTIME-004",
    "disclaimer_not_accepted": "DCD-AUTH-001", "douyin_cookie_missing": "DCD-AUTH-002",
    "consent_required": "DCD-AUTH-003", "invalid_encipher": "DCD-INPUT-001",
    "invalid_job_id": "DCD-INPUT-002", "urls_required": "DCD-INPUT-003",
    "saved_folder_scope_required": "DCD-INPUT-004", "invalid_date_range": "DCD-INPUT-005",
    "account_options_invalid": "DCD-INPUT-006", "invalid_pages": "DCD-INPUT-007",
    "invalid_payload_path": "DCD-INPUT-008", "invalid_remote_path": "DCD-INPUT-009",
    "unsupported_mode": "DCD-INPUT-010", "invalid_works_urls": "DCD-DOWNLOAD-001",
    "invalid_account_url": "DCD-DOWNLOAD-002", "account_access_failed": "DCD-DOWNLOAD-003",
    "invalid_mix_url": "DCD-DOWNLOAD-004", "mix_download_failed": "DCD-DOWNLOAD-005",
    "invalid_owner_url": "DCD-DOWNLOAD-006", "saved_folders_unavailable": "DCD-DOWNLOAD-007",
    "saved_folder_not_found": "DCD-DOWNLOAD-008", "saved_music_unavailable": "DCD-DOWNLOAD-009",
    "upstream_failed": "DCD-DOWNLOAD-010", "no_media_downloaded": "DCD-DOWNLOAD-011",
    "interrupted": "DCD-DOWNLOAD-012", "upstream_exception": "DCD-DOWNLOAD-013",
    "download_in_progress": "DCD-JOB-001",
    "job_busy": "DCD-JOB-002", "job_not_found": "DCD-JOB-003",
    "job_not_recoverable": "DCD-JOB-004", "job_not_resumable": "DCD-JOB-005",
    "payload_missing": "DCD-JOB-006", "job_not_uploadable": "DCD-UPLOAD-001",
    "drive_not_requested": "DCD-UPLOAD-002", "uploads_incomplete": "DCD-UPLOAD-003",
    "unsafe_cleanup_target": "DCD-UPLOAD-004", "ffmpeg_missing": "DCD-LIVE-001",
    "invalid_live_url": "DCD-LIVE-002", "live_not_active": "DCD-LIVE-003",
    "live_quality_invalid": "DCD-LIVE-004", "live_recording_failed": "DCD-LIVE-005",
}

RETRYABLE = {
    "command_failed", "account_access_failed", "mix_download_failed", "saved_folders_unavailable",
    "saved_music_unavailable", "upstream_failed", "no_media_downloaded", "interrupted", "upstream_exception",
    "download_in_progress", "job_busy", "uploads_incomplete", "live_not_active", "live_recording_failed",
}

RECOVERY = {
    "runtime_missing": "Run install or repair.",
    "runtime_commit_mismatch": "Run repair to restore the reviewed runtime.",
    "runtime_integrity_failed": "Run repair and do not reuse the modified runtime.",
    "upstream_contract_changed": "Review the upstream integration before changing the pin.",
    "disclaimer_not_accepted": "Run configure and accept the upstream disclaimer after reading it.",
    "douyin_cookie_missing": "Run configure and enter a valid Douyin Cookie.",
    "ffmpeg_missing": "Install ffmpeg and run doctor again.",
    "interrupted": "Run recover or resume-download for the retained job.",
    "uploads_incomplete": "Retry failed or pending uploads, record success, then finalize.",
    "payload_missing": "Create a new download job because the retained payload is unavailable.",
}


def error_spec(name: str) -> ErrorSpec:
    code = ERROR_CODES.get(name, "DCD-UNKNOWN-999")
    retryable = name in RETRYABLE
    cause = name.replace("_", " ").capitalize() + "."
    recovery = RECOVERY.get(name) or (
        "Retry the retained operation after correcting the transient condition."
        if retryable else "Correct the reported condition before retrying."
    )
    return ErrorSpec(code, cause, retryable, recovery)


def error_payload(name: str, message: str) -> dict[str, Any]:
    spec = error_spec(name)
    return {
        "code": spec.code, "name": name, "message": message, "cause": spec.cause,
        "retryable": spec.retryable, "recovery": spec.recovery,
    }
