# Third-party notices

## DouK-Downloader / TikTokDownloader

The source in `vendor/TikTokDownloader` is a verbatim snapshot of [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader) at commit `d3806386b392da7341397e18522acdd5283f2c81`. It is distributed under GPL-3.0; its complete licence text is retained in `vendor/TikTokDownloader/license`.

## Quark Drive Skill

This repository does not redistribute Quark Drive's opaque CLI runtime, credentials, or local task state. `scripts/install.ps1` retrieves the current published Skill package from Quark Drive's official Skill configuration endpoint at installation time.

## Baidu Netdisk

The bundled Baidu Skill installs its `bdpan` executable from Baidu's official CDN and requires the user to complete the provider's interactive safety and login flow. Do not commit its generated configuration or access tokens.
