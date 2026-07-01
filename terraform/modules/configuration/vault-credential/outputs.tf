
output "path" {
  description = "Vault KV mount-relative path for cross-layer ephemeral reads"
  value       = vault_kv_secret_v2.this.name
}

output "credentials" {
  # Callers must never reference this in a non-sensitive context (e.g. a tag
  # value); on Terraform < 1.5 a module output's sensitive marking does not
  # propagate to how the calling module's own state renders the value.
  description = "All credentials (generated + static) keyed by name"
  value = merge(
    var.static,
    { for k, v in random_password.this : k => v.result }
  )
  sensitive = true
}
