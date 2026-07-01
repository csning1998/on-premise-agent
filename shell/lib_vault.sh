#!/bin/bash

# Prevent multiple loading
if [[ -n "${VAULT_SH_LOADED:-}" ]]; then
  (return 0 2>/dev/null) && return 0 || exit 0
fi
readonly VAULT_SH_LOADED=true

# Development Vault Variables
readonly DEV_VAULT_ADDR="https://127.0.0.1:8210"
readonly DEV_CA="/opt/vault/tls/ca.pem"
readonly DEV_KEYS_DIR="${SCRIPT_DIR}/vault/keys"
readonly DEV_TLS_DIR="${SCRIPT_DIR}/vault/tls"
readonly DEV_INIT_FILE="${DEV_KEYS_DIR}/init-output.json"
readonly DEV_UNSEAL_KEY_FILE="${DEV_KEYS_DIR}/unseal.key"
readonly DEV_ROOT_TOKEN_FILE="$HOME/.vault-token"

# Status Reporting
vault_status_reporter() {
  # Auto-sync token whenever status is reported
  vault_token_sync_handler > /dev/null 2>&1 || true

  log_divider

  if podman exec -i vault-server vault status -address="${DEV_VAULT_ADDR}" -ca-cert="${DEV_CA}" -format=json > /dev/null 2>&1; then
    local status_json
    status_json=$(podman exec -i vault-server vault status -address="${DEV_VAULT_ADDR}" -ca-cert="${DEV_CA}" -format=json)
    local sealed
    sealed=$(echo "$status_json" | jq .sealed 2>/dev/null)
    if [[ "$sealed" == "true" ]]; then
      log_print "WARN" "Development Vault: Running (Sealed)"
    else
      log_print "OK" "Development Vault: Running (Unsealed)"
    fi
  else
    if podman ps --filter "name=vault-server" --filter "status=running" | grep -q "vault-server"; then
      log_print "WARN" "Development Vault: Running (Not Initialized)"
    else
      log_print "ERROR" "Development Vault: Stopped"
    fi
  fi

  log_divider
}

# Function: Generate TLS Certs for Development Vault (Host)
vault_dev_tls_generator() {

  log_print "STEP" "[Development Vault] Generating CA Root files for TLS..."
  log_print "WARN" "#############################################################################"
  log_print "WARN" "### Proceeding will DESTROY ALL existing files in vault/tls.              ###"
  log_print "WARN" "#############################################################################"

  log_print "INPUT" "Type 'yes' to confirm: "
  read -r confirmation

  if [[ "$confirmation" != "yes" ]]; then
    log_print "INFO" "Cancelled."
    return 1
  fi

  rm -rf "${DEV_TLS_DIR}"
  mkdir -p "${DEV_TLS_DIR}"

  # Generate CA and Certs (Using host openssl)
  run_command "openssl genrsa -out vault/tls/ca-key.pem 2048" || return 1
  run_command "openssl req -new -x509 -days 365 -key vault/tls/ca-key.pem -sha256 -out vault/tls/ca.pem -subj '/CN=DevVaultCA'" || return 1

  run_command "openssl genrsa -out vault/tls/vault-key.pem 2048" || return 1
  run_command "openssl req -subj '/CN=localhost' -sha256 -new -key vault/tls/vault-key.pem -out vault/tls/vault.csr" || return 1

  echo "subjectAltName = DNS:localhost,IP:127.0.0.1" > "${DEV_TLS_DIR}/extfile.cnf"

	run_command "openssl x509 -req -days 365 -sha256 -in vault/tls/vault.csr \
    -CA vault/tls/ca.pem -CAkey vault/tls/ca-key.pem \
    -CAcreateserial -out vault/tls/vault.pem \
    -extfile vault/tls/extfile.cnf" || return 1

  rm -f "${DEV_TLS_DIR}/vault.csr" "${DEV_TLS_DIR}/extfile.cnf"
  chmod 600 "${DEV_TLS_DIR}/"*key.pem
  chmod 644 "${DEV_TLS_DIR}/"*.pem

  log_print "OK" "Dev Vault TLS Certificates generated."
}

# Function: Sync VAULT_TOKEN to .env from JSON or fallback file
vault_token_sync_handler() {
  local token=""

  if [ -f "$DEV_INIT_FILE" ]; then
    log_print "TASK" "Syncing VAULT_TOKEN from $DEV_INIT_FILE..."
    token=$(jq -r '.root_token' "$DEV_INIT_FILE")
  elif [ -f "$DEV_ROOT_TOKEN_FILE" ]; then
    log_print "TASK" "Syncing VAULT_TOKEN from $DEV_ROOT_TOKEN_FILE..."
    token=$(cat "$DEV_ROOT_TOKEN_FILE")
  else
    log_print "WARN" "No Vault token files found. Skipping sync."
    return 0
  fi

  if [[ -n "$token" && "$token" != "null" ]]; then
    env_var_mutator "VAULT_TOKEN" "${token}"
    # Also set for current session
    export VAULT_TOKEN="${token}"
    # Ensure User Home fallback is also updated (atomic write to avoid a
    # world-readable window between the write and the chmod)
    local tmp_token
    tmp_token=$(mktemp "${DEV_ROOT_TOKEN_FILE}.XXXXXX")
    chmod 600 "$tmp_token"
    echo "$token" > "$tmp_token"
    mv "$tmp_token" "$DEV_ROOT_TOKEN_FILE"
  else
    log_print "ERROR" "Failed to extract a valid token."
    return 1
  fi
}

# Function: Ensure KV Engine is enabled (Dev Vault)
vault_dev_engine_enforcer() {
  log_print "TASK" "[Development Vault] Ensuring KV secrets engine is enabled at 'secret/'..."

  if [ ! -f "$DEV_ROOT_TOKEN_FILE" ]; then
    log_print "ERROR" "Root token not found. Cannot configure engine."
    return 1
  fi

  local root_token
  root_token=$(cat "$DEV_ROOT_TOKEN_FILE")

  if ! podman exec -i -e VAULT_TOKEN="${root_token}" vault-server vault secrets list -address="${DEV_VAULT_ADDR}" -ca-cert="${DEV_CA}" -format=json | jq -e '."secret/"' > /dev/null; then
    log_print "TASK" "'secret/' path not found, enabling kv-v2..."
    podman exec -i -e VAULT_TOKEN="${root_token}" vault-server vault secrets enable -address="${DEV_VAULT_ADDR}" -ca-cert="${DEV_CA}" -path=secret kv-v2
  else
    log_print "INFO" "kv-v2 secrets engine is already enabled."
  fi
}

# Function: Initialize, Unseal, Login, and Configure Dev Vault
vault_dev_init_handler() {
  log_print "STEP" "[Dev Vault] Initializing Local Podman Vault..."

  if [[ -f "$DEV_INIT_FILE" ]]; then
		log_print "WARN" "Init file exists. Skipping to prevent data loss."
		return 1
  fi

  mkdir -p "$DEV_KEYS_DIR"

  log_print "TASK" "Initializing..."
  local tmp_init
  tmp_init=$(mktemp "${DEV_INIT_FILE}.XXXXXX")
	if ! podman exec -i vault-server vault operator init -address="${DEV_VAULT_ADDR}" -ca-cert="${DEV_CA}" -format=json > "$tmp_init"; then
    rm -f "$tmp_init"
    log_print "FATAL" "Initialization failed. Is vault-server running?"
    return 1
  fi
  mv "$tmp_init" "$DEV_INIT_FILE"

  # Extract Keys
  if ! jq -r '.unseal_keys_b64[]' "$DEV_INIT_FILE" > "$DEV_UNSEAL_KEY_FILE"; then
    log_print "FATAL" "Failed to extract unseal keys from $DEV_INIT_FILE"
    return 1
  fi
  if [[ ! -s "$DEV_UNSEAL_KEY_FILE" ]]; then
    log_print "FATAL" "Unseal key file is empty"
    return 1
  fi
  chmod 600 "$DEV_KEYS_DIR"/*

  log_print "INFO" "Keys saved to ${DEV_KEYS_DIR}"

  # Sync Root Token to .env and $HOME/.vault-token (single source of truth)
  vault_token_sync_handler

  # Auto Unseal
  if ! vault_dev_unseal_handler; then
    log_print "ERROR" "Auto-unseal failed. Please unseal manually before configuring engine."
    return 1
  fi

  # Auto Configure Engine
  # KV v2 mount at secret/ is now owned by terraform/layers/20-security-vault-approle
  # vault_dev_engine_enforcer

  log_print "OK" "Dev Vault is ready for use."
}

# Function: Unseal Dev Vault
vault_dev_unseal_handler() {
  log_print "STEP" "[Dev Vault] Unsealing..."

  if [ ! -f "$DEV_UNSEAL_KEY_FILE" ]; then
    log_print "ERROR" "Unseal keys not found. Run '[DEV] Initialize' first."
    return 1
  fi

  local status_json
  status_json=$(podman exec -i vault-server vault status -address="${DEV_VAULT_ADDR}" -ca-cert="${DEV_CA}" -format=json 2>/dev/null || true)
  if [[ $(echo "$status_json" | jq .sealed 2>/dev/null) == "false" ]]; then
    log_print "INFO" "Development Vault is already unsealed."
    return 0
  fi

  while IFS= read -r key; do
    [[ -z "$key" ]] && continue
    # Strip carriage returns and pass key as a positional argument, not stdin
    clean_key=$(printf "%s" "$key" | tr -d '\r')
    podman exec vault-server vault operator unseal -address="${DEV_VAULT_ADDR}" -ca-cert="${DEV_CA}" "${clean_key}" || return 1
  done < "$DEV_UNSEAL_KEY_FILE"

  # Wait for Unseal to propagate
  local timeout=10
  local count=0
  while [ $count -lt $timeout ]; do
    status_json=$(podman exec -i vault-server vault status -address="${DEV_VAULT_ADDR}" -ca-cert="${DEV_CA}" -format=json 2>/dev/null || true)
    if [[ $(echo "$status_json" | jq .sealed 2>/dev/null) == "false" ]]; then
      log_print "OK" "Dev Vault Unsealed and ready."

      # Export and Sync
      if [ -f "$DEV_ROOT_TOKEN_FILE" ]; then
        vault_token_sync_handler
        log_print "INFO" "Vault environment variables set for this session."
      fi
      return 0
    fi
    sleep 0.5
    ((count++))
  done

  log_print "ERROR" "Vault sent unseal keys but is still reporting as SEALED after 5 seconds."
  return 1
}
