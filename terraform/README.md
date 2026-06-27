# Terraform Pipeline Architecture

## Section 1. Terraform Remote States

Both layers store state on GitLab.com via the Terraform HTTP backend (Project ID: `83830958`). `terraform apply` and `terraform destroy` require no extra CLI flags after initialization.

### Step A. Local Credential Files

Two gitignored files must be created once by the operator. Neither enters version control.

1. **`terraform/backend-auth.hcl`**

    Used only by `terraform init -backend-config`. Contains the GitLab PAT with `api` scope.

    ```hcl
    username = "oauth2"
    password = "glpat-xxxxxxxxxxxxxxxxxxxx"
    ```

2. **`terraform/backend-state.json`**

    Read at plan/apply time by `90-meta-gitlab/locals.tf` via `jsondecode(file(...))`. Supplies credentials for cross-layer remote state reads without CLI injection.

    ```json
    { "username": "oauth2", "token": "glpat-xxxxxxxxxxxxxxxxxxxx" }
    ```

### Step B. Initializing a Layer

1. **First-time init (no existing local state)**

    ```bash
    cd terraform/<layer-name>
    terraform init -backend-config=../backend-auth.hcl
    ```

2. **Migrating existing local state to remote**

    ```bash
    cd terraform/<layer-name>
    terraform init -migrate-state -backend-config=../backend-auth.hcl
    ```

    `-migrate-state` uploads the existing `terraform.tfstate` to GitLab.com and removes the local file reference.

### Step C. Cross-Layer State Read Mechanism

1. **Authentication locals**: `locals.tf` in `90-meta-gitlab` defines the local credentials block consumed by remote state data sources:

    ```hcl
    locals {
        _gl_creds   = jsondecode(file("${path.root}/../backend-state.json"))
        _state_base = "https://gitlab.com/api/v4/projects/83830958/terraform/state"
        _state_auth = {
            username = local._gl_creds.username
            password = local._gl_creds.token
        }
    }
    ```

2. **Data source pattern**: When a layer needs to read state from another layer, it uses `merge()` to inject `_state_auth` alongside the target address:

    ```hcl
    data "terraform_remote_state" "cloudflare" {
      backend = "http"
      config  = merge(local._state_auth, { address = "${local._state_base}/00-cloudflare" })
    }
    ```

### Step D. Layers and Deployment Sequence

Initialize and apply layers in the sequence listed below:

| #   | Layer            | Description                                                           |
| --- | ---------------- | --------------------------------------------------------------------- |
| 1   | `00-cloudflare`  | Manages Cloudflare resources (DNS records, tunnels, etc.)             |
| 2   | `90-meta-gitlab` | Manages GitLab project settings and branch protections for the mirror |

The following bulk-init script is a convenience shortcut. This script assumes all upstream remote states already exist.

```bash
for dir in ./*; do
    if [ -d "$dir" ] && [ -f "$dir/providers.tf" ]; then
        (echo -e "\n\n${dir}" && cd "$dir" && terraform init -upgrade -backend-config=../backend-auth.hcl)
    fi
done
```
