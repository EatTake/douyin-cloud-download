[CmdletBinding()]
param(
    [ValidateSet('ask', 'quark', 'baidu', 'both', 'skip')]
    [string]$Drive = 'ask',
    [string]$CodexHome,
    [switch]$DryRun,
    [switch]$QuickStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($CodexHome)) {
    $CodexHome = if ([string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex'
    } else {
        $env:CODEX_HOME
    }
}
$CodexHome = [IO.Path]::GetFullPath($CodexHome)
$skillsRoot = Join-Path $CodexHome 'skills'
$runtime = Join-Path $CodexHome 'state\douyin-cloud-download\upstream\d3806386b392'
$adapter = Join-Path $skillsRoot 'douyin-cloud-download\scripts\douyin_cloud.py'

function Require-Path {
    param([string]$Path, [string]$Description)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Description is missing. Run .\scripts\install.ps1 from the cloned repository first."
    }
}

function Confirm-Step {
    param([string]$Prompt)
    if ($DryRun) { return $false }
    if ($QuickStart) { return $true }
    $answer = Read-Host "$Prompt [Y/n]"
    return [string]::IsNullOrWhiteSpace($answer) -or $answer -match '^(?i:y|yes)$'
}

function Select-Drive {
    if ($Drive -ne 'ask') { return $Drive }
    if ($QuickStart) { return 'quark' }
    Write-Host ''
    Write-Host '选择首次要授权的网盘：'
    Write-Host '  1. 夸克网盘（默认）'
    Write-Host '  2. 百度网盘'
    Write-Host '  3. 两个网盘'
    Write-Host '  4. 暂不配置网盘'
    switch (Read-Host '输入 1-4') {
        '2' { return 'baidu' }
        '3' { return 'both' }
        '4' { return 'skip' }
        default { return 'quark' }
    }
}

function Invoke-DouyinSetup {
    Write-Host ''
    Write-Host '步骤 1/3：配置抖音 Cookie'
    Write-Host 'Cookie 是登录凭据。不要发送到聊天、截图、日志或 Git 仓库。'
    Write-Host '获取方式：在已登录的 douyin.com 浏览器按 F12 → 网络 → 勾选“保留日志” → 筛选 cookie-name:odin_tt → 打开任意作品评论区 → 从一个请求中复制完整 Cookie 值。'
    Write-Host '接下来会打开 DouK-Downloader 的本地配置终端；仅在该终端中粘贴 Cookie。'
    if (-not (Confirm-Step '现在开始配置抖音 Cookie？')) {
        Write-Host '已跳过 Cookie 配置。之后可重新运行此向导。'
        return $false
    }
    if ($DryRun) { return $false }

    & uv run --project $runtime python $adapter configure
    if ($LASTEXITCODE -ne 0) {
        Write-Warning '抖音配置尚未完成。请检查免责声明是否已确认、Cookie 是否完整，然后重新运行本向导。'
        return $false
    }

    $doctorOutput = @(& uv run --project $runtime python $adapter doctor --json)
    if ($LASTEXITCODE -ne 0 -or $doctorOutput.Count -eq 0) {
        Write-Warning '无法确认抖音配置状态；请重新运行本向导。'
        return $false
    }
    try {
        $doctor = $doctorOutput[-1] | ConvertFrom-Json
    } catch {
        Write-Warning '无法读取抖音配置状态；请重新运行本向导。'
        return $false
    }
    if ($doctor.ready) {
        Write-Host '抖音配置完成。'
        return $true
    }
    Write-Warning '抖音配置尚未就绪；请重新运行此向导完成 Cookie 与免责声明步骤。'
    return $false
}

function Invoke-QuarkSetup {
    $quarkRoot = Join-Path $skillsRoot 'quarkclouddrive'
    Require-Path (Join-Path $quarkRoot 'scripts\install.sh') '夸克网盘 Skill'
    Write-Host ''
    Write-Host '步骤 2/3：授权夸克网盘'
    Write-Host '将打开浏览器完成夸克官方授权。请仅在夸克官方页面确认授权范围。'
    if (-not (Confirm-Step '现在授权夸克网盘？')) {
        Write-Host '已跳过夸克授权。之后可重新运行此向导。'
        return $false
    }
    if ($DryRun) { return $false }

    Push-Location $quarkRoot
    try {
        & bash './scripts/install.sh'
        if ($LASTEXITCODE -ne 0) {
            Write-Warning '夸克网盘 Skill 环境检查失败。'
            return $false
        }
        & node './scripts/quark-drive.cjs' login
        if ($LASTEXITCODE -eq 0) {
            Write-Host '夸克网盘授权完成。'
            return $true
        }
    } finally {
        Pop-Location
    }

    Write-Warning '浏览器授权未完成或已超时。请重新运行本向导；若官方页面提供授权码，按页面提示将授权码粘贴回本终端继续。'
    return $false
}

function Invoke-BaiduSetup {
    $baiduRoot = Join-Path $skillsRoot 'baidu-drive'
    Require-Path (Join-Path $baiduRoot 'scripts\login.sh') '百度网盘 Skill'
    Write-Host ''
    Write-Host '步骤 3/3：授权百度网盘'
    Write-Host '百度网盘会显示自己的安全提示与授权页面。请阅读提示，并只在官方页面完成授权。'
    if (-not (Confirm-Step '现在授权百度网盘？')) {
        Write-Host '已跳过百度授权。之后可重新运行此向导。'
        return $false
    }
    if ($DryRun) { return $false }

    Push-Location $baiduRoot
    try {
        if (-not (Get-Command bdpan -ErrorAction SilentlyContinue)) {
            & bash './scripts/install.sh'
            if ($LASTEXITCODE -ne 0) {
                Write-Warning '百度网盘 CLI 安装未完成。'
                return $false
            }
        }
        & bash './scripts/login.sh'
        if ($LASTEXITCODE -ne 0) {
            Write-Warning '百度网盘授权未完成。'
            return $false
        }
        & bdpan whoami
        if ($LASTEXITCODE -ne 0) {
            Write-Warning '无法确认百度网盘登录状态。'
            return $false
        }
        Write-Host '百度网盘授权完成。'
        return $true
    } finally {
        Pop-Location
    }
}

Require-Path $runtime '固定的 DouK-Downloader 运行时'
Require-Path $adapter '抖音下载 Skill'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Required command not found: uv' }
if (-not (Get-Command bash -ErrorAction SilentlyContinue)) { throw 'Required command not found: bash' }

if ($DryRun) {
    Write-Host '演练模式：不会打开浏览器、写入 Cookie 或发起网盘授权。'
}
if ($QuickStart) {
    Write-Host '快捷模式：将直接开始本地配置与官方授权页面；平台页面中的确认仍需由你本人完成。'
}

$selectedDrive = Select-Drive
$douyinReady = Invoke-DouyinSetup
$quarkReady = $false
$baiduReady = $false
if ($selectedDrive -in @('quark', 'both')) { $quarkReady = Invoke-QuarkSetup }
if ($selectedDrive -in @('baidu', 'both')) { $baiduReady = Invoke-BaiduSetup }

Write-Host ''
Write-Host '配置结果：'
Write-Host ("  抖音：" + $(if ($douyinReady) { '已完成' } else { '待完成' }))
if ($selectedDrive -in @('quark', 'both')) { Write-Host ("  夸克网盘：" + $(if ($quarkReady) { '已完成' } else { '待完成' })) }
if ($selectedDrive -in @('baidu', 'both')) { Write-Host ("  百度网盘：" + $(if ($baiduReady) { '已完成' } else { '待完成' })) }
if ($selectedDrive -eq 'skip') { Write-Host '  网盘：暂未配置' }

if ($douyinReady -and ($quarkReady -or $baiduReady)) {
    Write-Host '可以开始使用：把一个已授权访问的抖音链接下载到已授权网盘。'
    exit 0
}
Write-Host '尚有配置未完成；重新运行 .\scripts\onboard.ps1 即可从缺失步骤继续。'
exit 2
