#!/bin/bash

set -e -u

# Define base directory and load configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPTS_LIB_DIR="${SCRIPT_DIR}/shell"

# Load core utilities first
source "${SCRIPTS_LIB_DIR}/utils.sh"
source "${SCRIPTS_LIB_DIR}/utils_environment.sh"

# Bootstrap .env file and discover layers
env_file_bootstrapper "${SCRIPT_DIR}"

# Source the .env file to export its variables to any sub-processes
if [ -f .env ]; then
  set -o allexport
  source .env
  set +o allexport
fi

# initialize_environment
# Only files following the lib_*.sh naming convention are auto-sourced here.
# Core utilities (utils.sh, utils_environment.sh) are loaded explicitly above.
for lib in "${SCRIPTS_LIB_DIR}"/lib_*.sh; do
	source "$lib"
done

#  Main Menu
echo
echo "======= Vault Management (Local Dev) ======="
echo

vault_status_reporter
echo

PS3=$'\n\033[1;34m[INPUT] Please select an action: \033[0m'
options=()

# [Dev Vault - Bootstrap Unit]
options+=("[DEV] Set up TLS for Dev Vault (Local)")
options+=("[DEV] Initialize Dev Vault (Local)")
options+=("[DEV] Unseal Dev Vault (Local)")
options+=("Quit")

select opt in "${options[@]}"; do
  case $opt in
    # --- Dev Vault ---
    "[DEV] Set up TLS for Dev Vault (Local)")
      vault_dev_tls_generator
      break
      ;;
    "[DEV] Initialize Dev Vault (Local)")
      vault_dev_init_handler
      break
      ;;
    "[DEV] Unseal Dev Vault (Local)")
      vault_dev_unseal_handler
      break
      ;;
    "Quit")
      log_print "INFO" "Exiting script."
      break
      ;;
    *) log_print "ERROR" "Invalid option $REPLY";;
  esac
done
