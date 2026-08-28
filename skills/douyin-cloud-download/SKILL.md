---
name: douyin-cloud-download
description: Download one or many authorized Douyin videos, image posts, live photos, accounts, favorites, collections, saved folders, saved music, or live streams with pinned DouK-Downloader, then archive the media to Quark Drive, Baidu Netdisk, or both. Use when the user asks to save/download/record Douyin content to a cloud drive; do not use for comments, search, trending lists, profiles, analytics, TikTok, or bypassing paid/private access.
---

# Douyin Cloud Download

Turn a natural-language Douyin download request into a local job, then hand its payload to the existing Quark and/or Baidu Drive skill. Default to Quark and core media only.

## Boundaries

- Download only content the user owns or is authorized to access.
- Do not support paid/private-content bypasses, TikTok, comments, search, trending lists, profile export, analytics, Web UI/API, or clipboard monitoring.
- Never print, upload, or put into a manifest: Douyin Cookie, cloud credentials, or signed media URLs.
- Use the pinned upstream commit only. Never update `master` implicitly and never edit upstream source.
- Never fetch or invent encryption-bypass code. An external `encipher.py` may be installed only through the explicit consent flow in [setup.md](references/setup.md).
- Every automatic archive must use `./抖音下载/[作者]/`. This root is fixed: do not create task, date, `Download`, or additional author-folder layers, and do not substitute another default directory.

## Route the request

1. Preserve the user's exact message as `session-input` for each cloud-drive skill.
2. Infer `mode`, URLs, destination, optional artifacts, account tab/date limits, saved-folder selectors, and live quality using [usage.md](references/usage.md).
3. If `saved-folders` has no explicit name, number, or `all`, ask for the scope before downloading. Ask when authorization or a destructive overwrite choice is genuinely missing.
4. Run `python scripts/douyin_cloud.py doctor --json`. If setup is incomplete, follow [setup.md](references/setup.md). For the standalone bundle, offer its interactive `scripts/onboard.ps1` flow; it keeps Cookie entry in the local terminal and delegates cloud authorisation to the official provider flows.
5. Run the download command with argument arrays, never a shell-built string. Read its JSON result and do not claim success unless `status` is `downloaded` and files are present.
6. Upload the payload using [cloud-upload.md](references/cloud-upload.md). Each drive has its own `{timestamp}-{random6}` session ID, reused throughout the conversation.
7. After verifying every drive result, update the job with `mark-upload`. Run `finalize`; it deletes the local staging directory only when all requested destinations succeeded. On any partial failure, retain it and retry only failed destinations.

## Stable command surface

```text
python scripts/douyin_cloud.py bootstrap
python scripts/douyin_cloud.py configure
python scripts/douyin_cloud.py doctor --json
python scripts/douyin_cloud.py download --mode MODE --url URL ... [options]
python scripts/douyin_cloud.py show-job --job JOB_ID
python scripts/douyin_cloud.py mark-upload --job JOB_ID --drive quark|baidu --status success|failed [--remote-path PATH] [--message TEXT]
python scripts/douyin_cloud.py finalize --job JOB_ID
python scripts/douyin_cloud.py install-encipher --file PATH --i-understand-this-executes-code
```

Do not pass secrets on the command line. `configure` opens the pinned upstream's interactive Cookie/disclaimer flow in the terminal.

## Result handling

- The automatic cloud path is always `./抖音下载/<作者>/`. The `./` denotes the cloud-drive relative root; drive commands use `抖音下载/<作者>/` and must never create a literal dot folder. No task-number or upstream `Download` folder is uploaded.
- The manifest is outside the upload payload. It contains job ID, source requests, relative files, sizes, media categories, and per-drive status only.
- An interrupted live job is marked `interrupted`; preserve its partial file and do not upload it automatically.
- If upstream returns no media, report the explicit failure and recovery hint. Never reinterpret it as success.
- To resume after an upload failure, use `show-job`, upload the existing `payload_path`, mark only the retried destination, then finalize.

See [usage.md](references/usage.md) for intent mapping, [cloud-upload.md](references/cloud-upload.md) for exact handoff rules, and [licensing.md](references/licensing.md) for the upstream pin and attribution.
