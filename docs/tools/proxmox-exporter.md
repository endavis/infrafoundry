# Proxmox Config Exporter

## Overview
The Proxmox Config Exporter allows you to extract existing Proxmox cluster configurations and convert them into InfraFoundry-compatible YAML definitions. This facilitates importing existing infrastructure into management.

## Usage

```bash
foundry config export --env prod --output ./envs/imported --provider proxmox
```

## Features
- Exports VMs, LXC containers, and storage configurations.
- Generates YAML files compatible with InfraFoundry's Proxmox provider.
- Filters by node or resource ID.
