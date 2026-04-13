# Error Reference

InfraFoundry uses structured error codes to help you quickly identify and resolve issues. Each error code follows the format `IF-CATEGORY-NNN` where:

- `IF` - InfraFoundry prefix
- `CATEGORY` - Error category (CONFIG, PROVIDER, RUNNER, etc.)
- `NNN` - Numeric identifier within the category

## Quick Reference

| Category | Description |
|----------|-------------|
| [CONFIG](#configuration-errors-if-config) | Configuration and environment errors |
| [PROVIDER](#provider-errors-if-provider) | Provider initialization and operation errors |
| [RUNNER](#runner-errors-if-runner) | Terraform, Ansible, and deployment errors |
| [STATE](#state-errors-if-state) | State management errors |
| [CREDENTIAL](#credential-errors-if-credential) | Credential and authentication errors |
| [SECRET](#secret-errors-if-secret) | Secret management errors |
| [POLICY](#policy-errors-if-policy) | Policy violation errors |
| [VALIDATION](#validation-errors-if-validation) | Configuration validation errors |
| [DEPENDENCY](#dependency-errors-if-dependency) | Resource dependency errors |
| [API](#api-errors-if-api) | External API errors |
| [TEMPLATE](#template-errors-if-template) | Template rendering errors |
| [PLUGIN](#plugin-errors-if-plugin) | Plugin system errors |
| [SYSTEM](#system-errors-if-system) | File system and IO errors |
| [GENERAL](#general-errors-if-general) | Unclassified errors |

---

## Configuration Errors (IF-CONFIG)

### IF-CONFIG-001: Environment Not Found

**Cause:** The specified environment does not exist in the configuration directory.

**Example:**
```
[IF-CONFIG-001] Environment Not Found
  Plan failed: Environment 'production' not found

  Suggestions:
    - Run 'foundry config envs' to list available environments
    - Check that the environment name is spelled correctly
    - Verify INFRAFOUNDRY_CONFIG_REPO points to the correct directory
```

**Solutions:**
1. List available environments: `foundry config envs`
2. Check your configuration directory structure
3. Verify `INFRAFOUNDRY_CONFIG_REPO` environment variable

---

### IF-CONFIG-002: Invalid Configuration

**Cause:** A configuration file contains invalid YAML syntax or structure.

**Example:**
```
[IF-CONFIG-002] Invalid Configuration
  Validation failed: Invalid YAML in proxmox/vm.yaml

  Suggestions:
    - Run 'foundry config doctor --deep' to check configuration health
    - Check YAML syntax (indentation, colons, quotes)
    - Ensure required fields are present
```

**Solutions:**
1. Validate your configuration: `foundry config doctor --deep`
2. Check YAML indentation (use spaces, not tabs)
3. Verify required fields are present

---

### IF-CONFIG-003: Missing Configuration

**Cause:** A required configuration file or value is missing.

**Example:**
```
[IF-CONFIG-003] Missing Configuration
  Plan failed: No configuration files found for environment 'dev'

  Suggestions:
    - Check that all required configuration files exist
    - Run 'foundry config new --env <env>' to create a new environment
    - Verify the config directory structure matches expected layout
```

**Solutions:**
1. Create a new environment: `foundry config new --env <name>`
2. Check the expected directory structure in documentation

---

## Provider Errors (IF-PROVIDER)

### IF-PROVIDER-001: Provider Not Found

**Cause:** The requested provider is not registered or available.

**Solutions:**
1. Check provider name spelling
2. Verify provider plugin is installed
3. Check provider configuration in your environment

---

### IF-PROVIDER-002: Provider Initialization Failed

**Cause:** The provider failed to initialize (usually due to missing credentials or connectivity issues).

**Solutions:**
1. Check provider credentials are set correctly
2. Verify network connectivity to the provider
3. Check provider-specific environment variables

---

### IF-PROVIDER-003: Unsupported Resource Type

**Cause:** The provider does not support the requested resource type.

**Solutions:**
1. Check provider documentation for supported resources
2. Verify resource type name is correct
3. Consider using a different provider

---

## Runner Errors (IF-RUNNER)

### IF-RUNNER-001: Terraform Execution Failed

**Cause:** A Terraform command failed during execution.

**Example:**
```
[IF-RUNNER-001] Terraform Execution Failed
  Apply failed: terraform apply exited with code 1

  Suggestions:
    - Check the Terraform output above for specific errors
    - Verify Terraform is installed and accessible
    - Run 'terraform init' in the generated directory
    - Check provider credentials are set correctly
```

**Solutions:**
1. Check Terraform error output for specific issues
2. Run `terraform init` in `generated/<env>/terraform/<provider>/`
3. Verify provider credentials

---

### IF-RUNNER-002: Ansible Execution Failed

**Cause:** An Ansible playbook failed during execution.

**Solutions:**
1. Check Ansible output for specific task failures
2. Verify SSH connectivity to target hosts
3. Check required Ansible collections are installed

---

### IF-RUNNER-003: Deployment Failed

**Cause:** The deployment operation failed.

**Solutions:**
1. Check error output for specific failure reasons
2. Verify all prerequisites are met
3. Run with `--debug` for more details

---

### IF-RUNNER-004: Rollback Failed

**Cause:** The rollback operation failed.

**Solutions:**
1. Check state database for valid rollback points
2. Verify target deployment ID exists
3. Try manual rollback using generated files

---

## State Errors (IF-STATE)

### IF-STATE-001: State Operation Failed

**Cause:** A state management operation failed.

**Solutions:**
1. Check state database is accessible
2. Verify file permissions on state directory
3. Run `foundry state init` to reinitialize

---

### IF-STATE-002: Deployment Not Found

**Cause:** The requested deployment does not exist in state.

**Solutions:**
1. Run `foundry state list` to see available deployments
2. Check deployment ID is correct
3. Verify you're using the correct environment

---

### IF-STATE-003: Resource Not Found

**Cause:** The requested resource does not exist in state.

**Solutions:**
1. Run `foundry state resources` to list tracked resources
2. Verify resource name is correct
3. Check if resource was previously deleted

---

### IF-STATE-004: State Inconsistency

**Cause:** The state database is inconsistent with actual resources.

**Solutions:**
1. Run `foundry config doctor --deep` to identify environment-level divergence
2. Run `foundry infra drift detect --env <env>` to detect resource-level drift
3. Check for concurrent modifications

---

### IF-STATE-005: Package Move Rollback Failed

**Cause:** A package move between environments failed and the rollback also encountered errors, potentially leaving state in an inconsistent condition.

**Solutions:**
1. Check the error message for both the original failure and rollback errors
2. Run `foundry config doctor --deep` to assess environment consistency
3. Manually verify package state in both source and destination environments
4. Use `foundry infra deployed --env <env>` to check resource tracking

---

## Credential Errors (IF-CREDENTIAL)

### IF-CREDENTIAL-001: Missing Credentials

**Cause:** Required credentials are not configured.

**Solutions:**
1. Set required environment variables
2. Check `secrets/` directory for credential files
3. Verify SOPS/age keys are configured

---

### IF-CREDENTIAL-002: Invalid Credentials

**Cause:** The provided credentials are invalid or malformed.

**Solutions:**
1. Verify credential values are correct
2. Check for typos in environment variable names
3. Ensure API keys/tokens have not expired

---

## Secret Errors (IF-SECRET)

### IF-SECRET-001: Secret Not Found

**Cause:** The requested secret file does not exist.

**Solutions:**
1. Check secret file exists in `secrets/<env>/`
2. Verify secret name is spelled correctly
3. Run `foundry secrets init` to set up secrets directory

---

### IF-SECRET-002: Secret Decryption Failed

**Cause:** Failed to decrypt a secret file (SOPS/age key issue).

**Solutions:**
1. Verify `SOPS_AGE_KEY_FILE` is set correctly
2. Check your age key matches the encrypted secret
3. Ensure secret file is properly encrypted with SOPS

---

## Policy Errors (IF-POLICY)

### IF-POLICY-001: Policy Violation

**Cause:** The operation violates one or more policies.

**Solutions:**
1. Review policy violations in the output
2. Modify resources to comply with policies
3. Contact administrator if policies need updating

---

### IF-POLICY-002: Policy Not Found

**Cause:** The specified policy does not exist.

**Solutions:**
1. Run `foundry policy list` to see available policies
2. Check policy name is correct
3. Verify `policies/` directory exists in config repo

---

## Validation Errors (IF-VALIDATION)

### IF-VALIDATION-001: Validation Failed

**Cause:** Resource validation failed.

**Solutions:**
1. Review validation errors in the output
2. Check resource configuration against schema
3. Run `foundry config doctor --deep` for detailed validation

---

### IF-VALIDATION-002: Connectivity Validation Failed

**Cause:** Provider connectivity check failed.

**Solutions:**
1. Verify network connectivity to the provider
2. Check firewall rules and security groups
3. Ensure provider API endpoints are accessible

---

### IF-VALIDATION-003: Reference Validation Failed

**Cause:** A resource reference is invalid.

**Solutions:**
1. Check referenced resources exist
2. Verify resource names match exactly (case-sensitive)
3. Review dependency graph with `foundry infra analyze dependencies --env <env>`

---

### IF-VALIDATION-004: Schema Validation Failed

**Cause:** Data does not match the expected schema.

**Solutions:**
1. Review schema requirements in documentation
2. Check for missing required fields
3. Verify data types match expected schema

---

## Dependency Errors (IF-DEPENDENCY)

### IF-DEPENDENCY-001: Circular Dependency Detected

**Cause:** Resources have circular dependencies that cannot be resolved.

**Solutions:**
1. Run `foundry infra analyze graph --env <env> --format mermaid` to visualize dependencies
2. Break circular dependency by restructuring resources
3. Use explicit dependency ordering if needed

---

### IF-DEPENDENCY-002: Missing Dependency

**Cause:** A required dependency is not available.

**Solutions:**
1. Check dependent resources are defined
2. Verify resource names in `depends_on` are correct
3. Ensure dependencies are in the same environment

---

## API Errors (IF-API)

### IF-API-001: API Request Failed

**Cause:** An API request to an external service failed.

**Solutions:**
1. Check network connectivity
2. Verify API credentials are valid
3. Check if service is experiencing issues

---

### IF-API-002: Connection Failed

**Cause:** Failed to connect to the remote service.

**Solutions:**
1. Verify service URL is correct
2. Check network connectivity and firewall rules
3. Ensure service is running and accessible

---

### IF-API-003: Authentication Failed

**Cause:** API authentication failed.

**Solutions:**
1. Verify API credentials are correct
2. Check if credentials have expired
3. Ensure API key has required permissions

---

### IF-API-004: Request Timeout

**Cause:** The API request timed out.

**Solutions:**
1. Try the operation again
2. Check if service is overloaded
3. Consider increasing timeout settings

---

## Template Errors (IF-TEMPLATE)

### IF-TEMPLATE-001: Template Rendering Failed

**Cause:** Failed to render a Jinja2 configuration template.

**Solutions:**
1. Check template syntax for errors
2. Verify all required variables are provided
3. Review Jinja2 template documentation

---

## Plugin Errors (IF-PLUGIN)

### IF-PLUGIN-001: Plugin Discovery Failed

**Cause:** Failed to discover plugins.

**Solutions:**
1. Check plugins are properly installed
2. Verify entry point configuration
3. Reinstall the package if needed

---

### IF-PLUGIN-002: Plugin Load Failed

**Cause:** Failed to load a plugin.

**Solutions:**
1. Check plugin dependencies are installed
2. Verify plugin version compatibility
3. Check for import errors in the plugin

---

### IF-PLUGIN-003: Plugin Validation Failed

**Cause:** Plugin validation failed.

**Solutions:**
1. Ensure plugin implements required interface
2. Check plugin configuration
3. Review plugin documentation

---

## System Errors (IF-SYSTEM)

### IF-SYSTEM-001: File Not Found

**Cause:** A required file or directory does not exist.

**Solutions:**
1. Check file path is correct
2. Verify file exists and is readable
3. Make sure you're running from the correct directory

---

### IF-SYSTEM-002: Permission Denied

**Cause:** Insufficient permissions to access a file or resource.

**Solutions:**
1. Check file permissions
2. Try running with appropriate access rights
3. Verify file is not locked by another process

---

### IF-SYSTEM-003: IO Error

**Cause:** An input/output operation failed.

**Solutions:**
1. Check disk space availability
2. Verify storage device is working properly
3. Check for file system errors

---

### IF-SYSTEM-004: Network Error

**Cause:** A network operation failed.

**Solutions:**
1. Check your network connection
2. Verify remote service is reachable
3. Check firewall and proxy settings

---

## General Errors (IF-GENERAL)

### IF-GENERAL-001: Unknown Error

**Cause:** An unexpected error occurred that doesn't match any specific category.

**Solutions:**
1. Run with `--debug` for full error details
2. Check logs for more information
3. Report the issue if it persists

---

## Getting More Information

### Debug Mode

Run any command with `--debug` to see full error details including stack traces:

```bash
foundry --debug infra plan --env dev
```

### Verbose Output

Some commands support `--verbose` for additional output:

```bash
foundry infra doctor --env dev --verbose
```

### Checking Logs

InfraFoundry logs can be found in your system's standard log locations or by setting:

```bash
export INFRAFOUNDRY_LOG_LEVEL=DEBUG
```

---

## Reporting Issues

If you encounter an error that you believe is a bug:

1. Run the command with `--debug` to get full details
2. Note the error code (e.g., IF-CONFIG-001)
3. Open an issue at: https://github.com/endavis/infrafoundry/issues

Include:
- Error code and message
- Command that caused the error
- Relevant configuration (sanitized of secrets)
- Debug output
