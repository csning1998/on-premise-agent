
module "pipelines_brave" {
  source = "../../modules/configuration/vault-credential"

  domain    = "pipelines"
  component = "brave-search"

  static = {
    brave_api_key = var.brave_api_key
  }

  vault_kv_namespace = local.vault_kv_namespace

  providers = {
    vault.production = vault.production
  }
}

module "open_webui_frontend" {
  source = "../../modules/configuration/vault-credential"

  domain    = "open-webui"
  component = "frontend"

  static = {
    webui_secret_key     = var.webui_secret_key
    webui_admin_password = var.webui_admin_password
  }

  vault_kv_namespace = local.vault_kv_namespace

  providers = {
    vault.production = vault.production
  }
}

module "searxng_frontend" {
  source = "../../modules/configuration/vault-credential"

  domain    = "searxng"
  component = "frontend"

  static = {
    searxng_secret = var.searxng_secret
  }

  vault_kv_namespace = local.vault_kv_namespace

  providers = {
    vault.production = vault.production
  }
}

module "pipelines_openai_compat" {
  source = "../../modules/configuration/vault-credential"

  domain    = "pipelines"
  component = "openai-compat"

  static = {
    openai_api_keys = var.openai_api_keys
  }

  vault_kv_namespace = local.vault_kv_namespace

  providers = {
    vault.production = vault.production
  }
}

module "cloudflare_api" {
  source = "../../modules/configuration/vault-credential"

  domain    = "cloudflare"
  component = "api"

  static = {
    cloudflare_api_token = var.cloudflare_api_token
  }

  vault_kv_namespace = local.vault_kv_namespace

  providers = {
    vault.production = vault.production
  }
}
