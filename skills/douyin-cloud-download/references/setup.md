# Setup and recovery

## First use

1. Run `python scripts/douyin_cloud.py bootstrap`.
2. Run `python scripts/douyin_cloud.py configure` in an interactive terminal.
3. Let the user read and accept DouK-Downloader's disclaimer, then paste their Douyin Cookie directly into that terminal. Never ask them to paste it into chat.
4. Run `python scripts/douyin_cloud.py doctor --json` and require `ready: true` before downloading.

The runtime lives under `$CODEX_HOME/state/douyin-cloud-download`. If `CODEX_HOME` is unset, the default is `%USERPROFILE%/.codex` on Windows and `$HOME/.codex` on Linux. `bootstrap` clones the exact commit `df8aced70e476ae3330fa913186f3207b4843201`, verifies `HEAD`, and installs its locked dependencies with uv and Python 3.12. The standalone bundle installer may instead copy its verbatim vendored snapshot and writes the same pinned revision plus a SHA256 runtime manifest. Neither path follows `master`.

## Standalone-bundle onboarding

Formal support covers Windows x86_64 and Linux x86_64 on Ubuntu/Debian. Base requirements are Python 3.12, Git, uv, Node.js, and Bash. Windows must use Git Bash from Git for Windows; WSL Bash is rejected as the Windows Bash runtime. ffmpeg is optional unless live recording is requested.

Windows installation and onboarding:

```powershell
.\scripts\install.ps1 -Onboard -QuickStart
.\scripts\onboard.ps1 -Drive both -QuickStart
```

Linux installation and onboarding:

```bash
./scripts/install.sh --onboard --quick-start
./scripts/onboard.sh --drive both --quick-start
```

The shared controller is `scripts/setup.py`. It exposes `doctor [--bundle]`, `repair`, `upgrade`, `check-upstreams`, `versions`, `rollback [SNAPSHOT_ID]`, and `cleanup-old-versions --keep N`.

The product version comes from the root `VERSION`; the reviewed DouK, Quark, and Baidu dependency metadata comes from `UPSTREAMS.lock.json`. `upgrade` performs preflight checks, creates a metadata-only migration backup, snapshots the currently installed Skills and matching DouK runtime, migrates retained job manifests to the current schema, and then installs the reviewed release. If installation fails, the snapshot is restored. Successful maintenance keeps the most recent two previous release snapshots by default.

Rollback restores the selected Skills and the corresponding DouK runtime as one release while preserving mutable user state: DouK `Volume/` and optional `encipher.py`, Quark `codex/`, and Baidu auth/config paths. `check-upstreams` is report-only and must never change the reviewed lock automatically.

`doctor --bundle` creates a sanitized ZIP with doctor/system information, recent rotating JSONL logs, retained manifests, and current release metadata. Cookie, Authorization, access/refresh tokens, BDUSS, STOKEN, and URLs are redacted. Command errors keep the historical `error` value for compatibility and add a stable `DCD-*` `error_code` plus `cause`, `retryable`, and `recovery` metadata.

- The guide explains how to copy the complete Cookie from a logged-in Douyin browser request, but never reads browser data itself. The user must paste it only into DouK-Downloader's local terminal, never into chat.
- Quark authorisation uses its official browser OAuth flow. If it is not completed, stop and let the user rerun the guide or follow the provider's official manual-code instructions.
- Baidu authorisation always uses the bundled `login.sh --continue-task` flow; do not invoke `bdpan login` directly or read its configuration file.
- The guide verifies only non-sensitive readiness state. It must not print Cookies, cloud tokens, or signed media URLs.

## Optional encipher.py

Upstream warns its encryption-parameter algorithms can expire. Do not search for, generate, or silently execute replacement code. When the user explicitly supplies a trusted `encipher.py`:

1. Tell them the file will be imported and executed by DouK-Downloader.
2. Run:

```text
python scripts/douyin_cloud.py install-encipher --file C:\absolute\path\encipher.py --i-understand-this-executes-code
```

The installer performs a non-executing AST check for `ABogus`, `XBogus`, and `XGnarly`, then copies the file into the pinned runtime. It does not validate the trustworthiness of the supplied code.

## Recovery signals

- `runtime_missing` or `runtime_commit_mismatch`: rerun `bootstrap`. A mismatched runtime is not overwritten; inspect or move it first.
- `runtime_integrity_failed`: run the repository `repair` command. The runtime manifest rejects modified immutable files before a download starts.
- `disclaimer_not_accepted`: rerun `configure` and accept only after reading.
- `douyin_cookie_missing`: rerun `configure` and enter the Cookie in the terminal.
- `ffmpeg_missing`: install ffmpeg and ensure it is on `PATH`; required for live recording.
- `no_media_downloaded`: Cookie, link access, or upstream encryption may have expired. Reconfigure Cookie first. Do not claim success.
- Authentication failures for a cloud drive are handled by that drive's existing Skill, not by this script.
- For interrupted jobs, run `recover --job JOB_ID`, inspect `show-job`, then use `resume-download --job JOB_ID` when applicable. Local payloads remain until every requested cloud destination has succeeded and `finalize` completes.
