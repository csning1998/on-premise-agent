
# Sensitive Credentials
variable "cloudflare" {
  description = "Cloudflare security credentials"
  type = object({
    api_token = string
  })
  sensitive = true
}
