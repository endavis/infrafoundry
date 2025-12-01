# OPNsense Configuration Parser

## Overview

`tools/opnsense-parser.py` converts OPNsense `config.xml` backups into organized YAML suitable for InfraFoundry (or other IaC) to enable documentation, version control, migration, and recovery.

## Audience and Prerequisites

- **Audience:** Operators exporting or migrating OPNsense configurations.
- **Prereqs:** Python (bundled with InfraFoundry tooling) and access to OPNsense `config.xml` backups.

## When to Use This

- Documenting firewall configs in readable YAML.
- Seeding InfraFoundry resources from existing OPNsense setups.
- Migrating between OPNsense instances or repos.

## Quick Start

```bash
python tools/opnsense-parser.py <config.xml> [-o output_directory]
```

Examples:
```bash
python tools/opnsense-parser.py ~/Downloads/config-OPNsense.xml
python tools/opnsense-parser.py config.xml -o $INFRAFOUNDRY_CONFIG_REPO/envs/prod/opnsense
```

## Configuration Details

- **Outputs:** Structured YAML per area (system, interfaces, VLANs, gateways, aliases, firewall rules, NAT outbound, DHCP, OpenVPN clients).
- **Default output dir:** `opnsense-config/` (overridden by `-o`).
- **Security:** Credentials/certs are not exported; sensitive fields are omitted/redacted.

## Validation and Checks

- Inspect generated YAML for completeness; sensitive data must be added manually where required.
- Confirm target directory is git-ignored if it contains environment-specific data.

## Examples

- **Output layout:**
  ```
  opnsense-config/
  └── opnsense/
      interfaces.yaml
      vlans.yaml
      gateways.yaml
      aliases.yaml
      firewall_rules_lan.yaml
      firewall_rules_wan.yaml
      firewall_rules_floating.yaml
      dhcp.yaml
      nat_outbound.yaml
      openvpn_clients.yaml
  ```
- **Use in config repo:** Place generated files under `envs/{env}/opnsense/` or `envs/{env}/resources/` and adapt to InfraFoundry resource schemas.

## Related Documentation

- [Configuration Guide](../configuration.md)
- [YAML-Only Configuration](../yaml-only-config.md)
- [Validation and Pre-Flight Checks](../validation.md)

## Troubleshooting

- **Symptom:** Missing secrets/certs. **Fix:** Add manually; parser intentionally skips sensitive material.
- **Symptom:** Wrong output path. **Fix:** Use `-o` to target the desired directory.
- **Symptom:** Unsupported sections needed. **Fix:** Extend parser or manually create YAML to cover remaining settings.

---

Last updated: 2025-11-29 14:27 GMT
