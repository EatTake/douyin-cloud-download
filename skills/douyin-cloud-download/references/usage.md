# Intent and option mapping

## Modes

| User intent | `--mode` | Required scope |
|---|---|---|
| One or many video/note/share links | `works` or `auto` | one or more `--url` |
| Account posts/favorites/collections | `account` | account `--url`; optional `--account-tab`, dates, pages |
| Collection/series/mix | `mix` | one or more collection `--url` |
| Current account's saved works | `saved-works` | owner account `--url` |
| Current account's saved folders | `saved-folders` | one or more `--selector`; must be explicit |
| Current account's saved music | `saved-music` | no URL required |
| Live recording | `live` | one or more live `--url` |

`auto` classifies full Douyin URLs and groups mixed batches. Short share links are treated as works unless the user's wording clearly identifies account, mix, or live intent; in that case pass the explicit mode.

## Defaults

- Destination: `--destination quark`.
- Archive path: always `./抖音下载/<作者>/`; it is not configurable per download.
- Core media: video, images, or live-photo components.
- Optional artifacts: repeat `--artifact music`, `--artifact static-cover`, or `--artifact dynamic-cover` only when explicitly requested.
- Account tab: `post`. Other values: `favorite`, `collection`.
- Date bounds: `--earliest YYYY-MM-DD`, `--latest YYYY-MM-DD`.
- Saved folders: selectors accept a 1-based number, exact folder name, or `all`. If absent, ask before execution.
- Live: `--live-quality 1`, upstream's highest quality index. A quality name is also accepted.
- Local cleanup: automatic after every requested drive succeeds. Use `--keep-local` only when the user requests it.

## Examples

```text
python scripts/douyin_cloud.py download --mode works --url "https://www.douyin.com/video/..." --destination quark
python scripts/douyin_cloud.py download --mode auto --url "..." --url "..." --destination both --artifact music
python scripts/douyin_cloud.py download --mode account --url "https://www.douyin.com/user/..." --account-tab post --earliest 2026-07-01 --destination quark
python scripts/douyin_cloud.py download --mode saved-folders --selector all --destination baidu
python scripts/douyin_cloud.py download --mode live --url "https://live.douyin.com/..." --live-quality 1 --destination baidu
```

The script emits one JSON object on its final stdout line. Treat nonzero exit status as failure even if upstream printed progress before it.
