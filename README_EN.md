# Douyin Cloud Download

[中文](README.md)

An installable Codex Skill bundle for downloading authorised Douyin media and archiving it to Quark Drive, Baidu Netdisk, or both.

It contains:

- `skills/douyin-cloud-download`: the pinned DouK-Downloader adapter, job ledger, tests, and cloud-archive instructions.
- `skills/baidu-drive`: the complete Baidu Netdisk Skill used by the adapter.
- `vendor/TikTokDownloader`: the DouK-Downloader source pinned to `d3806386b392da7341397e18522acdd5283f2c81`.
- `scripts/install.ps1`: a clean-machine installer for the two local Skills, the pinned runtime, and the official Quark Drive Skill.

The installer obtains the Quark Drive Skill from its official published installation endpoint instead of committing its opaque runtime or any account data to this repository.

## Requirements

- Windows PowerShell 7
- Git, Python 3.12, `uv`, Node.js 16+, and Git Bash
- A Codex desktop installation
- Your own authorised Douyin account/session when the source requires it
- Your own Quark and/or Baidu Netdisk accounts

## Install

Clone this repository, then run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1 -Onboard -QuickStart
```

The installer never copies cookies, netdisk tokens, past jobs, search history, or downloaded media. It installs the bundled Douyin and Baidu Skills under the active Codex home, installs the pinned DouK runtime from `vendor/`, and retrieves the official Quark Skill into the same Skill directory. `-Onboard` starts the interactive first-use guide and `-QuickStart` removes its repeated confirmations; run `.\scripts\onboard.ps1` later to resume it.

The guide explains how to copy a complete Cookie from a logged-in Douyin browser request and accepts it only in the local DouK-Downloader terminal. It then starts the official Quark and/or Baidu authorisation flows selected by the user. It never reads browser Cookies, displays cloud tokens, or bypasses provider safety prompts.

The Baidu CLI deliberately remains an interactive step because it displays its own safety notice. To install it during setup, explicitly run:

```powershell
.\scripts\install.ps1 -InstallBaiduCli -Onboard
```

To configure both cloud drives in one pass after installation:

```powershell
.\scripts\onboard.ps1 -Drive both -QuickStart
```

Then complete the required interactive sign-ins:

```powershell
# Configure the Douyin disclaimer and Cookie only in this terminal.
uv run --project "$env:USERPROFILE\.codex\state\douyin-cloud-download\upstream\d3806386b392" python "$env:USERPROFILE\.codex\skills\douyin-cloud-download\scripts\douyin_cloud.py" configure

# Baidu Netdisk sign-in (after its CLI is installed).
bash "$env:USERPROFILE\.codex\skills\baidu-drive\scripts\login.sh"
```

For Quark Drive, ask Codex to perform a Quark action; it will initiate the official interactive login if the account is not authorised.

## Usage

Restart Codex after installation. Examples:

- `把这个抖音下载到夸克网盘`
- `批量下载这些抖音到百度和夸克`
- `下载这个抖音合集到夸克网盘`

Cloud media is always stored under `./抖音下载/[作者]/`. Core media is the default; ask explicitly for music or covers.

Only download material you own or are authorised to save. The bundle does not support paid/private-content bypasses or anti-signature bypass code.

## Verification

```powershell
python -m py_compile .\skills\douyin-cloud-download\scripts\douyin_cloud.py
python .\skills\douyin-cloud-download\tests\test_douyin_cloud.py
```

## Licensing

DouK-Downloader is included as a verbatim GPL-3.0 upstream snapshot; see [vendor/TikTokDownloader/license](vendor/TikTokDownloader/license). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the remaining component boundaries.
