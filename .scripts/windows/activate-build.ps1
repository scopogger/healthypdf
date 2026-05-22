# activate-build.ps1

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$VENV_DIR = ".venv-build"

if (-not (Test-Path -PathType Container $VENV_DIR)) {
    Write-Error "Error: '$VENV_DIR' not found. Run setup-build.ps1 first."
    exit 1
}

Write-Host "Activating virtual environment: $VENV_DIR" -ForegroundColor Green
& "$VENV_DIR\Scripts\Activate.ps1"
