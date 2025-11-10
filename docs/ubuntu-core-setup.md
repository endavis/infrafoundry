# Ubuntu Core Template Setup Guide

## What is Ubuntu Core?

Ubuntu Core is a minimal, containerized version of Ubuntu designed for IoT and embedded devices:
- **Immutable system** with transactional updates
- **Snap-based** package management (no apt/deb packages)
- **Smaller footprint** than regular Ubuntu
- **Built-in security** with AppArmor confinement
- **Cloud-init support** for automated provisioning

## Creating Ubuntu Core Template in Proxmox

### Step 1: Download Ubuntu Core Image

```bash
# On your workstation or Proxmox host
wget https://cdimage.ubuntu.com/ubuntu-core/24/stable/current/ubuntu-core-24-amd64.img.xz
xz -d ubuntu-core-24-amd64.img.xz
```

### Step 2: Upload to Proxmox

Option A - Via Web UI:
1. Go to Proxmox node (pve1) > local > ISO Images
2. Upload `ubuntu-core-24-amd64.img`

Option B - Via SCP:
```bash
scp ubuntu-core-24-amd64.img root@pve1:/var/lib/vz/template/iso/
```

### Step 3: Create VM Manually

```bash
# SSH to Proxmox host
ssh root@pve1

# Create VM
qm create 201 \
  --name ubuntu-core-24-template \
  --memory 2048 \
  --cores 2 \
  --net0 virtio,bridge=vmbr1,tag=30 \
  --scsi0 share01:20 \
  --cdrom local:iso/ubuntu-core-24-amd64.img \
  --boot order=scsi0 \
  --agent 1

# Start VM and complete installation
qm start 201
```

### Step 4: Complete Ubuntu Core Installation

1. Open console: `qm terminal 201` or use Proxmox web UI
2. Select installation language
3. Connect to network (DHCP on VLAN 30)
4. **Important:** Link to Ubuntu SSO account (required for SSH access)
5. Wait for installation to complete
6. Reboot when prompted

### Step 5: Post-Installation Configuration

```bash
# SSH to the Ubuntu Core VM (use your SSO username)
ssh <your-ubuntu-sso-username>@<vm-ip>

# Install QEMU guest agent
sudo snap install qemu-guest-agent

# Configure cloud-init for future clones
sudo snap install cloud-init

# Clean up for templating
sudo cloud-init clean
sudo rm -rf /var/lib/cloud/instances
sudo sync
```

### Step 6: Convert to Template

```bash
# On Proxmox host
qm shutdown 201
qm template 201
```

## Using the Template with InfraFoundry

Once the template is created, update the configuration:

```yaml
# envs/test/resources/ubuntu-core-template.yaml
resources:
  - provider: proxmox
    type: template
    name: ubuntu-core-24-template
    config:
      vmid: 201
      # Template is already created manually, no need to clone
      # InfraFoundry will just track it
```

## Cloning VMs from Template

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
      
      ipconfig: ip=dhcp
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
