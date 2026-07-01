
variable "vault_addr" {
  description = "Address of the local Podman Vault serving the on-premise-agent namespace."
  type        = string
  default     = "https://127.0.0.1:8210"
}
