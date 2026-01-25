# InfraFoundry Tools

This directory contains utility tools for InfraFoundry and infrastructure automation.

**Full documentation:** [docs/tools/README.md](../docs/tools/README.md)

## Available Tools

| Tool | Description | Documentation |
|------|-------------|---------------|
| `opnsense-parser.py` | Parse OPNsense config.xml into YAML | [docs/tools/opnsense-parser.md](../docs/tools/opnsense-parser.md) |
| Config Diff | Compare configurations between environments | [docs/tools/config-diff.md](../docs/tools/config-diff.md) |
| Dependency Analysis | Analyze resource dependencies | [docs/tools/dependency-analysis.md](../docs/tools/dependency-analysis.md) |
| Proxmox Exporter | Export Proxmox infrastructure to YAML | [docs/tools/proxmox-exporter.md](../docs/tools/proxmox-exporter.md) |

## Quick Start

```bash
# OPNsense parser
python tools/opnsense-parser.py config.xml
```

## Contributing

To add a new tool:
1. Create the tool in `tools/`
2. Add documentation in `docs/tools/`
3. Update `docs/tools/README.md`
