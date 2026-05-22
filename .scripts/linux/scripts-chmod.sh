#!/bin/bash
# scripts-chmod.sh
set -euo pipefail

# Resolve the absolute path of the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for script in "$SCRIPT_DIR"/*.sh; do
    # Skip if no .sh files exist in the directory
    [ -f "$script" ] || continue
    chmod +x "$script"
done

# Make .master.sh (2 directories up) executable if it exists
MASTER_SCRIPT="$SCRIPT_DIR/../../.master.sh"
if [[ -f "$MASTER_SCRIPT" ]]; then
    chmod +x "$MASTER_SCRIPT"
fi

# A fix to make this script executable:
# chmod +x scripts-chmod.sh
