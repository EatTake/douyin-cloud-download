[CmdletBinding()]
param(
    [string]$CodexHome,
    [switch]$InstallBaiduCli,
    [switch]$Onboard,
    [switch]$QuickStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$pinnedCommit = 'd3806386b392da7341397e18522acdd5283f2c81'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if ([string]::IsNullOrWhiteSpace($CodexHome)) {
    $CodexHome = if ([string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex'
    } else {
        $env:CODEX_HOME
    }
}
$CodexHome = [IO.Path]::GetFullPath($CodexHome)
$skillsRoot = Join-Path $CodexHome 'skills'
$stateRoot = Join-Path $CodexHome 'state\douyin-cloud-download'

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Copy-NewDirectory {
    param(
        [Parameter(Mandatory)] [string]$Source,
        [Parameter(Mandatory)] [string]$Destination
    )
    if (Test-Path -LiteralPath $Destination) {
        throw "Refusing to overwrite existing path: $Destination"
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -Path (Join-Path $Source '*') -Destination $Destination -Recurse -Force
}

function Get-Property {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Install-OfficialQuarkSkill {
    param([string]$Destination)
    if (Test-Path -LiteralPath $Destination) {
        Write-Host "Quark Drive Skill already exists: $Destination"
        return
    }

    $requestId = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $config = Invoke-RestMethod -Uri "https://open-api-drive.quark.cn/agent/v1/skill_config?req_id=$requestId"
    $candidates = @(
        (Get-Property (Get-Property $config 'data') 'config'),
        (Get-Property $config 'config'),
        (Get-Property $config 'data'),
        $config
    )
    $zipUrl = $null
    foreach ($candidate in $candidates) {
        $candidateUrl = [string](Get-Property $candidate 'qkPan')
        if ($candidateUrl -match '^https?://\S+$') {
            $zipUrl = $candidateUrl
            break
        }
    }
    if ([string]::IsNullOrWhiteSpace($zipUrl)) {
        throw 'Quark Drive did not return a valid published Skill package URL.'
    }

    $temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("douyin-cloud-download-quark-" + [guid]::NewGuid())
    $downloadRoot = Join-Path $temporaryRoot 'download'
    $extractRoot = Join-Path $temporaryRoot 'extract'
    $archive = Join-Path $downloadRoot 'skill.zip'
    try {
        New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
        New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
        Invoke-WebRequest -Uri $zipUrl -OutFile $archive
        Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot -Force
        $skillFile = Get-ChildItem -Path $extractRoot -Recurse -File -Filter 'SKILL.md' |
            Select-Object -First 1
        if ($null -eq $skillFile) {
            throw 'The published Quark archive does not contain SKILL.md.'
        }
        $source = $skillFile.Directory.FullName
        if (-not (Test-Path -LiteralPath (Join-Path $source 'scripts\install.sh'))) {
            throw 'The published Quark archive does not contain its installer.'
        }
        Copy-NewDirectory -Source $source -Destination $Destination
    } finally {
        if (Test-Path -LiteralPath $temporaryRoot) {
            Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
        }
    }
    Push-Location $Destination
    try {
        & bash './scripts/install.sh'
        if ($LASTEXITCODE -ne 0) {
            throw 'The official Quark Drive Skill installer failed.'
        }
    } finally {
        Pop-Location
    }
}

Require-Command uv
Require-Command bash
New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null

Copy-NewDirectory -Source (Join-Path $repoRoot 'skills\douyin-cloud-download') -Destination (Join-Path $skillsRoot 'douyin-cloud-download')
Copy-NewDirectory -Source (Join-Path $repoRoot 'skills\baidu-drive') -Destination (Join-Path $skillsRoot 'baidu-drive')

$runtime = Join-Path $stateRoot ('upstream\' + $pinnedCommit.Substring(0, 12))
Copy-NewDirectory -Source (Join-Path $repoRoot 'vendor\TikTokDownloader') -Destination $runtime
Set-Content -LiteralPath (Join-Path $runtime '.douyin-cloud-download-upstream-commit') -Value $pinnedCommit -NoNewline -Encoding utf8

Push-Location $runtime
try {
    & uv sync --locked --python 3.12 --no-dev
    if ($LASTEXITCODE -ne 0) {
        throw 'The pinned DouK runtime dependency installation failed.'
    }
} finally {
    Pop-Location
}

Install-OfficialQuarkSkill -Destination (Join-Path $skillsRoot 'quarkclouddrive')

if ($InstallBaiduCli) {
    Push-Location (Join-Path $skillsRoot 'baidu-drive')
    try {
        & bash './scripts/install.sh'
        if ($LASTEXITCODE -ne 0) {
            throw 'The Baidu Netdisk CLI installer failed.'
        }
    } finally {
        Pop-Location
    }
}

Write-Host "Installed Skills under $skillsRoot"
if ($Onboard) {
    & (Join-Path $PSScriptRoot 'onboard.ps1') -CodexHome $CodexHome -QuickStart:$QuickStart
    exit $LASTEXITCODE
}
Write-Host 'Next: run .\scripts\onboard.ps1 to configure Douyin Cookie and cloud-drive authorisation interactively.'
