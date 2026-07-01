
# Enable KV v2 secrets engine on the on-premise-agent Vault
resource "vault_mount" "kv" {
  path = "secret"
  type = "kv"

  options = {
    version = "2"
  }
}

# Enable AppRole auth backend
resource "vault_auth_backend" "approle" {
  type = "approle"
  path = "approle"
}

# Namespace-scoped least-privilege policy for the on-premise-agent project
resource "vault_policy" "agent_admin" {
  name = "agent-terraform-admin-policy"

  policy = <<EOT
path "secret/data/on-premise-agent/*" {
  capabilities = ["read", "create", "update", "delete"]
}

path "secret/metadata/on-premise-agent/*" {
  capabilities = ["read", "list", "delete"]
}

path "secret/delete/on-premise-agent/*" {
  capabilities = ["update"]
}

path "secret/destroy/on-premise-agent/*" {
  capabilities = ["update"]
}
EOT
}

# AppRole for downstream layers (e.g. 25-security-credentials)
resource "vault_approle_auth_backend_role" "agent_admin" {
  backend        = vault_auth_backend.approle.path
  role_name      = "agent-terraform-admin"
  token_policies = [vault_policy.agent_admin.name]
  token_ttl      = 3600
  token_max_ttl  = 14400
}

resource "vault_approle_auth_backend_role_secret_id" "agent_admin" {
  backend   = vault_auth_backend.approle.path
  role_name = vault_approle_auth_backend_role.agent_admin.role_name
}
