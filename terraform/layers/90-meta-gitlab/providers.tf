
terraform {
  required_providers {
    gitlab = {
      source  = "gitlabhq/gitlab"
      version = "19.0.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "2.9.0"
    }
  }
  backend "http" {
    address        = "https://gitlab.com/api/v4/projects/83830958/terraform/state/90-meta-gitlab"
    lock_address   = "https://gitlab.com/api/v4/projects/83830958/terraform/state/90-meta-gitlab/lock"
    unlock_address = "https://gitlab.com/api/v4/projects/83830958/terraform/state/90-meta-gitlab/lock"
    lock_method    = "POST"
    unlock_method  = "DELETE"
    retry_wait_min = 5
  }
}

provider "gitlab" {
  token = var.gitlab_token
}
