# download-build-wheels.ps1
# Run from HashKit project root (where pyproject.toml lives)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Activate the build virtual environment
.\.venv-build\Scripts\Activate.ps1

$WHEELDIR = ".build_wheels_win"

# Remove old directory if it exists (fresh start)
if (Test-Path $WHEELDIR) {
    Remove-Item -Recurse -Force $WHEELDIR
}

# Download all wheels
pip download ".[build]" -d $WHEELDIR --index-url http://sng-alfa-sdev-1.sgc.oil.gas:8082/repository/pypi-all/simple --trusted-host sng-alfa-sdev-1.sgc.oil.gas

Write-Host "Done! All wheels are now in '$WHEELDIR' folder!"

# Deactivate the environment
deactivate
