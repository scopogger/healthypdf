#!/bin/bash
# setup-dev.sh

# Exit on error, undefined vars, or pipe failures
set -euo pipefail

VENV_DIR=".venv-dev"

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

# Activate the dev virtual environment
source "$VENV_DIR/bin/activate"

# Install the project and its dev tools - Local repository version
# pip install -e . --index-url http://sng-alfa-sdev-1.sgc.oil.gas:8082/repository/pypi-all/simple --trusted-host sng-alfa-sdev-1.sgc.oil.gas
# or
# pip install -e .

# Install the project and its dev tools - Local directory version
pip install -e . --no-index --find-links=".build_wheels_linux"

# Deactivate the environment
deactivate

# A fix to make this script executable:
# chmod +x setup-dev.sh
