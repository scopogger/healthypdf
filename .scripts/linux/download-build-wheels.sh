#!/bin/bash
# download-build-wheels.sh
# Run from HashKit project root (where pyproject.toml lives)

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

WHEEL_DIR=".build_wheels_linux"

# Remove old directory if it exists (fresh start)
if [ -d "$WHEEL_DIR" ]; then
    rm -rf "$WHEEL_DIR"
fi

# Download all wheels
pip download ".[build]" -d $WHEEL_DIR --index-url http://sng-alfa-sdev-1.sgc.oil.gas:8082/repository/pypi-all/simple --trusted-host sng-alfa-sdev-1.sgc.oil.gas

echo "Done! All wheels are now in '$WHEEL_DIR' folder!"

# Deactivate the environment
deactivate

# A fix to make this script executable:
# chmod +x download-build-wheels.sh
