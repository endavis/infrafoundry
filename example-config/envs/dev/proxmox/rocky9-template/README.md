# Rocky Linux 9 Cloud Image Template (Example)

Example package that consumes the `rocky9-template` blueprint to build a
Proxmox VM template from the Rocky Linux 9 GenericCloud qcow2 image.

The implementation (resource definitions, defaults, image URL, cloud-init
wiring) lives in the blueprint at `blueprints/rocky9-template/`. See
[`blueprints/rocky9-template/README.md`](../../../../../blueprints/rocky9-template/README.md)
for the full variable reference and details about what gets deployed.

## Quick Start

```bash
# Create the template
infra apply --env dev --package rocky9-template

# Destroy the template
infra destroy --env dev --package rocky9-template
```

## What This Example Sets

This example overrides only the three per-instance values the blueprint
requires. Everything else (cores, memory, disk size, image URL, etc.) is
inherited from the blueprint defaults.

| Variable | Value |
|---|---|
| `vmid` | `901` |
| `target_node` | `pve1` |
| `storage` | `local-lvm` |

To customise any other field (e.g. `cores`, `memory`, `disk_size`, `bridge`),
add it under `variables:` in `infrafoundry.yml`. The full list of overridable
fields is documented in the blueprint README.

## Package Structure

```
rocky9-template/
  infrafoundry.yml    # Thin blueprint instantiation — edit this
  README.md           # This file
```

The resource definitions live in `blueprints/rocky9-template/vm.yaml`, not
in this directory.
