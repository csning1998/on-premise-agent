#!/bin/bash

### This script contains general utility and helper functions.

# Prevent multiple loading
if [[ -n "${UTILS_SH_LOADED:-}" ]]; then
	# Prevent multiple loading in subshell (e.g. CI/CD pipeline, polluted env)
  (return 0 2>/dev/null) && return 0 || exit 0
fi
readonly UTILS_SH_LOADED=true

# ANSI Color Codes
readonly CLR_RESET='\033[0m'
readonly CLR_RED='\033[0;31m'
readonly CLR_GREEN='\033[0;32m'
readonly CLR_YELLOW='\033[0;33m'
readonly CLR_CYAN='\033[0;36m'
readonly CLR_PURPLE='\033[0;35m'
readonly CLR_BOLD_RED='\033[1;31m'
readonly CLR_BOLD_BLUE='\033[1;34m'

# Function: Unified Logging Interface
log_print() {
  local level="${1:-INFO}"
  local msg="${2:-}"

  case "${level^^}" in
    "STEP")    echo -e "${CLR_BOLD_BLUE}[STEP] ${msg}${CLR_RESET}" ;;
    "INFO")    echo -e "${CLR_GREEN}[INFO] ${msg}${CLR_RESET}" ;;
    "TASK")    echo -e "${CLR_CYAN}[TASK] ${msg}${CLR_RESET}" ;;
    "WARN")    echo -e "${CLR_YELLOW}[WARN] ${msg}${CLR_RESET}" ;;
    "ERROR")   echo -e "${CLR_RED}[ERROR] ${msg}${CLR_RESET}" >&2 ;;
    "FATAL")   echo -e "${CLR_BOLD_RED}[FATAL] ${msg}${CLR_RESET}" >&2 ;;
    "OK"|"SUCCESS") echo -e "${CLR_GREEN}[OK] ${msg}${CLR_RESET}" ;;
    "INPUT")   echo -e "${CLR_PURPLE}[INPUT] ${msg}${CLR_RESET}" ;;
    *)         echo -e "${CLR_RESET}[LOG] ${msg}${CLR_RESET}" ;;
  esac
}

# Function: Print a visual divider
log_divider() {
  local char="${1:--}"
  local length="${2:-60}"
  local color="${3:-${CLR_RESET}}"

  local line
  # Generate a line of 'length' spaces, then replace spaces with 'char'
  printf -v line "%*s" "$length" ""
  echo -e "${color}${line// /$char}${CLR_RESET}"
}

# Function: Execute a command string directly on the host.
run_command() {
  local cmd_string="$1"
	local host_work_dir="${2:-${SCRIPT_DIR}}" # Optional working directory

  # Native Mode: Execute the command directly on the host.
  (cd "${host_work_dir}" && bash -c "${cmd_string}")
}
