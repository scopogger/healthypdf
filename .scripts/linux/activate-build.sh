#!/bin/bash
# activate-build.sh

# Exit on error, undefined vars, or pipe failures
set -euo pipefail

VENV_DIR=".venv-build"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "Error: '$VENV_DIR' not found. Run setup-build.sh first."
    exit 1
fi

# Activate the build virtual environment
echo "Activating virtual environment: $VENV_DIR"
source "$VENV_DIR/bin/activate"

# A fix to make this script executable:
# chmod +x activate-build.sh
