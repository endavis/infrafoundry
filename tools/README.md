# InfraFoundry Tools

Utility tools for InfraFoundry and infrastructure automation.

## Available Tools

### OPNsense Configuration Parser

**Location:** `tools/opnsense-parser.py`

Parse OPNsense `config.xml` backup files into structured YAML configurations.

**Quick Start:**
```bash
python tools/opnsense-parser.py config.xml
```

**Features:**
- Extracts system settings, interfaces, VLANs, gateways
- Parses firewall rules and aliases
- Exports DHCP and OpenVPN configurations
- Generates clean, human-readable YAML files
- Perfect for documentation, version control, or disaster recovery

**Full Documentation:** [docs/tools/opnsense-parser.md](../docs/tools/opnsense-parser.md)

## Future Tools

Planned tools for the InfraFoundry ecosystem:

- **Proxmox Config Exporter** - Extract Proxmox cluster configuration
- **Config Diff Tool** - Compare configurations between environments
- **Resource Validator** - Validate YAML configs against provider schemas
- **Dependency Analyzer** - Visualize resource dependencies
- **Cost Calculator** - Estimate infrastructure costs

## Contributing

To add a new tool:

1. Create the tool in `tools/`
2. Add documentation in `docs/tools/`
3. Update this README
4. Add example usage to main README
5. Include tests if applicable

## Development Environment

For VS Code users, the workspace includes recommended extensions and debug configurations:

```bash
# Install recommended VS Code extensions
make setup-vscode
```

The workspace is configured with:
- Python debugging with proper path resolution
- Pytest integration for testing tools
- Code formatting (Black, Ruff)
- YAML/Terraform syntax highlighting

## Tool Requirements

- Keep tools self-contained and minimal dependencies
- Use standard library when possible
- Add proper argparse/click CLI interface
- Include `--help` output
- Generate clean, structured output (YAML/JSON preferred)
- Follow project code style (black, ruff)
