# Plugin Development Guide

## Overview

Provider plugins implement `ProviderBase`, render Terraform/Ansible via Jinja2, validate configs, and declare resource types/dependencies. Use the 3-layer pattern (Provider → Component Manager → Service) for complex flows.

## Audience and Prerequisites

- **Audience:** Contributors building or extending providers.
- **Prereqs:** Python familiarity, Jinja2 templates, and knowledge of the target platform’s APIs.

## When to Use This

- Adding a new provider.
- Extending provider resource types or templates.
- Applying the 3-layer architecture for complex API interactions.

## Quick Start

1. Create `src/infrafoundry/providers/<provider>/__init__.py` extending `ProviderBase`.
2. Add Terraform/Ansible templates under `templates/<provider>/`.
3. Implement validation, generation, and resource declarations.

## Architecture Details

- **ProviderBase responsibilities:** set `name`, configure template dirs/env, validate configs, generate Terraform/Ansible, expose `get_resource_types()` and `get_dependencies()`.
- **Environment setup:** **CRITICAL** - Call `set_environment(env_name)` before any `generate_*()` methods to configure environment-specific output directories. Orchestrator handles this automatically, but direct provider usage requires manual invocation.
- **Templates:** Use Jinja2; leverage mixins (`TemplateRendererMixin`) to render and group resources; output to `generated/{env}/{terraform|ansible}/{provider}/`.
- **3-layer stack:** Provider (orchestration) → Component Manager (complex workflows) → Service (API layer).
- **Dependencies:** `get_dependencies()` returns ordering (e.g., servers depend on networks).
- **Backward compatibility:** Re-export public APIs in `__init__.py`; keep provider module imports stable.

## Validation and Checks

- Validate required fields per resource type; surface clear errors.
- Ensure templates produce deterministic output; keep secrets out of generated files.
- Run `foundry infra doctor --env <env>` for new providers; add provider-specific validators as needed.

## Environment Configuration

**The `set_environment()` method must be called before any generate methods:**

```python
def set_environment(self, env_name: str) -> None:
    """Set the current environment and update output directories.

    This should be called before generate_terraform(), generate_ansible(),
    or generate_pyinfra() to ensure files are generated in the correct
    environment-specific directory.

    Args:
        env_name: Environment name (e.g., 'dev', 'staging', 'prod')
    """
```

**What it does:**
- Sets `self._current_environment = env_name`
- Updates `self.output_dir = base_output_dir / env_name`
- Updates `self.terraform_dir = output_dir / "terraform" / provider_name`
- Updates `self.ansible_dir = output_dir / "ansible" / provider_name`
- Updates `self.pyinfra_dir = output_dir / "pyinfra" / provider_name`

**When to call:**
- **Orchestrator usage:** Called automatically by the orchestrator
- **Direct provider usage:** Must be called manually before generate methods
- **Testing:** Always call in test setup before generating files

## Optional Provider Methods

Providers can override these optional methods to add advanced functionality:

### validate_connectivity()

**Purpose:** Validate connectivity to provider API and verify credentials.

```python
def validate_connectivity(
    self, env_config: EnvironmentConfig, report: ValidationReport
) -> None:
    """Validate connectivity to provider API.

    Optional method for providers to implement API connectivity checks.
    Should add results to the validation report.

    Args:
        env_config: Environment configuration including credentials
        report: ValidationReport to add results to
    """
    # Default: no connectivity validation
    return None
```

**When to implement:**
- Provider has an API that can be pinged/tested
- Credentials can be validated before deployment
- Network connectivity needs verification

**Example implementation:**
```python
def validate_connectivity(self, env_config, report):
    try:
        # Test API connection
        response = self.api_client.ping()
        if response.status_code == 200:
            report.add_success(f"{self.name}: API connectivity verified")
        else:
            report.add_error(f"{self.name}: API returned {response.status_code}")
    except Exception as e:
        report.add_error(f"{self.name}: Connection failed - {e}")
```

**Usage:** Called by `foundry infra doctor --env <env>`

---

### validate_references()

**Purpose:** Validate that resources referenced in configs actually exist in the provider.

```python
def validate_references(
    self,
    resources: list[ResourceConfig],
    env_config: EnvironmentConfig,
    report: ValidationReport
) -> None:
    """Validate that referenced resources exist in the provider.

    Optional method for providers to check that templates, networks,
    aliases, etc. referenced in configs actually exist.

    Args:
        resources: Resources to validate
        env_config: Environment configuration including credentials
        report: ValidationReport to add results to
    """
    # Default: no reference validation
    return None
```

**When to implement:**
- Resources reference templates, images, or base configs
- Resources reference networks, storage pools, or other infrastructure
- Want to catch missing references before deployment

**Example implementation:**
```python
def validate_references(self, resources, env_config, report):
    for resource in resources:
        # Check if referenced template exists
        if template_id := resource.config.get('template'):
            if not self.api_client.template_exists(template_id):
                report.add_error(
                    f"{resource.name}: Template '{template_id}' not found"
                )

        # Check if referenced network exists
        if network := resource.config.get('network'):
            if not self.api_client.network_exists(network):
                report.add_error(
                    f"{resource.name}: Network '{network}' not found"
                )
```

**Usage:** Called by `foundry infra doctor --env <env>`

---

### generate_pyinfra()

**Purpose:** Generate PyInfra deployment scripts and inventory.

```python
def generate_pyinfra(self, resources: list[ResourceConfig]) -> None:
    """Generate pyinfra deploy scripts and inventory.

    Optional method. Providers can override this to support pyinfra.

    Args:
        resources: List of resources to generate pyinfra for
    """
    return
```

**When to implement:**
- Provider wants to support PyInfra in addition to Terraform/Ansible
- Resources have pyinfra_ops or pyinfra_deploy_funcs configurations
- Want to use PyInfra for configuration management

**Example implementation:**
```python
def generate_pyinfra(self, resources):
    # Filter resources with PyInfra configs
    pyinfra_resources = [
        r for r in resources
        if r.config.get('pyinfra_ops') or r.config.get('pyinfra_deploy_funcs')
    ]

    if not pyinfra_resources:
        return

    self.ensure_directories()

    # Render deploy.py
    self.render_template(
        "deploy.py.j2",
        self.pyinfra_dir / "deploy.py",
        {"resources": pyinfra_resources}
    )

    # Render inventory.py
    self.render_template(
        "inventory.py.j2",
        self.pyinfra_dir / "inventory.py",
        {"resources": pyinfra_resources}
    )
```

**Usage:** Called automatically by orchestrator if provider implements this method and resources have pyinfra configurations.

**Template requirements:**
- `templates/<provider>/deploy.py.j2` - PyInfra deployment script
- `templates/<provider>/inventory.py.j2` - PyInfra inventory

## Examples

- **Provider skeleton:**
  ```python
  class YourProvider(ProviderBase):
      def __init__(self, config_dir: Path, output_dir: Path) -> None:
          super().__init__("yourprovider", config_dir, output_dir)
          self.template_dir = Path(__file__).parent / "templates"

      def get_resource_types(self) -> list[str]:
          return ["servers", "networks"]

      def get_dependencies(self) -> dict[str, list[str]]:
          return {"servers": ["networks"], "networks": []}

      def validate_config(self, config: dict[str, Any]) -> bool:
          return all(key in config for key in ["name", "type"])

      def generate_terraform(self, resources: list[ResourceConfig]) -> None:
          self.ensure_directories()
          # render templates ...

  # Usage example:
  provider = YourProvider(config_dir, output_dir)

  # CRITICAL: Set environment before generating files
  provider.set_environment("dev")

  # Now safe to generate - files will go to generated/dev/terraform/yourprovider/
  provider.generate_terraform(resources)
  ```
- **Template snippet (provider.tf.j2):**
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

## Validator Architecture

All providers use a **composition pattern** for validation: a main validator composes `BaseAPIValidator` (for credential checking and reporting) and delegates to specialized validators for specific checks.

### Main Validator Pattern

```python
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.yourprovider.api_client import YourClient

class YourValidator:
    def __init__(self, env_config, report):
        self.env_config = env_config
        self.report = report
        self.api_validator = BaseAPIValidator("yourprovider", env_config, report)
        self.provider_settings = self.api_validator.provider_settings

        # Compose specialized validators
        self.network_validator = NetworkValidator(report)
        self.resource_validator = ResourceValidator(report)
```

### validate_connectivity() Pattern

Credential checking uses `api_validator.get_credentials()`. API calls use a dedicated client:

```python
def validate_connectivity(self):
    credentials = self.api_validator.get_credentials(
        required_fields=["api_url", "api_key"]
    )
    if not credentials:
        return

    client = YourClient.from_provider_settings(self.provider_settings)
    if not client:
        self.api_validator.add_error(
            check_name="yourprovider_credentials",
            message="Missing API credentials",
        )
        return

    try:
        data = client.get_json("status")
        self.api_validator.add_success(
            check_name="yourprovider_connectivity",
            message=f"Connected (version: {data.get('version')})",
        )
    except APIError as exc:
        self.api_validator.add_error(
            check_name="yourprovider_connectivity",
            message=f"Connection failed: {exc.message}",
        )
```

### validate_references() Pattern

Collect references from resources, fetch live state, delegate to specialized validators:

```python
def validate_references(self, resources):
    client = YourClient.from_provider_settings(self.provider_settings)
    if not client:
        return

    try:
        refs = self._collect_resource_references(resources)
        live_data = client.get_json("resources")

        self.network_validator.validate(client, refs.networks)
        self.resource_validator.validate(live_data, refs.resource_refs)

    except Exception as exc:
        self.api_validator.handle_validation_exception(
            check_name="yourprovider_validation",
            error=exc,
            warning_level=ValidationLevel.WARNING,
        )
```

### Specialized Validator Types

1. **API-calling validators** take a client instance and make requests:
   ```python
   class NetworkValidator:
       def __init__(self, report):
           self.report = report

       def validate(self, client, networks):
           for network in networks:
               try:
                   data = client.get_json(f"networks/{network}")
                   self.report.add_check(
                       check_name=f"network_{network}",
                       passed=True,
                       message=f"Network '{network}' exists",
                   )
               except APIError:
                   self.report.add_check(
                       check_name=f"network_{network}",
                       passed=False,
                       message=f"Network '{network}' not accessible",
                       level=ValidationLevel.WARNING,
                   )
   ```

2. **Report-only validators** receive pre-fetched data (no client needed):
   ```python
   class TemplateValidator:
       def __init__(self, report):
           self.report = report

       def validate(self, existing_templates, template_refs):
           if existing_templates is None:
               return  # API fetch failed, skip gracefully
           for ref, users in template_refs.items():
               if ref in existing_templates:
                   self.report.add_check(...)
   ```

### Graceful Degradation

API validation should never block deployment. Use `optional=True` and `ValidationLevel.WARNING` for non-critical API checks. If signing/authentication fails, skip API checks and run only local cross-reference validation.

## API Client Pattern

Providers with HTTP APIs should have a dedicated API client in `api_client.py`. Clients handle authentication and HTTP, raise exceptions on failure, and have no knowledge of validation reporting.

### Client Structure

```python
from infrafoundry.core.exceptions import APIError, AuthenticationError

class YourClient:
    def __init__(self, api_url, api_key, timeout=10):
        self.api_url = api_url
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout = timeout

    @classmethod
    def from_provider_settings(cls, settings):
        """Create client from provider settings. Returns None if insufficient."""
        api_url = settings.get("api_url")
        api_key = settings.get("api_key")
        if not api_url or not api_key:
            return None
        return cls(api_url=api_url, api_key=api_key)

    def get_json(self, endpoint, **kwargs):
        """GET endpoint and parse JSON. Raises APIError."""
        url = f"{self.api_url}/{endpoint}"
        try:
            response = requests.get(
                url, headers=self.headers, timeout=self.timeout, **kwargs
            )
        except requests.exceptions.RequestException as e:
            raise APIError(f"Request failed: {e}", provider="yourprovider") from e

        if response.status_code in (401, 403):
            raise AuthenticationError(
                "Authentication failed",
                status_code=response.status_code,
                provider="yourprovider",
            )
        if not response.ok:
            raise APIError(
                f"Request failed: {response.status_code}",
                status_code=response.status_code,
                provider="yourprovider",
            )
        return response.json()
```

### Error Handling Convention

| Exception | When |
|-----------|------|
| `AuthenticationError` | HTTP 401/403 |
| `APIError` | Other HTTP errors, connection errors, timeouts, JSON parse failures |
| `ConfigurationError` | Missing key files, invalid credentials format (at client construction) |

Validators catch these exceptions and report them via `ValidationReport`.

### Existing Clients

- `providers/opnsense/api_client.py` — `OPNsenseClient` (wraps httpx via opnsense-openapi) + `KeaClient` (domain-specific DHCP operations)
- `providers/proxmox/api_client.py` — `ProxmoxClient` (PVE token auth, `get_json()`)
- `providers/oci/api_client.py` — `OCIClient` (RSA-SHA256 HTTP Signature auth, `list_resources()`)

## Provider Mixins

Mixins provide reusable functionality via composition. Import from `infrafoundry.core.provider_mixins`.

| Mixin | Purpose | Used By |
|-------|---------|---------|
| `TemplateRendererMixin` | Jinja2 template setup and rendering | All providers |
| `ResourceGrouperMixin` | Group resources by type or dependency | Most providers |
| `TerraformGeneratorMixin` | Generate `.tf` files and `.tfvars` | All Terraform providers |
| `CloudInitMixin` | Load, merge, and variable-substitute cloud-init snippets | Proxmox, OCI |

### Using CloudInitMixin

```python
from infrafoundry.core.provider_mixins import CloudInitMixin

class YourProvider(ProviderBase, CloudInitMixin):
    def _process_cloud_init(self, config):
        merged = self._merge_cloud_init_snippets(config)
        if merged:
            # Proxmox serializes to YAML, OCI stores as dict
            config["cloud_init_data"] = yaml.dump(merged)
```

Cloud-init snippets are loaded from `envs/{env}/cloud-init/` and support variable substitution via `cloud_init_vars` in the resource config.

## New Provider Checklist

### Required Files

| File | Purpose |
|------|---------|
| `providers/<name>/__init__.py` | Provider class extending `ProviderBase` |
| `providers/<name>/templates/` | Jinja2 templates for Terraform/Ansible |

### Recommended Files (for API-backed providers)

| File | Purpose |
|------|---------|
| `providers/<name>/api_client.py` | Dedicated API client with auth |
| `providers/<name>/validator.py` | Main validator composing `BaseAPIValidator` |
| `providers/<name>/validators/__init__.py` | Specialized validator package |
| `providers/<name>/validators/*.py` | Individual validators (network, storage, etc.) |
| `providers/<name>/exporter.py` | Resource exporter (if applicable) |

### Required Methods

- [ ] `__init__(config_dir, output_dir)` — call `super().__init__("name", ...)`
- [ ] `get_resource_types()` — return list of supported resource type names
- [ ] `get_dependencies()` — return dependency ordering dict
- [ ] `validate_config(config)` — validate resource configuration
- [ ] `generate_terraform(resources)` — render Terraform files

### Recommended Methods

- [ ] `validate_connectivity(env_config, report)` — test API connectivity
- [ ] `validate_references(resources, env_config, report)` — validate resource cross-references
- [ ] `generate_ansible(resources)` — render Ansible playbooks (if applicable)

### Testing Requirements

- [ ] Unit tests for API client (`test_api_client.py`)
- [ ] Unit tests for each specialized validator
- [ ] Unit tests for main validator orchestration
- [ ] Integration test in `tests/unit/test_provider_validation.py`
- [ ] All tests pass: `doit check`

### Registration

Providers are auto-discovered via the plugin system. Ensure the provider module is properly structured with an `__init__.py` that exports the provider class.

## Related Documentation

- [Manager Patterns](manager-patterns.md)
- [Architectural Patterns](../architecture/architectural-patterns.md)
- [Pluggable Runners](../architecture/pluggable-runners.md)
- [Implementing Secret Providers](implementing-secret-providers.md)
- [ISC to Kea Migration (example)](../guides/isc-to-kea-migration.md)

## Troubleshooting

- **Symptom:** Resources out of order. **Fix:** Update `get_dependencies()` and verify resource references.
- **Symptom:** Templates fail to render. **Fix:** Check template paths and Jinja2 variables; use mixins for consistent filters.
- **Symptom:** New provider not discovered. **Fix:** Ensure it is registered and exposed via `__init__.py`.
- **Symptom:** Generated files appear in wrong directory or base output dir. **Fix:** Ensure `set_environment(env_name)` is called before any `generate_*()` methods. The orchestrator calls this automatically, but direct provider usage requires manual invocation.

---

Last updated: 2026-04-03


---
[Back to Table of Contents](../index.md)
