# OPNsense Configuration Parser

A tool to parse OPNsense `config.xml` backup files and generate clean, organized YAML configurations compatible with InfraFoundry (or any infrastructure-as-code tool).

## Overview

The OPNsense parser extracts all essential configuration from an OPNsense XML backup and converts it into structured YAML files. This enables:

- **Documentation** - Human-readable configuration files
- **Version Control** - Track changes to your firewall configuration over time
- **Disaster Recovery** - Rebuild your OPNsense setup from scratch
- **Infrastructure as Code** - Integrate with InfraFoundry or other automation tools
- **Migration** - Easily transfer configurations between OPNsense instances

## Installation

No additional dependencies required beyond standard InfraFoundry installation.

## Usage

### Basic Usage

```bash
python tools/opnsense-parser.py <config.xml> [-o output_directory]
```

### Examples

```bash
# Parse with default output directory (opnsense-config)
python tools/opnsense-parser.py ~/Downloads/config-OPNsense-20251107.xml

# Parse with custom output directory
python tools/opnsense-parser.py config.xml -o my-opnsense-configs

# Parse directly from your config repo
python tools/opnsense-parser.py \
  ~/backups/config-OPNsense.xml \
  -o $INFRAFOUNDRY_CONFIG_REPO/envs/prod/opnsense
```

## Exported Configuration

The parser extracts the following configuration sections:

### System Settings (`system.yaml`)
- Hostname and domain
- Timezone
- DNS servers
- SSH configuration
- WebGUI settings

### Network Configuration
- **`interfaces.yaml`** - All network interfaces with IPv4/IPv6 addresses
- **`vlans.yaml`** - VLAN definitions
- **`gateways.yaml`** - Default and VPN gateways

### Firewall (`firewall_rules_*.yaml`)
- **`aliases.yaml`** - Host groups, network groups, port aliases
- **`firewall_rules_<interface>.yaml`** - Rules separated by interface
- **`firewall_rules_floating.yaml`** - Floating rules
- **`nat_outbound.yaml`** - NAT outbound rules (IPv4/IPv6)

### Services
- **`dhcp.yaml`** - DHCP server configurations with static reservations
- **`openvpn_clients.yaml`** - OpenVPN client configurations

## Output Structure

```
opnsense-config/
├── README.md                          # Summary and usage instructions
└── opnsense/
    ├── system.yaml                    # System settings
    ├── interfaces.yaml                # Network interfaces
    ├── vlans.yaml                     # VLAN definitions
    ├── gateways.yaml                  # Gateway configurations
    ├── aliases.yaml                   # Firewall aliases
    ├── dhcp.yaml                      # DHCP servers
    ├── nat_outbound.yaml              # NAT rules
    ├── openvpn_clients.yaml           # VPN clients
    ├── firewall_rules_lan.yaml        # LAN rules
    ├── firewall_rules_wan.yaml        # WAN rules
    ├── firewall_rules_opt1.yaml       # OPT1 rules
    ├── firewall_rules_opt2.yaml       # OPT2 rules
    └── firewall_rules_floating.yaml   # Floating rules
```

## Configuration Coverage

### ✅ Fully Supported

- System hostname, domain, timezone
- DNS servers
- Network interfaces (physical and VLAN)
- VLANs
- Gateways (static and dynamic)
- Firewall aliases (host, network, port)
- Firewall rules (all interfaces)
- NAT outbound rules
- DHCP servers with static mappings
- OpenVPN clients
- SSH and WebGUI settings

### ⚠️ Not Included (Security/Manual Configuration)

- User accounts and passwords
- SSL certificates and private keys
- OpenVPN authentication credentials (marked as REDACTED)
- WireGuard configurations
- NAT port forwarding rules
- Plugin/package installations
- Traffic shaping rules
- Captive portal settings

## Use Cases

### 1. Documentation and Audit

Generate human-readable documentation of your firewall configuration:

```bash
python tools/opnsense-parser.py config.xml -o firewall-docs
cd firewall-docs
git init
git add .
git commit -m "Document firewall configuration as of $(date +%Y-%m-%d)"
```

### 2. Version Control

Track changes to your OPNsense configuration over time:

```bash
# Export configuration weekly
python tools/opnsense-parser.py \
  /path/to/latest-backup.xml \
  -o ~/firewall-configs/$(date +%Y-%m-%d)

# Diff changes
diff -r firewall-configs/2025-11-01 firewall-configs/2025-11-07
```

### 3. Disaster Recovery

Rebuild your OPNsense from scratch:

1. Export configuration: `python tools/opnsense-parser.py config.xml`
2. Store YAML files in secure location
3. If disaster strikes:
   - Install fresh OPNsense
   - Use YAML files as reference to manually recreate configuration
   - Or wait for InfraFoundry OPNsense provider (future)

### 4. Migration Between Instances

Transfer configuration to new hardware:

```bash
# Export from old firewall
python tools/opnsense-parser.py old-firewall-config.xml -o migration

# Review and adjust for new hardware
vim migration/opnsense/interfaces.yaml  # Update interface names

# Use as reference for new firewall setup
```

### 5. Multi-Site Management

Manage multiple OPNsense firewalls:

```bash
# Parse each site's configuration
python tools/opnsense-parser.py site-a.xml -o configs/site-a
python tools/opnsense-parser.py site-b.xml -o configs/site-b
python tools/opnsense-parser.py site-c.xml -o configs/site-c

# Compare configurations
diff configs/site-a/opnsense/firewall_rules_lan.yaml \
     configs/site-b/opnsense/firewall_rules_lan.yaml
```

## Workflow with InfraFoundry

Once the OPNsense provider is implemented for InfraFoundry:

```bash
# 1. Export configuration
python tools/opnsense-parser.py config.xml -o temp-export

# 2. Copy to your InfraFoundry config repo
cp -r temp-export/opnsense $INFRAFOUNDRY_CONFIG_REPO/envs/prod/

# 3. Add sensitive data (VPN credentials, etc.)
cat > $INFRAFOUNDRY_CONFIG_REPO/secrets/opnsense.yaml <<EOF
openvpn:
  nordvpn_username: "your-username"
  nordvpn_password: "your-password"
EOF

# 4. Encrypt secrets
infra secrets encrypt secrets/opnsense.yaml

# 5. Update environment
vim $INFRAFOUNDRY_CONFIG_REPO/envs/prod/environment.yaml
# Add:
# providers:
#   - opnsense

# 6. Generate and apply
infra plan --env prod
infra apply --env prod
```

## Exporting Configuration from OPNsense

### Via WebGUI

1. Log into OPNsense WebGUI
2. Navigate to: **System → Configuration → Backups**
3. Click **Download configuration**
4. Save the `config-*.xml` file
5. Parse it: `python tools/opnsense-parser.py config-*.xml`

### Via Command Line (SSH)

```bash
# SSH to OPNsense
ssh root@opnsense.local

# Copy config to home directory
cp /conf/config.xml ~/config-backup-$(date +%Y%m%d).xml

# Exit and SCP to local machine
exit
scp root@opnsense.local:~/config-backup-*.xml ./
```

### Automated Backups

Set up automated parsing in a cron job:

```bash
#!/bin/bash
# backup-opnsense.sh

DATE=$(date +%Y-%m-%d)
BACKUP_DIR=~/opnsense-backups

# Download latest backup from OPNsense
scp root@opnsense.local:/conf/config.xml $BACKUP_DIR/config-$DATE.xml

# Parse to YAML
cd /path/to/infrafoundry
python tools/opnsense-parser.py $BACKUP_DIR/config-$DATE.xml \
  -o $BACKUP_DIR/parsed-$DATE

# Commit to git
cd $BACKUP_DIR
git add .
git commit -m "OPNsense backup $DATE" || true
git push
```

## Limitations

### Not Extracted

The parser does **not** currently extract:

- **NAT Port Forward** - Inbound port forwarding rules
- **VPN Server** - OpenVPN/WireGuard server configurations
- **Traffic Shaping** - Bandwidth management rules
- **Users/Groups** - User accounts (security sensitive)
- **Certificates** - SSL/TLS certificates and keys (security sensitive)
- **High Availability** - CARP/pfsync settings
- **Plugins** - Third-party plugin configurations
- **Captive Portal** - Guest portal settings
- **Dynamic DNS** - DDNS providers and credentials
- **System Tunables** - sysctl values

These can be added in future versions if needed.

### Security Considerations

The parser intentionally **redacts** security-sensitive information:

- ✅ **Safe to commit**: All exported YAML files
- ⚠️ **Manual entry required**: VPN passwords, API keys, certificate private keys

**Best Practice**: Store the original XML backup securely (encrypted) and only commit the sanitized YAML files to version control.

## Troubleshooting

### Error: "Config file not found"

```bash
# Check file path
ls -l /path/to/config.xml

# Use absolute path
python tools/opnsense-parser.py "$(pwd)/config.xml"
```

### Output directory already exists

```bash
# Remove old output
rm -rf opnsense-config

# Or use different directory
python tools/opnsense-parser.py config.xml -o opnsense-config-new
```

### Missing configuration sections

Some sections might be empty if not configured in OPNsense:

```yaml
# Empty dhcp.yaml if no DHCP servers configured
dhcp_servers: []

# No openvpn_clients.yaml file if no VPN clients
```

This is expected and not an error.

## Future Enhancements

Planned features:

- [ ] Extract NAT port forward rules
- [ ] Extract VPN server configurations (OpenVPN/WireGuard)
- [ ] Extract traffic shaping rules
- [ ] Extract High Availability (CARP) settings
- [ ] Extract certificate information (without private keys)
- [ ] Support for pfSense XML format
- [ ] Diff tool to compare two configurations
- [ ] Validation against OPNsense schema

## Contributing

To add support for additional configuration sections:

1. Add parsing method to `OPNsenseParser` class
2. Call from `generate_infrafoundry_configs()`
3. Write output YAML file
4. Update documentation
5. Submit pull request

## Related Documentation

- [InfraFoundry Setup Guide](../SETUP_GUIDE.md)
- [Ansible Integration](../ansible-integration.md)
- [Separate Config Repository Pattern](../separate-config-repo.md)

## Examples

See `example-config/envs/dev/opnsense/` for example output structure.

## License

Same as InfraFoundry project (MIT).
