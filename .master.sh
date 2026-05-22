#!/bin/bash
# .master.sh
set -uo pipefail

# Detect if whether we are being sourced or simply executed
if (return 0 2>/dev/null); then
  _MASTER_SOURCED=1
else
  _MASTER_SOURCED=0
fi

# Resolve script directory reliably
baseDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Enable colors only if stdout is a terminal
if [[ -t 1 ]]; then
    YELLOW='\033[33m'
    RED='\033[31m'
    RESET='\033[0m'
else
    YELLOW=''
    RED=''
    RESET=''
fi

# Show usage if no command is given
if [[ $# -eq 0 ]]; then
    scriptsDir="$baseDir/.scripts/linux"
    cmd_list=""
    if [[ -d "$scriptsDir" ]]; then
        # Use mapfile/readarray for safer pipeline handling with pipefail
        mapfile -t found < <(find "$scriptsDir" -maxdepth 1 -type f -name "*.sh" -exec basename {} \; | sed 's/\.sh$//' | sort)
        cmd_list=$(printf '%s, ' "${found[@]}")
        cmd_list=${cmd_list%, }
    fi

    [[ -z "$cmd_list" ]] && cmd_list="No scripts found in '.scripts/linux/'"

    echo -e "${YELLOW}Usage: ./.master.sh <command>${RESET}"
    echo -e "${YELLOW}Commands: $cmd_list${RESET}"
    echo

    if (( _MASTER_SOURCED )); then return 1; else exit 1; fi
fi

# Safely extract command
COMMAND="$1"
shift 1 || true  # Prevents crash if $# is somehow 0 despite the check above
SCRIPT="$baseDir/.scripts/linux/${COMMAND}.sh"

# Graceful guard for missing scripts
if [[ ! -f "$SCRIPT" ]]; then
    echo -e "${RED}❌ Error: Script '$SCRIPT' not found.${RESET}" >&2
    echo -e "${YELLOW}Run '${0##*/}' without arguments to see available commands.${RESET}" >&2

    if (( _MASTER_SOURCED )); then return 1; else exit 1; fi
fi

# List all activation/env-modding commands here
SOURCE_COMMANDS=("activate-build" "activate-dev")

# Check if the current command is in the list
needs_source=false
for cmd in "${SOURCE_COMMANDS[@]}"; do
  if [[ "$COMMAND" == "$cmd" ]]; then
    needs_source=true
    break
  fi
done

if $needs_source; then
  if (( _MASTER_SOURCED )); then
    source "$SCRIPT"
  else
    echo -e "${RED}Error: '$COMMAND' changes the current shell environment.${RESET}"
    echo -e "${YELLOW}Run it with:${RESET} source ./.master.sh $COMMAND ${YELLOW}or${RESET} . ./.master.sh $COMMAND ${YELLOW}commands.${RESET}"
    exit 1
  fi
else
  if (( _MASTER_SOURCED )); then
    echo -e "${RED}❌ Error: '$COMMAND' does not modify the environment.${RESET}" >&2
    echo -e "${YELLOW}Run it with:${RESET} ./.master.sh $COMMAND" >&2
    return 1
  fi
  # All other commands run safely in a subshell
  bash "$SCRIPT" "$@"
fi
