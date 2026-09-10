# Third-party notices

## DouK-Downloader / TikTokDownloader

The source in `vendor/TikTokDownloader` is a verbatim snapshot of [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader) at commit `df8aced70e476ae3330fa913186f3207b4843201`. It is distributed under GPL-3.0; its complete licence text is retained in `vendor/TikTokDownloader/license`.

## Quark Drive Skill

This repository does not redistribute Quark Drive's opaque CLI runtime, credentials, or local task state. The shared installer used by `scripts/install.ps1` and `scripts/install.sh` retrieves the fixed official Skill version `1.0.19` from Quark Drive's official configuration endpoint, validates the package, and records its SHA256 receipt.

## Baidu Netdisk

The bundled Baidu Skill is synchronized to official Skill `v1.7.5`. Its installer installs the `bdpan` executable from Baidu's official CDN and requires the user to complete the provider's interactive safety and login flow. Do not commit generated configuration or access tokens.
