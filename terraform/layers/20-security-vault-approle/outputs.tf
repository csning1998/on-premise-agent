
output "role_id" {
  description = "RoleID for the on-premise-agent Terraform admin AppRole."
  value       = vault_approle_auth_backend_role.agent_admin.role_id
}

output "secret_id" {
  description = "SecretID for the on-premise-agent Terraform admin AppRole."
  value       = vault_approle_auth_backend_role_secret_id.agent_admin.secret_id
  sensitive   = true
}

output "approle_path" {
  description = "Mount path of the AppRole auth backend."
  value       = vault_auth_backend.approle.path
}
