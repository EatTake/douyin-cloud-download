# Setup and recovery

## First use

1. Run `python scripts/douyin_cloud.py bootstrap`.
2. Run `python scripts/douyin_cloud.py configure` in an interactive terminal.
3. Let the user read and accept DouK-Downloader's disclaimer, then paste their Douyin Cookie directly into that terminal. Never ask them to paste it into chat.
4. Run `python scripts/douyin_cloud.py doctor --json` and require `ready: true` before downloading.

The runtime lives under `%CODEX_HOME%/state/douyin-cloud-download` (or `%USERPROFILE%/.codex/state/douyin-cloud-download`). `bootstrap` clones the exact commit `d3806386b392da7341397e18522acdd5283f2c81`, verifies `HEAD`, and installs its locked dependencies with uv and Python 3.12. The standalone bundle installer may instead copy its verbatim vendored snapshot and writes the same pinned revision to a local runtime marker; the adapter verifies that marker before use. Neither path follows `master`.

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
- `disclaimer_not_accepted`: rerun `configure` and accept only after reading.
- `douyin_cookie_missing`: rerun `configure` and enter the Cookie in the terminal.
- `ffmpeg_missing`: install ffmpeg and ensure it is on `PATH`; required for live recording.
- `no_media_downloaded`: Cookie, link access, or upstream encryption may have expired. Reconfigure Cookie first. Do not claim success.
- Authentication failures for a cloud drive are handled by that drive's existing Skill, not by this script.
