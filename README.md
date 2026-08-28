# 抖音网盘下载

[English](README_EN.md)

可安装的 Codex Skill 套件：下载已获授权的抖音媒体，并归档至夸克网盘、百度网盘或两者。

本仓库包含：

- `skills/douyin-cloud-download`：固定版本 DouK-Downloader 的适配器、任务清单、测试与网盘归档规则。
- `skills/baidu-drive`：供适配器调用的完整百度网盘 Skill。
- `vendor/TikTokDownloader`：固定在 `d3806386b392da7341397e18522acdd5283f2c81` 的 DouK-Downloader 源码。
- `scripts/install.ps1`：在干净机器上一键安装两个本地 Skill、固定下载运行时，以及夸克网盘官方 Skill。

安装器会从夸克网盘官方发布端点获取夸克网盘 Skill；不会把其不透明运行时、账号凭据或本机任务记录提交到本仓库。

## 环境要求

- Windows PowerShell 7
- Git、Python 3.12、`uv`、Node.js 16+ 与 Git Bash
- Codex 桌面应用
- 需要访问受限抖音内容时，使用你自己已授权的抖音账号/会话
- 你自己的夸克网盘和/或百度网盘账号

## 安装

克隆本仓库后运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
```

安装器不会复制 Cookie、网盘令牌、历史任务、搜索记录或下载媒体。它会把本仓库中的抖音与百度网盘 Skill 安装到当前 Codex 主目录，将固定的 DouK 运行时从 `vendor/` 安装到状态目录，并获取官方夸克网盘 Skill。

百度 CLI 保持为可见的交互式安装步骤，以便阅读其安全提示。若要在安装时一并安装，显式执行：

```powershell
.\scripts\install.ps1 -InstallBaiduCli
```

随后完成必要的交互式登录：

```powershell
# 仅在此终端中配置抖音免责声明与 Cookie。
uv run --project "$env:USERPROFILE\.codex\state\douyin-cloud-download\upstream\d3806386b392" python "$env:USERPROFILE\.codex\skills\douyin-cloud-download\scripts\douyin_cloud.py" configure

# 百度网盘登录（已安装百度 CLI 后）。
bash "$env:USERPROFILE\.codex\skills\baidu-drive\scripts\login.sh"
```

夸克网盘请直接让 Codex 执行任意夸克操作；若未授权，它会发起官方交互式登录。

## 使用

安装完成后重启 Codex。示例：

- `把这个抖音下载到夸克网盘`
- `批量下载这些抖音到百度和夸克`
- `下载这个抖音合集到夸克网盘`

媒体固定保存到 `./抖音下载/[作者]/`。默认保存视频、图集或实况等核心媒体；需要配乐或封面时请明确说明。

仅下载你拥有或已获授权保存的内容。本套件不支持付费/私密内容绕过，也不会提供反签名绕过代码。

## 验证

```powershell
python -m py_compile .\skills\douyin-cloud-download\scripts\douyin_cloud.py
python .\skills\douyin-cloud-download\tests\test_douyin_cloud.py
```

## 许可证

DouK-Downloader 是其上游 GPL-3.0 源码快照，许可证见 [vendor/TikTokDownloader/license](vendor/TikTokDownloader/license)。其他组件的边界见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
