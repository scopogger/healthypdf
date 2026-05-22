# .master.ps1
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Use the directory where this script lives to resolve paths reliably
$baseDir = $PSScriptRoot

if ($args.Count -eq 0) {
    $scriptsDir = Join-Path $baseDir ".scripts\windows"

    if (Test-Path $scriptsDir) {
        $commands = Get-ChildItem -Path $scriptsDir -Filter "*.ps1" -File |
                    Select-Object -ExpandProperty Name |
                    ForEach-Object { $_ -replace '\.ps1$', '' } |
                    Sort-Object
        $cmdList = $commands -join ', '
    } else {
        $cmdList = "No scripts found in '.scripts/windows/'"
    }

    Write-Host "Usage: .\.master.ps1 <command>"
    Write-Host "Commands: $cmdList" -ForegroundColor Yellow
    Write-Host
    exit 1
}

$command = $args[0]
$restArgs = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }
$scriptPath = Join-Path $baseDir ".scripts\windows\$command.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Host "❌ Error: Script '$scriptPath' not found." -ForegroundColor Red
    exit 1
}

# Run target script with remaining arguments
& $scriptPath @restArgs
