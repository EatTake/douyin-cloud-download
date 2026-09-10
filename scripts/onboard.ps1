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
$argsList += @('onboard', '--drive', $Drive)
if ($DryRun) { $argsList += '--dry-run' }
if ($QuickStart) { $argsList += '--quick-start' }

& $python[0] @prefixArgs $setup @argsList
exit $LASTEXITCODE
