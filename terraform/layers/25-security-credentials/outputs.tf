
output "credential_paths" {
  description = "Mount-relative Vault KV paths of all written credentials."
  value = {
    pipelines_brave         = module.pipelines_brave.path
    open_webui_frontend     = module.open_webui_frontend.path
    searxng_frontend        = module.searxng_frontend.path
    cloudflare_api          = module.cloudflare_api.path
    pipelines_openai_compat = module.pipelines_openai_compat.path
  }
}
