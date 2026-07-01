
terraform {
  required_providers {
    vault = {
      source  = "hashicorp/vault"
      version = "5.5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.6.3"
    }
  }
  backend "http" {
    address        = "https://gitlab.com/api/v4/projects/83830958/terraform/state/25-security-credentials"
    lock_address   = "https://gitlab.com/api/v4/projects/83830958/terraform/state/25-security-credentials/lock"
    unlock_address = "https://gitlab.com/api/v4/projects/83830958/terraform/state/25-security-credentials/lock"
    lock_method    = "POST"
    unlock_method  = "DELETE"
    retry_wait_min = 5
  }
}

provider "vault" {
  alias        = "production"
  address      = var.vault_addr
  ca_cert_file = abspath("${path.root}/../../../vault/tls/ca.pem")

  auth_login {
    path = "auth/approle/login"
    parameters = {
      role_id   = var.agent_role_id
      secret_id = var.agent_secret_id
    }
  }
  skip_child_token = true
}
