# Setting Up Your InfraFoundry Configuration

This guide walks you through setting up InfraFoundry for your environment with Proxmox and OPNsense.

## Choose Your Approach

### Option A: Automated Setup (Recommended for First Time)

Run the setup scripts to install all dependencies and configure your environment:

```bash
# Step 1: Install all system dependencies (just, uv, terraform, ansible, sops, age, direnv)
./scripts/setup-dependencies.sh

# The script will:
# - Install just command runner
# - Use just recipes to install all required tools
# - Verify installations
# - Show next steps

# Step 2: Run the interactive configuration wizard
./scripts/setup-config.sh

# The wizard will:
# - Install just and uv if not already present (uses just install-uv recipe)
# - Ask you questions about your infrastructure
# - Generate all configuration files automatically
# - Set up secrets management
# - Create .envrc.local for environment variables
```

### Option B: Manual Setup (Full Control)

Follow the steps below to manually configure everything.

---

## Manual Setup Steps

### Step 1: Gather Required Information

Before starting, collect this information:

#### Proxmox
- [ ] API URL: `https://your-proxmox-ip:8006/api2/json`
- [ ] API Token ID: `user@pam!tokenname` (create at Datacenter > Permissions > API Tokens)
- [ ] API Token Secret: (shown once when created)
- [ ] Node name(s): (e.g., `pve01`)
- [ ] Storage pool: (e.g., `local-lvm`)
- [ ] Network bridge: (usually `vmbr0`)
- [ ] VM template name: (if you have one)

#### OPNsense
- [ ] Web UI URL: `https://your-opnsense-ip`
- [ ] API Key: (create at System > Access > Users > Edit > API keys)
- [ ] API Secret: (shown once when created)

#### Network
- [ ] Network CIDR: (e.g., `192.168.1.0/24`)
- [ ] Gateway IP: (e.g., `192.168.1.1`)
- [ ] DNS servers: (e.g., `1.1.1.1, 8.8.8.8`)
- [ ] Domain name: (e.g., `homelab.local`)

### Step 2: Create Your Configuration Directory

Choose one:

**Option A: Use local example-config (simpler)**
```bash
# Work directly in example-config
cd example-config
```

**Option B: Create separate config repo (recommended)**
```bash
# Create new config repository
cp -r example-config ../my-infra-config
cd ../my-infra-config
git init
git add .
git commit -m "Initial configuration"

# Set environment variable
export INFRAFOUNDRY_CONFIG_REPO=/path/to/my-infra-config
```

### Step 3: Create Your Environment

```bash
# Create environment directory
ENV_NAME="homelab"  # or "production", "test", etc.
mkdir -p envs/$ENV_NAME

# Create provider directories
mkdir -p envs/$ENV_NAME/proxmox
mkdir -p envs/$ENV_NAME/opnsense
```

### Step 4: Configure Environment Settings and Credentials

Create `envs/$ENV_NAME/settings.yaml` with **all** configuration including credentials:

```yaml
name: homelab
description: Home lab environment

# Providers to enable
providers:
  - proxmox
  - opnsense

# Environment variables
variables:
  environment: homelab
  domain: homelab.local
  network_cidr: 192.168.1.0/24
  gateway_ip: 192.168.1.1

# Global SSH configuration (applies to all providers)
ssh:
  user: root
  port: 22
  # key_path: /home/user/.ssh/id_ed25519  # Optional

# Provider-specific settings (credentials, endpoints, defaults)
provider_settings:
  proxmox:
    # API credentials
    api_url: https://192.168.1.100:8006/api2/json
    api_token_id: root@pam!terraform
    api_token_secret: your-secret-token-here

    # Default settings
    node: pve01
    storage: local-lvm

  opnsense:
    # API credentials
    api_url: https://192.168.1.1
    api_key: your-api-key-here
    api_secret: your-api-secret-here
```

**IMPORTANT**: This file contains credentials. Keep it secure:
- Add to `.gitignore` if not using SOPS encryption
- Or encrypt it with SOPS (see encryption section below)
- Never commit unencrypted credentials to git

### Step 5: Configure Proxmox Resources

Create `envs/$ENV_NAME/proxmox/vms.yaml`:

```yaml
vms:
  # Basic test VM
  - name: test-vm-01
    target_node: pve01              # Your Proxmox node name
    clone: ubuntu-22-04-template    # Your VM template name
    cores: 2
    sockets: 1
    memory: 2048                    # 2GB RAM
    disk:
      size: 20G
      type: scsi
      storage: local-lvm            # Your storage pool
    network:
      model: virtio
      bridge: vmbr0                 # Your network bridge
    ipconfig: ip=192.168.1.100/24,gw=192.168.1.1  # Static IP
    onboot: true
    agent: 1                        # Enable QEMU guest agent
    ssh_user: ubuntu
    tags:
      - test
      - homelab
```

**If you don't have a VM template yet**, create one in Proxmox first:

```bash
# Example: Create Ubuntu 22.04 template
# 1. Download cloud image
wget https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img

# 2. Create VM and convert to template (run on Proxmox host)
qm create 9000 --name ubuntu-22-04-template --memory 2048 --cores 2 --net0 virtio,bridge=vmbr0
qm importdisk 9000 jammy-server-cloudimg-amd64.img local-lvm
qm set 9000 --scsihw virtio-scsi-pci --scsi0 local-lvm:vm-9000-disk-0
qm set 9000 --boot c --bootdisk scsi0
qm set 9000 --ide2 local-lvm:cloudinit
qm set 9000 --serial0 socket --vga serial0
qm set 9000 --agent enabled=1
qm template 9000
```

### Step 6: Configure OPNsense Resources

Create `envs/$ENV_NAME/opnsense/firewall_rules.yaml`:

```yaml
# Basic firewall rules
# Add more as needed

firewall_rules:
  - description: Allow SSH from LAN
    interface: lan
    protocol: tcp
    source_net: any
    destination_port: 22
    action: pass

  - description: Allow HTTPS from LAN
    interface: lan
    protocol: tcp
    source_net: any
    destination_port: 443
    action: pass
```

**Note**: For now, you can leave this file mostly empty until you're ready to manage firewall rules.

### Step 7: (Optional) Encrypt Settings with SOPS

InfraFoundry supports SOPS encryption for protecting sensitive credentials. You can encrypt the entire `settings.yaml` file or use the per-environment settings.yaml files approach for credential management.

Create `envs/dev/settings.yaml`:

```yaml
# Proxmox credentials
proxmox_api_url: https://192.168.1.100:8006/api2/json
proxmox_api_token_id: root@pam!terraform
proxmox_api_token_secret: your-secret-token-here

# OPNsense credentials
opnsense_api_url: https://192.168.1.1
opnsense_api_key: your-api-key-here
opnsense_api_secret: your-api-secret-here
```

**Encrypt it**:

```bash
# Initialize age encryption (first time only)
# This creates envs/dev/age.key, envs/prod/age.key, etc.
infra secrets init

# Create .sops.yaml configuration for per-environment secrets
cat > .sops.yaml << EOF
creation_rules:
  - path_regex: envs/dev/.*\.yaml$
    age: $(age-keygen -y envs/dev/age.key)
  - path_regex: envs/prod/.*\.yaml$
    age: $(age-keygen -y envs/prod/age.key)
EOF

# Move credentials to environment-specific directory
mkdir -p envs/dev envs/prod
mv envs/dev/settings.yaml envs/dev/credentials.yaml
cp envs/dev/credentials.yaml envs/prod/credentials.yaml  # Edit for prod!

# Encrypt the credentials files
sops --encrypt --in-place envs/dev/credentials.yaml
sops --encrypt --in-place envs/prod/credentials.yaml

# Verify they're encrypted
cat envs/dev/credentials.yaml  # Should show encrypted content
```

**Note**: Credentials are now organized per-environment in `envs/{env}/`. Use `--env` flag to automatically load the right credentials:
```bash
infra plan --env dev   # Uses envs/dev/credentials.yaml
infra apply --env prod # Uses envs/prod/credentials.yaml
```

**Future**: When `settings.yaml` SOPS support is implemented, you'll be able to:
```bash
# This will work in a future version
sops --encrypt --in-place envs/$ENV_NAME/settings.yaml
infra plan --env $ENV_NAME  # Will automatically decrypt
```

### Step 8: Configure Environment Variables

Create `.envrc.local` in the framework directory:

```bash
# .envrc.local - Personal settings (git-ignored)

# Point to your config directory (if using separate repo)
export INFRAFOUNDRY_CONFIG_REPO=/path/to/my-infra-config

# Proxmox credentials (use actual values)
export PROXMOX_API_URL=https://192.168.1.100:8006/api2/json
export PROXMOX_API_TOKEN_ID=root@pam!terraform
export PROXMOX_API_TOKEN_SECRET=your-secret-token-here

# OPNsense credentials (use actual values)
export OPNSENSE_API_URL=https://192.168.1.1
export OPNSENSE_API_KEY=your-api-key-here
export OPNSENSE_API_SECRET=your-api-secret-here

# Ansible configuration
export ANSIBLE_HOST_KEY_CHECKING=False

# Optional: Enable debug logging
# export INFRAFOUNDRY_LOG_LEVEL=DEBUG
```

Load the environment:

```bash
# If using direnv
direnv allow

# Or manually source
source .envrc.local
```

### Step 9: Test Your Configuration

```bash
# List available environments (should show your environment)
infra envs

# Generate Terraform files without applying (dry run)
infra plan --env homelab --dry-run

# Generate actual Terraform files
infra plan --env homelab

# Review generated files
ls -la generated/terraform/proxmox/
cat generated/terraform/proxmox/vms.tf
```

### Step 10: Deploy (When Ready)

```bash
# Apply the infrastructure
infra apply --env homelab

# Check status
infra status --env homelab

# If needed, destroy everything
infra destroy --env homelab
```

---

## Configuration Examples

### Example 1: Web Server

Add to `envs/$ENV_NAME/proxmox/vms.yaml`:

```yaml
  - name: webserver-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 2
    memory: 4096
    disk:
      size: 50G
      type: scsi
      storage: local-lvm
    network:
      model: virtio
      bridge: vmbr0
    ipconfig: ip=192.168.1.110/24,gw=192.168.1.1
    onboot: true
    agent: 1
    ssh_user: ubuntu
    tags:
      - webserver
      - nginx
    # Configure with Ansible after creation
    ansible_roles:
      - common
      - webserver
      - docker
```

### Example 2: Database Server

```yaml
  - name: database-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 4
    memory: 8192
    disk:
      size: 100G
      type: scsi
      storage: local-lvm
    network:
      model: virtio
      bridge: vmbr0
    ipconfig: ip=192.168.1.111/24,gw=192.168.1.1
    onboot: true
    agent: 1
    ssh_user: ubuntu
    tags:
      - database
      - postgresql
    ansible_roles:
      - common
      - database
```

### Example 3: Tailscale Exit Node

```yaml
  - name: tailscale-exit-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 2
    memory: 2048
    disk:
      size: 20G
      type: scsi
      storage: local-lvm
    network:
      model: virtio
      bridge: vmbr0
    ipconfig: ip=192.168.1.120/24,gw=192.168.1.1
    onboot: true
    agent: 1
    ssh_user: ubuntu
    tags:
      - tailscale
      - exit-node
    ansible_roles:
      - tailscale-exit-node
    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
```

Don't forget to add the Tailscale auth key to `envs/dev/settings.yaml`:

```yaml
vault_tailscale_auth_key: tskey-auth-xxxxxxxxxxxxx
```

---

## Troubleshooting

### Can't connect to Proxmox API

```bash
# Test connection manually
curl -k "${PROXMOX_API_URL}/version"

# Test with token
curl -k -H "Authorization: PVEAPIToken=${PROXMOX_API_TOKEN_ID}=${PROXMOX_API_TOKEN_SECRET}" \
  "${PROXMOX_API_URL}/nodes"
```

### Can't connect to OPNsense API

```bash
# Test connection
curl -k -u "${OPNSENSE_API_KEY}:${OPNSENSE_API_SECRET}" \
  "${OPNSENSE_API_URL}/api/core/firmware/status"
```

### Environment not found

```bash
# Check config directory
echo $INFRAFOUNDRY_CONFIG_REPO

# List environments
ls -la example-config/envs/  # or your config repo path

# Verify settings.yaml exists
cat example-config/envs/homelab/settings.yaml
```

### Terraform errors

```bash
# Enable debug logging
export INFRAFOUNDRY_LOG_LEVEL=DEBUG
export TF_LOG=DEBUG

# Run plan again
infra plan --env homelab

# Check generated Terraform
cd generated/terraform/proxmox
terraform validate
terraform plan
```

---

## Next Steps

1. **Start small**: Create one test VM first
2. **Verify it works**: Check in Proxmox web UI
3. **Add more VMs**: Gradually build out your infrastructure
4. **Add Ansible roles**: Configure VMs after creation
5. **Manage firewall rules**: Add OPNsense rules as needed
6. **Set up backups**: Implement backup strategy for critical VMs

## Additional Resources

- [Proxmox API Documentation](https://pve.proxmox.com/pve-docs/api-viewer/)
- [OPNsense API Documentation](https://docs.opnsense.org/development/api.html)
- [InfraFoundry Ansible Integration](docs/ansible-integration.md)
- [Tailscale Exit Node Role](example-config/roles/tailscale-exit-node/README.md)
