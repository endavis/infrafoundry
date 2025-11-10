# Ubuntu Core Template Setup Guide

## What is Ubuntu Core?

Ubuntu Core is a minimal, containerized version of Ubuntu designed for IoT and embedded devices:
- **Immutable system** with transactional updates
- **Snap-based** package management (no apt/deb packages)
- **Smaller footprint** than regular Ubuntu
- **Built-in security** with AppArmor confinement
- **Cloud-init support** for automated provisioning

## Creating Ubuntu Core Template in Proxmox

### Fully Automated Method (Recommended - Use InfraFoundry!)

InfraFoundry can now download the ISO and build the template automatically via Terraform:

```yaml
# envs/test/resources/ubuntu-core-template.yaml
resources:
  - provider: proxmox
    type: template
    name: ubuntu-core-24-template
    config:
      vmid: 201
      target_node: pve1

      # Download Ubuntu Core image and create template automatically
      download_image:
        url: "https://cdimage.ubuntu.com/ubuntu-core/24/stable/current/ubuntu-core-24-amd64.img.xz"
        filename: "ubuntu-core-24-amd64.img.xz"
        extract: true  # Extract .xz file after download

      cores: 2
      memory: 2048

      disk:
        storage: share01

      network:
        bridge: vmbr1
        tag: 30

      # Cloud-init support - Add YOUR SSH keys (NO SSO REQUIRED!)
      cloud_init: true
      ciuser: ubuntu
      sshkeys: "ssh-ed25519 AAAAC3... user@host"

      agent: 1
```

Then just run:
```bash
# Create the template
infra apply --env test --resource ubuntu-core-24-template

# That's it! The template is ready to use
```

**What happens behind the scenes:**
1. InfraFoundry SSHs to your Proxmox host
2. Downloads Ubuntu Core image directly to Proxmox (no local download!)
3. Extracts the .xz file
4. Creates a VM with cloud-init configuration
5. Imports the Ubuntu Core disk image
6. Attaches the disk and configures cloud-init with your SSH key
7. Converts the VM to a template

**No manual steps, no SSO account needed!**

### Manual Method (If You Need Custom Setup)

If you want more control over the installation:

**Note:** The automated method above is much easier and doesn't require SSO!

If you still want to do manual installation:

1. Go to Proxmox UI → pve1 → local → ISO Images → "Download from URL"
2. URL: `https://cdimage.ubuntu.com/ubuntu-core/24/stable/current/ubuntu-core-24-amd64.img.xz`
3. Create VM with the ISO attached as CDROM
4. Complete interactive installation (requires Ubuntu SSO account)

**We recommend the automated method instead** - it's faster and uses cloud-init for SSH keys.

---

## Using the Template

### Clone VMs from Template

```yaml
# envs/test/resources/my-ubuntu-core-vm.yaml
resources:
  - provider: proxmox
    type: vm
    name: my-core-vm
    config:
      vmid: 301
      target_node: pve1
      clone: 201  # Ubuntu Core template VMID

      cores: 2
      memory: 2048

      disk:
        size: 20G
        storage: share01

      network:
        bridge: vmbr1
        tag: 30
        macaddr: "BC:24:11:1E:01:2C"

      cloud_init:      ipconfig: ip=dhcp
      ssh_user: your-ubuntu-sso-username
```

## Ubuntu Core Specifics

### Package Management
```bash
# Install packages (snaps only)
snap install <package>

# List installed snaps
snap list

# Update system
snap refresh
```

### System Updates
- Transactional updates (can rollback)
- Automatic security updates
- Reboot required for kernel updates

### SSH Access
- Uses Ubuntu SSO accounts only (no local users by default)
- SSH keys from your Ubuntu SSO profile automatically added
- No password authentication

### Tailscale on Ubuntu Core
```bash
# Install Tailscale
sudo snap install tailscale

# Connect
sudo tailscale up

# Enable as exit node
sudo tailscale up --advertise-exit-node
```

## Troubleshooting

### Cannot SSH to VM
- Ensure you used your Ubuntu SSO username during installation
- Check SSH keys are in your Ubuntu SSO profile
- Verify network connectivity (ping the VM IP)

### QEMU Guest Agent Not Working
```bash
# Check if running
snap services qemu-guest-agent

# Start if needed
sudo snap start qemu-guest-agent
```

### Disk Space Issues
Ubuntu Core is minimal, but snaps take space:
```bash
# Check disk usage
df -h

# Remove old snap revisions
sudo snap set system refresh.retain=2
```

## References

- [Ubuntu Core Documentation](https://ubuntu.com/core/docs)
- [Ubuntu Core Downloads](https://ubuntu.com/download/iot)
- [Snap Documentation](https://snapcraft.io/docs)
- [Cloud-init on Ubuntu Core](https://ubuntu.com/core/docs/cloud-init)
