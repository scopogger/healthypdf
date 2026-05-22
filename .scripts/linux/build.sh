#!/bin/bash
# build.sh

# Exit on error, undefined vars, or pipe failures
set -euo pipefail

VENV_DIR=".venv-build"

# Check if virtual environment exists, create if not
if [[ ! -d "$VENV_DIR" ]]; then
    echo "Virtual environment '$VENV_DIR' not found. Creating..."

    # Try to find python3.13 using the current PATH
    PYTHON_BIN=$(which python3.13 2>/dev/null)

    # If not found, use the presumed absolute path as a fallback
    if [ -z "$PYTHON_BIN" ]; then
        PYTHON_BIN="~/python"
    fi

    # Verify that the binary exists and is executable
    if [ ! -x "$PYTHON_BIN" ]; then
        echo "Error: Python 3.13 not found at $PYTHON_BIN" >&2
        exit 1
    fi

    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "Virtual environment '$VENV_DIR' already exists. Skipping creation."
fi

# Activate the build virtual environment
source .venv-build/bin/activate

# Install the project and its build tools (non-editable - clean snapshot) - Local repository version
# pip install ".[build]" --index-url http://sng-alfa-sdev-1.sgc.oil.gas:8082/repository/pypi-all/simple --trusted-host sng-alfa-sdev-1.sgc.oil.gas
# or
# pip install ".[build]"

# Install the project and its build tools (non-editable - clean snapshot) - Local directory version
pip install --no-index --find-links=".build_wheels_linux" ".[build]"

# Run PyInstaller using the spec file
pyinstaller AltPDF.spec

# Deactivate the environment
deactivate

# A fix to make this script executable:
# chmod +x build.sh
