
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "5.21.1"
    }
  }
  backend "http" {
    address        = "https://gitlab.com/api/v4/projects/83830958/terraform/state/00-cloudflare"
    lock_address   = "https://gitlab.com/api/v4/projects/83830958/terraform/state/00-cloudflare/lock"
    unlock_address = "https://gitlab.com/api/v4/projects/83830958/terraform/state/00-cloudflare/lock"
    lock_method    = "POST"
    unlock_method  = "DELETE"
    retry_wait_min = 5
  }
}

provider "cloudflare" {
  api_token = var.cloudflare.api_token
}
