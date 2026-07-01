#!/bin/bash

# Function: Scans project directories to find all Terraform layers.
iac_layer_discoverer() {
  log_print "STEP" "Discovering Terraform layers..."
  cd "${SCRIPT_DIR}" || return 1

  # Discover Terraform Layers
  local terraform_layers_str=""
  if [ -d "terraform/layers" ]; then
    terraform_layers_str=$(find "terraform/layers" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | \
      sort | \
      tr '\n' ' ')
  fi
  env_var_mutator "ALL_TERRAFORM_LAYERS" "${terraform_layers_str% }"

  log_print "INFO" "Layer discovery complete."
}

env_file_bootstrapper() {
  local detected_root="$1"
  local env_path="${detected_root}/.env"

  local current_uid=$(id -u)
  local current_gid=$(id -g)
  local current_uname=$(whoami)

  if [[ ! -f "$env_path" ]]; then
    log_print "INFO" "Creating new .env file..."

    cat > "$env_path" <<EOF
# Project Root
PROJECT_ROOT="${detected_root}"

# Discovered Layers
ALL_TERRAFORM_LAYERS=""

# Vault Configuration
DEV_VAULT_ADDR="https://127.0.0.1:8210"
DEV_VAULT_CACERT="\${PROJECT_ROOT}/vault/tls/ca.pem"
VAULT_TOKEN=""

# Container Runtime
HOST_UID=${current_uid}
HOST_GID=${current_gid}
UNAME=${current_uname}
UHOME=\${HOME}
EOF
  else
    # Update critical host info
    env_var_mutator "HOST_UID" "${current_uid}"
    env_var_mutator "HOST_GID" "${current_gid}"
    env_var_mutator "PROJECT_ROOT" "${detected_root}"
  fi

  iac_layer_discoverer
}

# Function to update a specific variable in the .env file (Adds if not exists)
env_var_mutator() {
  local key="$1"
  local value="$2"
  local env_file="${SCRIPT_DIR}/.env"

  local escaped_key
  escaped_key=$(printf '%s' "${key}" | sed 's/[.^$*[\\]/\\&/g')
  local escaped_value
  escaped_value=$(printf '%s' "${value}" | sed 's/[|&\\]/\\&/g')

  if grep -q "^${escaped_key}[[:space:]]*=" "$env_file"; then
    sed -i "s|^\\(${escaped_key}\\s*=\\s*\\).*|\\1\"${escaped_value}\"|" "$env_file"
  else
    echo "${key}=\"${value}\"" >> "$env_file"
  fi
}
