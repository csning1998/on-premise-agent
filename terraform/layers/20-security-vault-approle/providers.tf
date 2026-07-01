
terraform {
  required_providers {
    vault = {
      source  = "hashicorp/vault"
      version = "5.5.0"
    }
  }
  backend "http" {
    address        = "https://gitlab.com/api/v4/projects/83830958/terraform/state/20-security-vault-approle"
    lock_address   = "https://gitlab.com/api/v4/projects/83830958/terraform/state/20-security-vault-approle/lock"
    unlock_address = "https://gitlab.com/api/v4/projects/83830958/terraform/state/20-security-vault-approle/lock"
    lock_method    = "POST"
    unlock_method  = "DELETE"
    retry_wait_min = 5
  }
}

# Local Podman Vault (bootstrapper/target unified for this project's minimal scope)
provider "vault" {
  address      = var.vault_addr
  ca_cert_file = abspath("${path.root}/../../../vault/tls/ca.pem")
}
