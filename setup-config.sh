#!/usr/bin/env bash
#
# InfraFoundry Configuration Setup Wizard
# Interactive script to set up your environment configuration

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════╗
║                                                       ║
║          InfraFoundry Configuration Setup             ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo "This wizard will help you set up your InfraFoundry configuration."
echo ""

# Determine if using separate config repo or local
echo -e "${YELLOW}Configuration Location${NC}"
echo "1. Use local example-config/ directory (simpler, good for getting started)"
echo "2. Create separate configuration repository (recommended for production)"
echo ""
read -p "Choose option [1]: " config_location
config_location=${config_location:-1}

if [ "$config_location" = "2" ]; then
    read -p "Enter path for your config repository [../my-infra-config]: " config_path
    config_path=${config_path:-../my-infra-config}

    if [ ! -d "$config_path" ]; then
        echo -e "${GREEN}Creating new config repository at: $config_path${NC}"
        cp -r example-config "$config_path"
        cd "$config_path"
        git init
        echo -e "${GREEN}✓ Config repository created${NC}"
    fi

    CONFIG_DIR="$config_path"
    export INFRAFOUNDRY_CONFIG_REPO="$config_path"
else
    CONFIG_DIR="example-config"
fi

echo ""
echo -e "${YELLOW}Environment Name${NC}"
read -p "What should we call your environment? [homelab]: " env_name
env_name=${env_name:-homelab}

# Create environment directory if using new name
ENV_DIR="$CONFIG_DIR/envs/$env_name"
if [ ! -d "$ENV_DIR" ]; then
    mkdir -p "$ENV_DIR"
    echo -e "${GREEN}✓ Created environment directory: $ENV_DIR${NC}"
fi

echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}Proxmox Configuration${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"

read -p "Proxmox API URL (e.g., https://192.168.1.100:8006/api2/json): " proxmox_url
read -p "Proxmox API Token ID (e.g., root@pam!terraform): " proxmox_token_id
read -sp "Proxmox API Token Secret: " proxmox_token_secret
echo ""
read -p "Proxmox node name(s) [pve01]: " proxmox_node
proxmox_node=${proxmox_node:-pve01}
read -p "Storage pool for VMs [local-lvm]: " proxmox_storage
proxmox_storage=${proxmox_storage:-local-lvm}
read -p "Network bridge [vmbr0]: " proxmox_bridge
proxmox_bridge=${proxmox_bridge:-vmbr0}
read -p "Do you have a VM template? [ubuntu-22-04-template]: " vm_template
vm_template=${vm_template:-ubuntu-22-04-template}

echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}OPNsense Configuration${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"

read -p "OPNsense web UI URL (e.g., https://192.168.1.1): " opnsense_url
read -p "OPNsense API Key: " opnsense_key
read -sp "OPNsense API Secret: " opnsense_secret
echo ""

echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}Network Configuration${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"

read -p "Your local network CIDR [192.168.1.0/24]: " network_cidr
network_cidr=${network_cidr:-192.168.1.0/24}
read -p "Gateway IP [192.168.1.1]: " gateway_ip
gateway_ip=${gateway_ip:-192.168.1.1}
read -p "Starting IP for VMs [192.168.1.100]: " vm_start_ip
vm_start_ip=${vm_start_ip:-192.168.1.100}
read -p "Domain name [homelab.local]: " domain_name
domain_name=${domain_name:-homelab.local}

echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}Additional Features${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"

read -p "Set up a Tailscale exit node? [y/N]: " setup_tailscale
setup_tailscale=${setup_tailscale:-n}

if [[ "$setup_tailscale" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Tailscale Authentication Method:"
    echo "  1. Auth Key (recommended for automation, CI/CD)"
    echo "  2. OAuth (more secure, interactive deployments)"
    read -p "Choose method [1]: " tailscale_auth_method
    tailscale_auth_method=${tailscale_auth_method:-1}

    if [ "$tailscale_auth_method" = "2" ]; then
        echo ""
        echo "Generate OAuth credentials at: https://login.tailscale.com/admin/settings/oauth"
        read -p "OAuth Client ID (or press Enter to configure later): " tailscale_oauth_id
        read -sp "OAuth Client Secret (or press Enter to configure later): " tailscale_oauth_secret
        echo ""
    else
        echo ""
        echo "Generate auth key at: https://login.tailscale.com/admin/settings/keys"
        read -p "Tailscale auth key (or press Enter to configure later): " tailscale_key
    fi
fi

# Generate configuration files
echo ""
echo -e "${GREEN}Generating configuration files...${NC}"

# Create environment.yaml
cat > "$ENV_DIR/environment.yaml" << EOF
name: $env_name
description: ${env_name^} environment
providers:
  - proxmox
  - opnsense

variables:
  environment: $env_name
  domain: $domain_name
  network_cidr: $network_cidr
  gateway_ip: $gateway_ip
EOF

echo -e "${GREEN}✓ Created $ENV_DIR/environment.yaml${NC}"

# Create Proxmox directory
mkdir -p "$ENV_DIR/proxmox"

# Create a basic VM configuration
cat > "$ENV_DIR/proxmox/vms.yaml" << EOF
vms:
  - name: test-vm-01
    target_node: $proxmox_node
    clone: $vm_template
    cores: 2
    sockets: 1
    memory: 2048
    disk:
      size: 20G
      type: scsi
      storage: $proxmox_storage
    network:
      model: virtio
      bridge: $proxmox_bridge
    ipconfig: ip=$vm_start_ip/24,gw=$gateway_ip
    onboot: true
    agent: 1
    ssh_user: ubuntu
    tags:
      - test
      - $env_name
EOF

if [[ "$setup_tailscale" =~ ^[Yy]$ ]]; then
    if [ "$tailscale_auth_method" = "2" ]; then
        # OAuth configuration
        cat >> "$ENV_DIR/proxmox/vms.yaml" << EOF

  # Tailscale exit node (OAuth authentication)
  - name: tailscale-exit-01
    target_node: $proxmox_node
    clone: $vm_template
    cores: 2
    sockets: 1
    memory: 2048
    disk:
      size: 20G
      type: scsi
      storage: $proxmox_storage
    network:
      model: virtio
      bridge: $proxmox_bridge
    ipconfig: ip=${vm_start_ip%.*}.101/24,gw=$gateway_ip
    onboot: true
    agent: 1
    ssh_user: ubuntu
    tags:
      - tailscale
      - exit-node
    ansible_roles:
      - common
      - tailscale-exit-node
    ansible_vars:
      tailscale_auth_method: "oauth"
      tailscale_oauth_client_id: "{{ vault_tailscale_oauth_client_id }}"
      tailscale_oauth_client_secret: "{{ vault_tailscale_oauth_client_secret }}"
EOF
    else
        # Auth Key configuration (default)
        cat >> "$ENV_DIR/proxmox/vms.yaml" << EOF

  # Tailscale exit node
  - name: tailscale-exit-01
    target_node: $proxmox_node
    clone: $vm_template
    cores: 2
    sockets: 1
    memory: 2048
    disk:
      size: 20G
      type: scsi
      storage: $proxmox_storage
    network:
      model: virtio
      bridge: $proxmox_bridge
    ipconfig: ip=${vm_start_ip%.*}.101/24,gw=$gateway_ip
    onboot: true
    agent: 1
    ssh_user: ubuntu
    tags:
      - tailscale
      - exit-node
    ansible_roles:
      - common
      - tailscale-exit-node
    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
EOF
    fi
fi

echo -e "${GREEN}✓ Created $ENV_DIR/proxmox/vms.yaml${NC}"

# Create OPNsense directory
mkdir -p "$ENV_DIR/opnsense"

cat > "$ENV_DIR/opnsense/firewall_rules.yaml" << EOF
# OPNsense firewall rules
# Add your firewall rules here

# Example rule:
# firewall_rules:
#   - description: Allow SSH from LAN
#     interface: lan
#     protocol: tcp
#     source_net: any
#     destination_port: 22
#     action: pass
EOF

echo -e "${GREEN}✓ Created $ENV_DIR/opnsense/firewall_rules.yaml${NC}"

# Create secrets directory
mkdir -p "$CONFIG_DIR/secrets"

# Create secrets file
cat > "$CONFIG_DIR/secrets/credentials.yaml" << EOF
# Proxmox credentials
proxmox_api_url: $proxmox_url
proxmox_api_token_id: $proxmox_token_id
proxmox_api_token_secret: $proxmox_token_secret

# OPNsense credentials
opnsense_api_url: $opnsense_url
opnsense_api_key: $opnsense_key
opnsense_api_secret: $opnsense_secret
EOF

if [[ "$setup_tailscale" =~ ^[Yy]$ ]]; then
    if [ "$tailscale_auth_method" = "2" ]; then
        # OAuth credentials
        if [ -n "$tailscale_oauth_id" ] || [ -n "$tailscale_oauth_secret" ]; then
            cat >> "$CONFIG_DIR/secrets/credentials.yaml" << EOF

# Tailscale OAuth
vault_tailscale_oauth_client_id: ${tailscale_oauth_id:-"CHANGEME"}
vault_tailscale_oauth_client_secret: ${tailscale_oauth_secret:-"CHANGEME"}
EOF
        fi
    else
        # Auth key
        if [ -n "$tailscale_key" ]; then
            cat >> "$CONFIG_DIR/secrets/credentials.yaml" << EOF

# Tailscale Auth Key
vault_tailscale_auth_key: $tailscale_key
EOF
        fi
    fi
fi

echo -e "${GREEN}✓ Created $CONFIG_DIR/secrets/credentials.yaml${NC}"

# Create .envrc.local in framework directory
ENVRC_LOCAL=".envrc.local"

cat > "$ENVRC_LOCAL" << EOF
# .envrc.local - Personal settings (git-ignored)
# Generated by setup wizard on $(date)

# Configuration repository location
export INFRAFOUNDRY_CONFIG_REPO=$PWD/$CONFIG_DIR

# Proxmox credentials
export PROXMOX_API_URL=$proxmox_url
export PROXMOX_API_TOKEN_ID=$proxmox_token_id
export PROXMOX_API_TOKEN_SECRET=$proxmox_token_secret

# OPNsense credentials
export OPNSENSE_API_URL=$opnsense_url
export OPNSENSE_API_KEY=$opnsense_key
export OPNSENSE_API_SECRET=$opnsense_secret

# Ansible configuration
export ANSIBLE_HOST_KEY_CHECKING=False

# Log level
export INFRAFOUNDRY_LOG_LEVEL=INFO
EOF

echo -e "${GREEN}✓ Created .envrc.local${NC}"

echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Configuration Setup Complete!${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo ""

echo "📁 Configuration files created:"
echo "   • $ENV_DIR/environment.yaml"
echo "   • $ENV_DIR/proxmox/vms.yaml"
echo "   • $ENV_DIR/opnsense/firewall_rules.yaml"
echo "   • $CONFIG_DIR/secrets/credentials.yaml"
echo "   • .envrc.local"
echo ""

echo -e "${YELLOW}⚠️  IMPORTANT SECURITY STEPS:${NC}"
echo ""
echo "1. Encrypt your secrets file with SOPS:"
echo ""
echo "   ${BLUE}# First, initialize age encryption${NC}"
echo "   infra secrets init"
echo ""
echo "   ${BLUE}# Then encrypt the credentials file${NC}"
echo "   infra secrets encrypt $CONFIG_DIR/secrets/credentials.yaml"
echo ""
echo "2. Load environment variables:"
echo ""
echo "   ${BLUE}# If using direnv (recommended)${NC}"
echo "   direnv allow"
echo ""
echo "   ${BLUE}# Or manually source the file${NC}"
echo "   source .envrc.local"
echo ""

echo -e "${YELLOW}🚀 Next Steps:${NC}"
echo ""
echo "1. Review and customize your configuration:"
echo "   • Edit $ENV_DIR/proxmox/vms.yaml to add/modify VMs"
echo "   • Edit $ENV_DIR/opnsense/firewall_rules.yaml for firewall rules"
echo ""
echo "2. Test the configuration:"
echo "   ${BLUE}infra envs${NC}                    # List environments"
echo "   ${BLUE}infra plan --env $env_name${NC}    # Generate Terraform files (dry run)"
echo ""
echo "3. When ready to deploy:"
echo "   ${BLUE}infra apply --env $env_name${NC}   # Deploy infrastructure"
echo ""

if [[ "$setup_tailscale" =~ ^[Yy]$ ]]; then
    if [ "$tailscale_auth_method" = "2" ]; then
        # OAuth reminders
        if [ -z "$tailscale_oauth_id" ] || [ -z "$tailscale_oauth_secret" ]; then
            echo -e "${YELLOW}📝 Don't forget to:${NC}"
            echo "   • Generate OAuth credentials at: https://login.tailscale.com/admin/settings/oauth"
            echo "   • Add them to $CONFIG_DIR/secrets/credentials.yaml:"
            echo "       vault_tailscale_oauth_client_id: \"your-client-id\""
            echo "       vault_tailscale_oauth_client_secret: \"tskey-client-xxxxx\""
            echo "   • Re-encrypt the secrets file"
            echo ""
        fi
        echo -e "${YELLOW}ℹ️  OAuth Authentication:${NC}"
        echo "   • During deployment, you'll be prompted to visit a URL"
        echo "   • Approve the device in your browser"
        echo "   • Deployment will continue automatically"
        echo ""
    else
        # Auth key reminders
        if [ -z "$tailscale_key" ]; then
            echo -e "${YELLOW}📝 Don't forget to:${NC}"
            echo "   • Generate a Tailscale auth key at: https://login.tailscale.com/admin/settings/keys"
            echo "   • Add it to $CONFIG_DIR/secrets/credentials.yaml as 'vault_tailscale_auth_key'"
            echo "   • Re-encrypt the secrets file"
            echo ""
        fi
    fi
fi

echo -e "${GREEN}Happy infrastructure automation! 🎉${NC}"
echo ""
