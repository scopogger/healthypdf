# build.ps1

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Activate the build virtual environment
.\.venv-build\Scripts\Activate.ps1

# Install the project and its build tools (non-editable - clean snapshot) - Local repository version
# pip install ".[build]" --index-url http://sng-alfa-sdev-1.sgc.oil.gas:8082/repository/pypi-all/simple --trusted-host sng-alfa-sdev-1.sgc.oil.gas
# or
# pip install ".[build]"

# Install the project and its build tools (non-editable - clean snapshot) - Local directory version
pip install ".[build]" --no-index --find-links=".build_wheels_win"

# Run PyInstaller using the spec file
pyinstaller AltPDF.spec

# Deactivate the environment
deactivate
