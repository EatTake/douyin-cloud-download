# Douyin Cloud Download

[中文](README.md)

An installable Codex Skill bundle for downloading authorised Douyin media and archiving it to Quark Drive, Baidu Netdisk, or both.

Pinned upstreams: DouK-Downloader `df8aced70e476ae3330fa913186f3207b4843201`, official Quark Skill `1.0.19`, and official Baidu Skill `v1.7.5`. Install and upgrade use only these fixed revisions. `check-upstreams` is read-only and never follows upstream automatically.

The current product version is `1.0.0`. The root `VERSION` file is the product version source of truth, `UPSTREAMS.lock.json` contains the reviewed upstream versions, origins, and installer SHA256 values, and `CHANGELOG.md` records release history. Version tags trigger GitHub Release packaging with source archives and `SHA256SUMS`.

## Supported platforms

Formal support covers Windows x86_64 and Linux x86_64 (Ubuntu/Debian). Base requirements are Python 3.12, Git, uv, Node.js, and Bash. Windows requires Git Bash from Git for Windows; the controller rejects WSL/Linux Bash as the Windows Bash runtime. ffmpeg is required only for live recording.

`CODEX_HOME` is honoured when set. Otherwise the default is `%USERPROFILE%\.codex` on Windows and `$HOME/.codex` on Linux.

## Install

Windows:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1 -Onboard -QuickStart
```

Linux:

```bash
bash ./scripts/install.sh --onboard --quick-start
```

Add `-InstallBaiduCli` on Windows or `--install-baidu-cli` on Linux if the Baidu CLI should be installed during setup. To configure both drives later:

```powershell
.\scripts\onboard.ps1 -Drive both -QuickStart
```

```bash
bash ./scripts/onboard.sh --drive both --quick-start
```

Program files are replaced atomically while user state is preserved: DouK `Volume/`, optional `encipher.py`, jobs and history; Quark `codex/` auth/config; existing Baidu auth/config. The installed DouK runtime gets a SHA256 manifest and is verified before use. Quark installation accepts only an official HTTPS host, exact Skill version `1.0.19`, the expected package structure, and a matching CLI version, then writes an installation receipt.

## Maintenance

The shared controller is `scripts/setup.py`:

```text
python3.12 scripts/setup.py install
python3.12 scripts/setup.py onboard --drive both
python3.12 scripts/setup.py doctor
python3.12 scripts/setup.py doctor --bundle
python3.12 scripts/setup.py repair
python3.12 scripts/setup.py upgrade
python3.12 scripts/setup.py check-upstreams
python3.12 scripts/setup.py versions
python3.12 scripts/setup.py rollback [SNAPSHOT_ID]
python3.12 scripts/setup.py cleanup-old-versions --keep 2
```

Use `py -3.12` on Windows. `repair` rebuilds the pinned runtime and Skills while preserving state. Before installation, `upgrade` creates a metadata backup, migrates old job manifests, and creates a persistent rollback snapshot; an installation failure restores that snapshot automatically. The default retention is the two most recent previous releases. Rollback restores the matching Skills and DouK runtime together while preserving the current Cookie/provider auth state, `Volume/`, and optional `encipher.py`.

`doctor --bundle` writes a sanitized diagnostic ZIP containing system/runtime checks, recent rotating logs, job manifests, and current release metadata. Cookie, Authorization, access/refresh tokens, BDUSS, STOKEN, and URLs are redacted. Core failures keep the legacy top-level `error` name for existing consumers and add a stable `DCD-*` `error_code`, `cause`, `retryable`, and `recovery` metadata.

`upgrade` installs only versions already reviewed in `UPSTREAMS.lock.json`. If Quark advertises a version other than `1.0.19`, installation/upgrade stops. `check-upstreams` reports candidates only; changing the reviewed lock remains an explicit review step.

## Jobs and recovery

Cloud media is stored under `./抖音下载/[作者]/`. A job can be finalized and its local payload removed only after every requested destination is verified successful. With destination `both`, one failed upload keeps the payload.

```text
python scripts/douyin_cloud.py recover --job JOB_ID
python scripts/douyin_cloud.py resume-download --job JOB_ID
```

See `skills/douyin-cloud-download/SKILL.md` and `references/setup.md` for the full command surface and recovery rules.

## Verification

Automated checks are intentionally focused on environment, paths, runtime integrity, compatibility boundaries, and job state. Real provider flows remain manual acceptance tests.

```powershell
py -3.12 -m py_compile scripts/setup.py skills/douyin-cloud-download/scripts/douyin_cloud.py
py -3.12 skills/douyin-cloud-download/tests/test_douyin_cloud.py
py -3.12 scripts/setup.py check-upstreams
```

Manual acceptance should cover Douyin→Quark, Douyin→Baidu, a deliberate one-drive failure with `both`, interrupted download recovery, and cleanup only after all requested uploads succeed.

Only download media you own or are authorised to save. The bundle does not provide paid/private-content bypasses.

## Licensing

DouK-Downloader is retained as a GPL-3.0 upstream source snapshot in `vendor/TikTokDownloader`; see `vendor/TikTokDownloader/license`. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the remaining third-party boundaries.
