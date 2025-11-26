# Validation and Pre-Flight Checks

## Overview

InfraFoundry provides comprehensive validation to catch errors **before** running `terraform apply`. This prevents wasted time and potential infrastructure issues.

## Validation Command

```bash
infra validate --env dev [OPTIONS]
```

### Options

- `--check-api` - Verify connectivity and credentials to provider APIs
- `--check-refs` - Validate that referenced resources exist (templates, networks, aliases)

### Validation Levels

Checks are categorized by severity:

- **ERROR** 🔴 - Blocks deployment, must be fixed
- **WARNING** ⚠️ - Should be reviewed but won't block deployment
- **INFO** ℹ️ - Informational only

## What Gets Validated

### Always Checked (No Flags)

1. **YAML Syntax** - Configuration files are valid YAML
2. **Environment Structure** - Required files exist (`settings.yaml`, resource files)
3. **Resource Types** - All resources use supported provider types
4. **Provider Registration** - Providers are available for all resources
5. **Configuration Completeness** - Required fields are present

### With `--check-api`

Validates connectivity and credentials to provider APIs:

**Proxmox:**
- API endpoint reachable
- API token valid
- Node accessible

**OPNsense:**
- API endpoint reachable
- API credentials valid (key + secret)
- Firewall responsive

**Kubernetes:**
- Kubeconfig valid
- Cluster reachable
- Namespace exists

### With `--check-refs`

Validates that referenced resources actually exist:

**Proxmox:**
- VM templates exist on target node
- Networks/bridges are available
- Storage pools exist

**OPNsense:**
- Aliases referenced in firewall rules exist
- VLANs referenced in DHCP maps exist
- Interfaces are valid

**Kubernetes:**
- Namespaces exist
- ConfigMaps/Secrets referenced exist

## Usage Examples

### Basic Validation

```bash
# Quick validation (YAML syntax, resource types)
infra validate --env dev

# Example output:
# ✓ Loaded environment configuration
# ✓ Found 15 resource(s)
# ✓ All resources have registered providers
#
# Validating proxmox: 10 resource(s)
# Validating opnsense: 5 resource(s)
#
# Validation Report:
#   Total checks: 3
#   ✓ Passed: 3
#
# ✅ Validation passed successfully
```

### Pre-Deployment Validation

```bash
# Full validation before terraform apply
infra validate --env prod --check-api --check-refs

# Example output with issues:
# ✓ Loaded environment configuration
# ✓ Found 25 resource(s)
# ✓ All resources have registered providers
#
# Validating proxmox: 15 resource(s)
#   Checking API connectivity...
#   Validating resource references...
#
# Validating opnsense: 10 resource(s)
#   Checking API connectivity...
#   Validating resource references...
#
# Validation Report:
#   Total checks: 12
#   ✓ Passed: 10
#   ✗ Errors: 2
#
# Details:
#   [INFO] ✓ proxmox_connectivity: Successfully connected to Proxmox at https://pve01.example.com:8006
#   [ERROR] ✗ proxmox_template_ubuntu-22.04: Template 'ubuntu-22.04' not found on node pve01
#   [INFO] ✓ opnsense_connectivity: Successfully connected to OPNsense at https://fw.example.com
#   [ERROR] ✗ firewall_rule_allow_web_source_alias: Firewall rule 'allow-web' references undefined source alias 'WEB_SERVERS'
#   ...
#
# ❌ Validation failed with errors
```

## Validation in CI/CD

### GitHub Actions

```yaml
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Validate infrastructure
        run: |
          infra validate --env prod --check-api --check-refs

      - name: Apply if validation passes
        if: success()
        run: |
          infra apply --env prod --auto-approve
```

### GitLab CI

```yaml
validate:
  stage: validate
  script:
    - infra validate --env $CI_ENVIRONMENT_NAME --check-api --check-refs

deploy:
  stage: deploy
  dependencies:
    - validate
  script:
    - infra apply --env $CI_ENVIRONMENT_NAME --auto-approve
  when: manual
```

## Implementing Custom Validators

Providers can implement optional validation methods:

### API Connectivity Check

```python
class MyProvider(ProviderBase):
    def validate_connectivity(
        self, env_config: dict[str, Any], report: ValidationReport
    ) -> None:
        """Check API connectivity."""
        api_url = env_config.get("provider_settings", {}).get("myprovider", {}).get("api_url")

        try:
            response = requests.get(f"{api_url}/health")
            if response.status_code == 200:
                report.add_check(
                    check_name="myprovider_connectivity",
                    passed=True,
                    message=f"Connected to {api_url}",
                    level=ValidationLevel.INFO,
                )
            else:
                report.add_check(
                    check_name="myprovider_connectivity",
                    passed=False,
                    message=f"API returned {response.status_code}",
                    level=ValidationLevel.ERROR,
                )
        except Exception as e:
            report.add_check(
                check_name="myprovider_connectivity",
                passed=False,
                message=f"Connection failed: {e}",
                level=ValidationLevel.ERROR,
            )
```

### Reference Validation

```python
def validate_references(
    self, resources: list[ResourceConfig], env_config: dict[str, Any], report: ValidationReport
) -> None:
    """Validate resource references."""
    # Check that templates exist
    for resource in resources:
        if resource.type == "vm":
            template = resource.config.get("template")
            if template and not self._template_exists(template):
                report.add_check(
                    check_name=f"vm_{resource.name}_template",
                    passed=False,
                    message=f"Template '{template}' not found",
                    level=ValidationLevel.ERROR,
                    details={"resource": resource.name, "template": template},
                )
```

## Benefits

### Catch Errors Early

- ❌ **Without validation**: Deploy fails 10 minutes into terraform apply
- ✅ **With validation**: Fail in 10 seconds, before any infrastructure changes

### Prevent Common Issues

- Invalid API credentials
- Missing templates/images
- Undefined resource references
- Network/storage unavailable
- Quota limits exceeded

### Improve CI/CD Reliability

- Validate before deployment in pipelines
- Fast-fail on configuration errors
- Clear error messages for debugging
- Automated checks in pull requests

## Related Documentation

- [Settings File Structure](settings-file-structure.md) - Configuration format
- [Provider Development](plugin-development.md) - Implementing validators
- [CI/CD Integration](ci-cd-testing.md) - Pipeline examples
