[CmdletBinding()]
param(
    [string]$CodexHome,
    [switch]$InstallBaiduCli,
    [switch]$Onboard,
    [switch]$QuickStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$setup = Join-Path $PSScriptRoot 'setup.py'

function Resolve-Python312 {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 --version *> $null
        if ($LASTEXITCODE -eq 0) { return @('py', '-3.12') }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $version = & python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
        if ($LASTEXITCODE -eq 0 -and $version -eq '3.12') { return @('python') }
    }
    throw 'Python 3.12 is required. Install Python 3.12 and rerun this script.'
}

$python = Resolve-Python312
$prefixArgs = @()
if ($python.Count -gt 1) { $prefixArgs = $python[1..($python.Count - 1)] }
$argsList = @()
if (-not [string]::IsNullOrWhiteSpace($CodexHome)) { $argsList += @('--codex-home', $CodexHome) }
$argsList += 'install'
if ($InstallBaiduCli) { $argsList += '--install-baidu-cli' }

& $python[0] @prefixArgs $setup @argsList
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Onboard) {
    $onboardArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($CodexHome)) { $onboardArgs += @('--codex-home', $CodexHome) }
    $onboardArgs += @('onboard', '--drive', 'ask')
    if ($QuickStart) { $onboardArgs += '--quick-start' }
    & $python[0] @prefixArgs $setup @onboardArgs
    exit $LASTEXITCODE
}

Write-Host 'Installed. Next: .\scripts\onboard.ps1'
