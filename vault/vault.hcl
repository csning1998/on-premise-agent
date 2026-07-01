
ui            = true
api_addr      = "https://127.0.0.1:8210"
cluster_addr  = "https://127.0.0.1:8211"
disable_mlock = false

storage "raft" {
  node_id = "node1"
  path    = "/opt/vault/data"
}

# Bound to loopback only. This relies on compose.yaml's vault service using
# network_mode: host; switching to a bridge/overlay network requires changing
# this address to a routable interface.
listener "tcp" {
  address       = "127.0.0.1:8210"
  tls_disable   = false
  tls_cert_file = "/opt/vault/tls/vault.pem"
  tls_key_file  = "/opt/vault/tls/vault-key.pem"
}
