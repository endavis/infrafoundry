# SSH Authentication for Proxmox Operations

InfraFoundry uses SSH for certain Proxmox operations that don't have direct API support:
- Extracting compressed image files (`.xz`, `.gz`)
- Importing disk images (`qm importdisk`)

## Default Configuration

By default, InfraFoundry uses:
- **SSH User**: Your current username (`$USER`)
- **SSH Key**: ssh-agent or `~/.ssh/config` settings
- **SSH Port**: 22

## Per-Environment SSH Configuration

You can configure SSH settings per environment in your config repo:

```bash
# endavis-infra/envs/test/.ssh-config (example)
SSH_USER=endavis
SSH_KEY_PATH=~/.ssh/id_ed25519
SSH_PORT=22

# endavis-infra/envs/prod/.ssh-config
SSH_USER=automation
SSH_KEY_PATH=/secure/keys/prod_infra
SSH_PORT=2222
```

Or use Terraform variables:

```bash
# endavis-infra/envs/test/terraform.tfvars
proxmox_ssh_user     = "endavis"
proxmox_ssh_key_path = "/home/endavis/.ssh/id_ed25519"
proxmox_ssh_port     = 22
```

These will be automatically copied to the generated Terraform directory.

## Authentication Options

### Option 1: SSH Agent (Recommended for Development)

**Pros:** Most convenient, keys remain secure, works automatically
**Cons:** Requires ssh-agent running

```bash
# Start ssh-agent if not running
eval "$(ssh-agent -s)"

# Add your SSH key
ssh-add ~/.ssh/id_ed25519

# Verify key is loaded
ssh-add -l

# Test connection to Proxmox
ssh root@pve1 "hostname"

# Run InfraFoundry
infra apply --env test
```

The Terraform SSH provisioners will automatically use your ssh-agent.

### Option 2: Explicit SSH Key Path

**Pros:** Works in CI/CD, explicit configuration
**Cons:** Key path needs to be specified

Set environment variable or create `.tfvars` file:

```bash
# Via environment variable
export TF_VAR_proxmox_ssh_key_path="$HOME/.ssh/id_ed25519"

# Or create terraform.tfvars in generated/{env}/terraform/proxmox/
cat > generated/test/terraform/proxmox/terraform.tfvars <<EOF
proxmox_ssh_key_path = "/home/user/.ssh/id_ed25519"
proxmox_ssh_user     = "root"
proxmox_ssh_port     = 22
EOF

# Run InfraFoundry
infra apply --env test
```

### Option 3: SSH Config File

**Pros:** Centralized SSH configuration, works for multiple hosts
**Cons:** Additional setup required

Create or edit `~/.ssh/config`:

```ssh-config
Host pve1 pve2 pve3
    User root
    IdentityFile ~/.ssh/id_ed25519
    Port 22
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

Then InfraFoundry will use these settings automatically:

```bash
infra apply --env test
```

### Option 4: Passwordless SSH Key (CI/CD)

**For CI/CD pipelines**, set up passwordless SSH key on Proxmox:

```bash
# Generate SSH key without passphrase (in CI environment)
ssh-keygen -t ed25519 -f ~/.ssh/proxmox_ci -N ""

# Copy to Proxmox host
ssh-copy-id -i ~/.ssh/proxmox_ci root@pve1

# In CI, set environment variable
export TF_VAR_proxmox_ssh_key_path="/path/to/proxmox_ci"
```

## CI/CD Setup

### GitHub Actions

```yaml
- name: Setup SSH for Proxmox
  run: |
    mkdir -p ~/.ssh
    echo "${{ secrets.PROXMOX_SSH_KEY }}" > ~/.ssh/proxmox_ci
    chmod 600 ~/.ssh/proxmox_ci
    ssh-keyscan pve1 >> ~/.ssh/known_hosts

- name: Configure Terraform SSH
  run: |
    echo "TF_VAR_proxmox_ssh_key_path=$HOME/.ssh/proxmox_ci" >> $GITHUB_ENV
    echo "TF_VAR_proxmox_ssh_user=root" >> $GITHUB_ENV

- name: Deploy Infrastructure
  run: infra apply --env prod --auto-approve
```

### GitLab CI

```yaml
before_script:
  - mkdir -p ~/.ssh
  - echo "$PROXMOX_SSH_KEY" > ~/.ssh/proxmox_ci
  - chmod 600 ~/.ssh/proxmox_ci
  - ssh-keyscan pve1 >> ~/.ssh/known_hosts
  - export TF_VAR_proxmox_ssh_key_path="$HOME/.ssh/proxmox_ci"
  - export TF_VAR_proxmox_ssh_user="root"
```

## Configuration Variables

All SSH configuration can be customized via Terraform variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `proxmox_ssh_user` | SSH user for Proxmox host | `root` |
| `proxmox_ssh_key_path` | Path to SSH private key | `""` (uses ssh-agent) |
| `proxmox_ssh_port` | SSH port | `22` |

## Troubleshooting

### SSH Connection Refused

```bash
# Test SSH connection manually
ssh -v root@pve1 "hostname"

# Check if SSH is running on Proxmox
ssh root@pve1 "systemctl status ssh"
```

### Permission Denied (publickey)

```bash
# Verify key is added to ssh-agent
ssh-add -l

# Or specify key explicitly
export TF_VAR_proxmox_ssh_key_path="$HOME/.ssh/id_ed25519"

# Check key permissions
chmod 600 ~/.ssh/id_ed25519
```

### Host Key Verification Failed

InfraFoundry disables strict host key checking by default (`-o StrictHostKeyChecking=no`). If you want to enable it:

1. Add Proxmox host keys to `~/.ssh/known_hosts`:
   ```bash
   ssh-keyscan pve1 >> ~/.ssh/known_hosts
   ```

2. Remove the `StrictHostKeyChecking=no` option from generated Terraform (custom template modification needed)

### SSH Key Not Found in CI

Make sure to:
1. Store SSH private key as a secret (GitHub Secrets, GitLab CI Variables)
2. Write key to file with correct permissions (600)
3. Export `TF_VAR_proxmox_ssh_key_path` environment variable
4. Verify key format (should start with `-----BEGIN OPENSSH PRIVATE KEY-----`)

## Security Best Practices

1. **Use dedicated SSH keys** for infrastructure automation
2. **Restrict key access** with `chmod 600`
3. **Use SSH agent forwarding** cautiously (only in trusted environments)
4. **Rotate keys** regularly
5. **Use different keys** for different environments (dev/staging/prod)
6. **Consider SSH certificates** for large deployments
7. **Audit SSH access** via Proxmox logs

## Alternative: Avoid SSH Entirely

If SSH is not feasible in your environment, consider:

1. **Pre-download and extract images** on Proxmox manually
2. **Use pre-created templates** instead of `download_image`
3. **Create templates via Proxmox UI** and reference them in configs
4. **Request API support** from Proxmox team for missing functionality

See `docs/ubuntu-core-setup.md` for manual template creation steps.
