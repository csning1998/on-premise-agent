
variable "vault_addr" {
  description = "Address of the local Podman Vault serving the on-premise-agent namespace."
  type        = string
  default     = "https://127.0.0.1:8210"
}

# Supply via TF_VAR_agent_role_id / TF_VAR_agent_secret_id, obtained by running
# `terraform output -raw role_id` / `-raw secret_id` in
# terraform/layers/20-security-vault-approle. Never place these in a
# terraform.tfvars file: they grant the full agent-terraform-admin-policy
# scope and must not be persisted as plaintext on local disk.
variable "agent_role_id" {
  description = "RoleID of the on-premise-agent Terraform admin AppRole (from Layer 20)."
  type        = string
  sensitive   = true
}

variable "agent_secret_id" {
  description = "SecretID of the on-premise-agent Terraform admin AppRole (from Layer 20)."
  type        = string
  sensitive   = true
}

variable "brave_api_key" {
  description = "Brave Search API key consumed by the pipelines service."
  type        = string
  sensitive   = true
}

variable "webui_secret_key" {
  description = "Open WebUI session signing secret."
  type        = string
  sensitive   = true
}

variable "webui_admin_password" {
  description = "Open WebUI admin account password."
  type        = string
  sensitive   = true
}

variable "searxng_secret" {
  description = "SearXNG instance secret key."
  type        = string
  sensitive   = true
}

variable "openai_api_keys" {
  description = "Shared API key authenticating Open WebUI to the pipelines OpenAI-compatible endpoint."
  type        = string
  sensitive   = true
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token used by the terraform/layers/00-cloudflare layer."
  type        = string
  sensitive   = true
}
