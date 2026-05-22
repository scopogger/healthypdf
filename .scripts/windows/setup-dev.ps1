# setup-dev.ps1

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$VENV_DIR = ".venv-dev"

# Check if virtual environment exists, create if not
if (-not (Test-Path -Path $VENV_DIR)) {
    Write-Host "Virtual environment '$VENV_DIR' not found. Creating..."
    python -m venv $VENV_DIR
} else {
    Write-Host "Virtual environment '$VENV_DIR' already exists. Skipping creation."
}

# Activate the dev virtual environment
& ".\$VENV_DIR\Scripts\Activate.ps1"

# Install the project and its dev tools - Local repository version
# pip install -e . --index-url http://sng-alfa-sdev-1.sgc.oil.gas:8082/repository/pypi-all/simple --trusted-host sng-alfa-sdev-1.sgc.oil.gas
# or
# pip install -e .

# Install the project and its dev tools - Local directory version
pip install -e . --no-index --find-links=".build_wheels_win"

# Deactivate the environment
deactivate
