# Open WebUI + Ollama RAG

## Section 0. Introduction

This project implements a **Multistage Deep-Thinking Agent** that integrates **Ollama**, **Open WebUI**, and **SearXNG** to provide advanced reasoning capabilities. It addresses the limitations of the native RAG system by utilizing a containerized **Pipelines** service for complex, multistage tasks.

Native RAG mode cannot switch models between the intent analysis and deep reasoning stages. In an 8GB VRAM environment, this leads to Out-of-Memory (OOM) errors or severe performance degradation when attempting to load E4B and 26B simultaneously.

### Development machine (for reference only)

- **Chipset**: Intel® HM770
- **CPU**: Intel® Core™ i7-14700HX
- **GPU**: NVIDIA RTX 4070 with 8GB DDR6 VRAM (Laptop Mobile)
- **RAM**: Micron Crucial Pro 64 GB (32 GB × 2) DDR5-5600
- **SSD**: WD PC SN560 1 TB
- **OS**: Linux, Fedora 44 KDE

## Section 1. Configure Environment

### Step A. NVIDIA GPU Container Device Interface

To allow Podman to correctly identify and invoke NVIDIA GPUs, a CDI (Container Device Interface) specification file must be generated.

- **Generate CDI configuration file:**

    It is recommended to use a system-wide path to ensure complete permissions.

    ```zsh
    sudo mkdir -p /etc/cdi
    sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml --device-name-strategy=type-index
    ```

- **Verify device list:**

    Confirm that the output includes `nvidia.com/gpu=all`.

    ```zsh
    nvidia-ctk cdi list
    ```

- **Smoke Test:**

    Ensure that GPU information can be correctly read inside the container.

    ```zsh
    podman run --rm --device nvidia.com/gpu=all fedora nvidia-smi
    ```

- **Fix: CDI Device Injection Failure (`failed to stat /dev/nvidia-modeset`):**

    If Podman fails with an error stating it cannot find `/dev/nvidia-modeset`, which means the CDI specification is likely stale. Regenerate it locally and instruct Podman to prioritize it:
    1. Regenerate CDI spec for the current user

        ```zsh
        mkdir -p ~/.config/cdi
        nvidia-ctk cdi generate --output=${HOME}/.config/cdi/nvidia.yaml
        ```

    2. Force Podman to ignore broken system-wide CDI specs

        ```zsh
        mkdir -p ~/.config/containers
        cat <<EOF > ~/.config/containers/containers.conf
        [engine]
        cdi_spec_dirs = ["${HOME}/.config/cdi"]
        EOF
        ```

### Step B. SELinux Security Policy Configuration

Fedora's default SELinux policy restricts container access to hardware devices and specific system calls; these must be manually permitted.

- **Enable device usage permissions:**

    ```zsh
    sudo setsebool -P container_use_devices true
    sudo setsebool -P container_manage_cgroup true
    ```

- **Reset device node security:**

    To prevent terminal access errors that may be caused by the Rootless network driver (pasta).

    ```zsh
    sudo restorecon -v /dev/ptmx
    ```

- **Enable Podman User Socket:**

    Required for Terraform (OpenTofu) to manage containers via the local socket.

    ```zsh
    systemctl --user enable --now podman.socket
    ```

### Step C. Security Keys and Variable Configuration

1. **Initialize the required `.tfvars` files:**

    ```zsh
    cp terraform/terraform.tfvars.example terraform/terraform.tfvars
    ```

2. **Generate a random Base64 key:**

    ```zsh
    openssl rand -base64 32
    ```

    Fill the generated string into the `open_web_ui.secret_key` field in the `terraform.tfvars` file.

    > [!TIP]
    > **Container Runtime Socket**:
    >
    > - **Podman (Rootless)**: `unix:///run/user/<UID>/podman/podman.sock` (Retrieve UID via `id -u`).
    > - **Docker (Standard)**: `unix:///var/run/docker.sock`.
    >   Update `project_info.docker_host` in `terraform.tfvars` accordingly.

### Step D. Volume Permissions and UID Mapping Handling

In Rootless mode, there is a mapping relationship between the host user and the `root` (UID 0) inside the container; `podman unshare` must be used to correct directory ownership.

- **Directory initialization and permission transfer:**
    1. Create data storage directories
    2. Map directory ownership to the container's root (0:0)
    3. Grant appropriate read, write, and execute permissions

    ```zsh
    mkdir -p ./ollama_data ./open-webui_data ./searxng_data
    podman unshare chown -R 0:0 ./ollama_data ./open-webui_data ./searxng_data
    chmod -R 775 ./ollama_data ./open-webui_data ./searxng_data
    ```

### Step E. Infrastructure Deployment

Use OpenTofu/Terraform to start the integrated services and ensure SELinux labels are correct.

- **Initialize and Apply:**

    ```zsh
    cd terraform
    terraform init
    terraform plan
    terraform apply -auto-approve
    ```

    Simply change `terraform` to `tofu` if OpenTofu is preferred.

- **Migrate existing local models (Optional):**

    Existing models located in the host directory (e.g., `~/.ollama`) can be migrated into the isolated container volume. Re-application of the rootless ownership mapping is mandatory after file transfer.

    ```zsh
    cp -r ~/.ollama/models/* ./ollama_data/models/
    podman unshare chown -R 0:0 ./ollama_data/models
    ```

- **Check Ollama model list and permissions:**

    If this step does not report `permission denied`, the configuration was successful.

    ```zsh
    podman exec -it ollama ollama list
    ```

- **View real-time logs:**

    ```zsh
    podman logs -f open-webui
    ```

## Section 2. Troubleshooting

### A. Permission Denied (`mkdir /root/.ollama/models`)

In Podman + SELinux Enforcing mode, ensure the `volumes` block in `resources.tf` includes `selinux_relabel = "Z"`. Also verify `podman unshare` is executed as described in Step D.

### B. Unresolvable CDI Device

Please confirm whether the `/etc/cdi/nvidia.yaml` file contains the correct device name and ensure the file has global read permissions (`chmod a+r`).

```zsh
podman unshare chown -R 0:0 ./ollama_data ./open-webui_data
chmod -R 775 ./ollama_data ./open-webui_data
```
