# AIQUM (Active IQ Unified Manager) — Example

Example package consuming the `aiqum` blueprint. All deployment logic lives in
`blueprints/aiqum/`; this directory only supplies the per-instance values.

See `blueprints/aiqum/README.md` for the full variable reference, prerequisites,
automation flow, and firewall port table.

## Quick Start

```bash
# Deploy everything (VM, DHCP, AIQUM install, initial setup, cluster add)
foundry infra apply --env dev --package aiqum

# Destroy everything
foundry infra destroy --env dev --package aiqum
```

## What This Example Demonstrates

- Cloning the `rocky9-template` blueprint VM (`template_vmid: 901`)
- Placing the VM on `pve1` with `local-lvm` storage
- A static DHCP reservation at `192.168.1.50` on the `my-subnet` Kea subnet
- Running the post-deploy event handler against an example jumphost and
  ONTAP cluster (replace the placeholder hosts and `CHANGE_ME` secrets
  before applying)

## Per-Instance Overrides

`infrafoundry.yml` supplies only the per-instance values listed in
`blueprints/aiqum/README.md` under "Required". Everything else (VM hardware,
VLAN, AIQUM/SMTP/ONTAP usernames, SMTP port) is inherited from the blueprint
defaults.

## Cleanup Note

`gateway` and `dns_server` from the pre-blueprint version were removed during
the conversion — both were unused (no script, template, or resource referenced
them). DHCP networking is configured entirely via the `network/dhcp` cloud-init
snippet baked into the blueprint.
