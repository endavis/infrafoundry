# Plugin Development Guide

This guide explains how to create new provider plugins for InfraFoundry.

## Provider Plugin Architecture

Each provider is a Python module that:
1. Implements the `ProviderBase` abstract class
2. Contains Jinja2 templates for Terraform and Ansible generation
3. Validates resource configurations
4. Declares resource types and dependencies

## Step-by-Step: Creating a New Provider

### 1. Create Provider Module

Create `src/infrafoundry/providers/yourprovider/__init__.py`:

```python
"""Your Provider description."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from infrafoundry.core.provider import ProviderBase, ResourceConfig


class YourProvider(ProviderBase):
    """Provider for managing XYZ infrastructure."""

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize provider."""
        super().__init__("yourprovider", config_dir, output_dir)
        self.template_dir = Path(__file__).parent / "templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate configuration has required fields."""
        required_fields = ["name", "type"]
        return all(field in config for field in required_fields)

    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration files."""
        self.ensure_directories()

        # Group resources by type
        resources_by_type: dict[str, list[ResourceConfig]] = {}
        for resource in resources:
            if resource.type not in resources_by_type:
                resources_by_type[resource.type] = []
            resources_by_type[resource.type].append(resource)

        # Generate provider configuration
        provider_template = self.jinja_env.get_template("yourprovider/provider.tf.j2")
        provider_content = provider_template.render()
        (self.terraform_dir / "provider.tf").write_text(provider_content)

        # Generate variables
        variables_template = self.jinja_env.get_template("yourprovider/variables.tf.j2")
        variables_content = variables_template.render()
        (self.terraform_dir / "variables.tf").write_text(variables_content)

        # Generate resources by type
        if "servers" in resources_by_type:
            self._generate_servers_terraform(resources_by_type["servers"])

        # Generate outputs
        outputs_template = self.jinja_env.get_template("yourprovider/outputs.tf.j2")
        outputs_content = outputs_template.render(
            resources_by_type=resources_by_type,
        )
        (self.terraform_dir / "outputs.tf").write_text(outputs_content)

    def _generate_servers_terraform(self, servers: list[ResourceConfig]) -> None:
        """Generate Terraform for servers."""
        template = self.jinja_env.get_template("yourprovider/servers.tf.j2")
        content = template.render(servers=servers)
        (self.terraform_dir / "servers.tf").write_text(content)

    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks."""
        self.ensure_directories()

        # Generate main playbook
        playbook_template = self.jinja_env.get_template("yourprovider/playbook.yml.j2")
        playbook_content = playbook_template.render(resources=resources)
        (self.ansible_dir / "playbook.yml").write_text(playbook_content)

        # Generate inventory
        inventory_template = self.jinja_env.get_template("yourprovider/inventory.yml.j2")
        inventory_content = inventory_template.render(resources=resources)
        (self.ansible_dir / "inventory.yml").write_text(inventory_content)

    def get_resource_types(self) -> list[str]:
        """Get supported resource types."""
        return ["servers", "networks", "configs"]

    def get_dependencies(self) -> dict[str, list[str]]:
        """Define resource dependencies for proper ordering."""
        return {
            "servers": ["networks"],  # Servers depend on networks
            "networks": [],           # Networks have no dependencies
            "configs": ["servers"],   # Configs depend on servers
        }
```

### 2. Create Terraform Templates

Create templates in `src/infrafoundry/providers/yourprovider/templates/yourprovider/`:

**provider.tf.j2:**
```hcl
terraform {
  required_providers {
    yourprovider = {
      source  = "vendor/yourprovider"
      version = "~> 1.0"
    }
  }
}

provider "yourprovider" {
  api_url    = var.yourprovider_api_url
  api_key    = var.yourprovider_api_key
  api_secret = var.yourprovider_api_secret
}
```

**variables.tf.j2:**
```hcl
variable "yourprovider_api_url" {
  description = "API URL"
  type        = string
}

variable "yourprovider_api_key" {
  description = "API key"
  type        = string
  sensitive   = true
}

variable "yourprovider_api_secret" {
  description = "API secret"
  type        = string
  sensitive   = true
}
```

**servers.tf.j2:**
```hcl
{% for server in servers %}
resource "yourprovider_server" "{{ server.config.name | replace('-', '_') }}" {
  name   = "{{ server.config.name }}"
  type   = "{{ server.config.type }}"
  region = "{{ server.config.region | default('us-east') }}"

  {% if server.config.size is defined %}
  size   = "{{ server.config.size }}"
  {% endif %}

  {% if server.config.tags is defined %}
  tags = {
    {% for key, value in server.config.tags.items() %}
    "{{ key }}" = "{{ value }}"
    {% endfor %}
  }
  {% endif %}
}

{% endfor %}
```

**outputs.tf.j2:**
```hcl
{% if resources_by_type.get('servers') %}
output "servers" {
  description = "Created servers"
  value = {
    {% for server in resources_by_type['servers'] %}
    "{{ server.config.name }}" = yourprovider_server.{{ server.config.name | replace('-', '_') }}.id
    {% endfor %}
  }
}
{% endif %}
```

### 3. Create Ansible Templates

**playbook.yml.j2:**
```yaml
---
# YourProvider Ansible Playbook
- name: Configure resources
  hosts: yourprovider_servers
  become: true
  gather_facts: true

  tasks:
    - name: Install required packages
      package:
        name:
          - curl
          - wget
        state: present

    - name: Configure application
      template:
        src: app.conf.j2
        dest: /etc/app/config.conf
```

**inventory.yml.j2:**
```yaml
---
all:
  children:
    yourprovider_servers:
      hosts:
{% for resource in resources %}
{% if resource.type == 'servers' %}
        {{ resource.config.name }}:
          ansible_host: "{{ resource.config.ip }}"
          ansible_user: "{{ resource.config.ssh_user | default('root') }}"
{% endif %}
{% endfor %}
```

### 4. Register Provider in CLI

Edit `src/infrafoundry/cli.py` in the `_get_orchestrator()` function:

```python
# Add to _get_orchestrator() function
try:
    from infrafoundry.providers.yourprovider import YourProvider
    orchestrator.register_provider(
        YourProvider(
            config_dir=config_manager.base_dir,
            output_dir=Path(os.getenv("INFRAFOUNDRY_OUTPUT_DIR", "generated")),
        )
    )
except ImportError:
    pass
```

### 5. Create Example Configurations

Create `envs/dev/yourprovider/servers.yaml`:

```yaml
servers:
  - name: app-server-01
    type: application
    region: us-east
    size: medium
    ip: 192.168.1.10
    ssh_user: ubuntu
    tags:
      environment: dev
      application: webapp

  - name: db-server-01
    type: database
    region: us-east
    size: large
    ip: 192.168.1.11
    ssh_user: ubuntu
    tags:
      environment: dev
      application: database
```

### 6. Create Test Resources

Create test resource file `envs/dev/yourprovider/test.yaml`:

```yaml
test_resource:
  - name: test-01
    config:
      field1: value1
      field2: value2
```

**Note:** Providers are auto-discovered from resource files, no need to declare them in `settings.yaml`.
```

### 7. Add Credentials to .envrc.local

```bash
# .envrc.local
export YOURPROVIDER_API_URL=https://api.example.com
export YOURPROVIDER_API_KEY=your-key
export YOURPROVIDER_API_SECRET=your-secret
```

### 8. Create Encrypted Secrets

```bash
# Create secrets file
cat > secrets/yourprovider.yaml <<EOF
yourprovider_api_url: https://api.example.com
yourprovider_api_key: your-key-here
yourprovider_api_secret: your-secret-here
EOF

# Encrypt it
infra secrets encrypt secrets/yourprovider.yaml
```

## Testing Your Provider

```bash
# Verify provider is registered
infra envs

# Generate Terraform (dry-run)
infra plan --env dev --dry-run

# Generate Terraform files
infra plan --env dev

# Inspect generated files
ls -la generated/terraform/yourprovider/
cat generated/terraform/yourprovider/servers.tf

# Test Terraform
cd generated/terraform/yourprovider
terraform init
terraform validate
terraform plan

# Apply if everything looks good
cd ../../..
infra apply --env dev
```

## Best Practices

### Configuration Validation
- Validate required fields in `validate_config()`
- Use Pydantic models for complex validation
- Provide helpful error messages

### Template Organization
- One template file per resource type
- Keep templates simple and readable
- Use Jinja2 filters for transformations (e.g., `replace('-', '_')`)
- Add comments in generated files

### Resource Dependencies
- Declare dependencies in `get_dependencies()`
- Framework handles ordering automatically
- Example: networks before VMs, namespaces before deployments

### Error Handling
- Raise descriptive exceptions
- Check for missing templates
- Validate Jinja2 template syntax

### Testing
- Create example configs for all resource types
- Test with different configurations
- Verify generated Terraform is valid
- Test Ansible playbooks in isolation

## Advanced Features

### Custom Template Filters

Add custom Jinja2 filters:

```python
def __init__(self, config_dir: Path, output_dir: Path) -> None:
    super().__init__("yourprovider", config_dir, output_dir)
    self.template_dir = Path(__file__).parent / "templates"
    self.jinja_env = Environment(
        loader=FileSystemLoader(str(self.template_dir)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Add custom filter
    self.jinja_env.filters['to_label'] = lambda s: s.replace('_', '-').lower()
```

### Dynamic Secret Loading

```python
def generate_terraform(self, resources: list[ResourceConfig]) -> None:
    # Load provider-specific secrets
    from infrafoundry.core.secrets import SecretManager
    secrets = SecretManager()
    provider_secrets = secrets.decrypt_file(f"{self.name}.yaml")

    # Use in template rendering
    template.render(resources=resources, secrets=provider_secrets)
```

### Conditional Resource Generation

```python
def generate_terraform(self, resources: list[ResourceConfig]) -> None:
    self.ensure_directories()

    # Only generate if resources exist
    if not resources:
        self.console.print(f"[yellow]No {self.name} resources to generate[/yellow]")
        return

    # Group and generate...
```

## Troubleshooting

**Provider not found:**
- Check import in `cli.py`
- Verify module path
- Check for syntax errors: `python -c "from infrafoundry.providers.yourprovider import YourProvider"`

**Template not found:**
- Check template directory structure
- Verify `templates/yourprovider/` exists
- Check template filename matches `get_template()` call

**Generated Terraform invalid:**
- Run `terraform validate` in generated directory
- Check Jinja2 syntax (missing `{% endfor %}`, etc.)
- Verify variable interpolation `{{ }}` is correct

## Example Providers

Study existing providers for examples:
- `src/infrafoundry/providers/proxmox/` - VMs, templates, networks
- `src/infrafoundry/providers/opnsense/` - Firewall rules, VLANs, aliases
- `src/infrafoundry/providers/kubernetes/` - Deployments, services, configmaps

## Contributing Your Provider

1. Create provider following this guide
2. Add tests in `tests/providers/test_yourprovider.py`
3. Update `README.md` with provider description
4. Submit pull request with:
   - Provider implementation
   - Templates
   - Example configurations
   - Documentation
