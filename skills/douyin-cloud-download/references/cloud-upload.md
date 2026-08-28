# Cloud upload handoff

The download adapter never owns cloud credentials and never invokes cloud CLIs. Follow the installed `quarkclouddrive` and `baidu-drive` skills in full; this file records the cross-skill contract.

## Shared lifecycle

1. Read `payload_path`, `cloud_root`, `author_folders`, and `requested_destinations` from the job JSON. `cloud_root` is fixed as `抖音下载`; each author folder is a direct child of the payload and maps to `./抖音下载/<作者>/`.
2. Preserve the original user message byte-for-byte as each skill's session input.
3. Generate separate session IDs for Quark and Baidu as `{timestamp}-{random6}`; reuse each drive's ID for every call in the same conversation.
4. Use argument arrays. Never interpolate user text into a shell command string. The `./` in the user-facing layout is not a folder name: pass `抖音下载/<作者>/` to the drive CLIs.
5. Verify returned file count, byte sizes, and destination path. Do not treat a process exit alone as upload success.
6. Call `mark-upload` after each target. Call `finalize` only after all requested targets report success.

## Quark Drive

- Before every Quark CLI call, run that skill's `bash scripts/install.sh` as required by `quarkclouddrive`.
- Never inspect `scripts/quark-drive.cjs`.
- Pass exact `--session-input` and the Quark `--session-id` to every command.
- Idempotently create/find only the base directory `抖音下载`, then create/find each author folder beneath it. Upload that author folder's media files (not the folder itself) to its FID so no additional nesting is created.
- Parse every NDJSON line. Require a successful terminal result and reconcile uploaded file count/size. Preserve resumable state on failure.
- If unauthorized, show the CLI message, perform the skill's one login flow, then retry the original operation once.
- Do not describe FID `0` as “root” unless the user explicitly chose it.

## Baidu Netdisk

- Follow the installed `baidu-drive` skill and use only relative paths under `/apps/bdpan/`.
- Pass `--agentname codex`, exact `--session-input`, and the Baidu `--session-id` to every command.
- Display paths as `我的应用数据/bdpan/<relative path>`.
- Before upload, confirm the local payload exists and list `抖音下载/<作者>/` for same-name media. Create any missing author folder and follow the Baidu Skill's overwrite confirmation rule when a name already exists.
- Upload each media file to `抖音下载/<作者>/<文件名>` with JSON output, then reconcile each author's count and total size.
- Never read token configuration. Use only the Baidu Skill's `scripts/login.sh` authentication flow.

## Resume

Use `python scripts/douyin_cloud.py show-job --job JOB_ID`. Upload only drives whose status is not `success`, then mark those results. A failed or missing drive keeps the local payload. `finalize` is the sole cleanup gate.
