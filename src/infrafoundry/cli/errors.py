"""Error catalog with error codes and actionable suggestions.

Provides structured error codes (IF-CATEGORY-NNN) for all InfraFoundry errors,
with actionable suggestions to help users resolve issues.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCategory(StrEnum):
    """Error code categories."""

    CONFIG = "CONFIG"
    PROVIDER = "PROVIDER"
    RUNNER = "RUNNER"
    STATE = "STATE"
    CREDENTIAL = "CREDENTIAL"
    SECRET = "SECRET"  # nosec B105 - enum value, not a password
    POLICY = "POLICY"
    VALIDATION = "VALIDATION"
    DEPENDENCY = "DEPENDENCY"
    API = "API"
    TEMPLATE = "TEMPLATE"
    PLUGIN = "PLUGIN"
    SYSTEM = "SYSTEM"
    GENERAL = "GENERAL"


@dataclass(frozen=True)
class ErrorInfo:
    """Error code information with actionable guidance.

    Attributes:
        code: Error code (e.g., IF-CONFIG-001)
        title: Short error title
        description: Detailed description of the error
        suggestions: List of actionable suggestions to resolve the error
        see_also: Optional documentation reference
    """

    code: str
    title: str
    description: str
    suggestions: list[str]
    see_also: str | None = None

    def format_message(self, original_message: str, *, verbose: bool = False) -> str:
        """Format error message with code and suggestions.

        Args:
            original_message: The original exception message
            verbose: Include full description if True

        Returns:
            Formatted error message with code and suggestions
        """
        lines = [f"[{self.code}] {self.title}"]
        lines.append(f"  {original_message}")

        if verbose and self.description:
            lines.append("")
            lines.append(f"  {self.description}")

        if self.suggestions:
            lines.append("")
            lines.append("  Suggestions:")
            for suggestion in self.suggestions:
                lines.append(f"    - {suggestion}")

        if self.see_also:
            lines.append("")
            lines.append(f"  See: {self.see_also}")

        lines.append("")
        lines.append("  Run with --debug for full error details.")

        return "\n".join(lines)


# Error catalog - maps error codes to their information
ERROR_CATALOG: dict[str, ErrorInfo] = {
    # Configuration errors (IF-CONFIG-XXX)
    "IF-CONFIG-001": ErrorInfo(
        code="IF-CONFIG-001",
        title="Environment Not Found",
        description="The specified environment does not exist in the configuration.",
        suggestions=[
            "Run 'foundry config envs' to list available environments",
            "Check that the environment name is spelled correctly",
            "Verify INFRAFOUNDRY_CONFIG_REPO points to the correct directory",
        ],
        see_also="docs/configuration/environments.md",
    ),
    "IF-CONFIG-002": ErrorInfo(
        code="IF-CONFIG-002",
        title="Invalid Configuration",
        description="The configuration file contains invalid or malformed data.",
        suggestions=[
            "Run 'foundry config validate --env <env>' to see validation errors",
            "Check YAML syntax (indentation, colons, quotes)",
            "Ensure required fields are present",
        ],
        see_also="docs/configuration/syntax.md",
    ),
    "IF-CONFIG-003": ErrorInfo(
        code="IF-CONFIG-003",
        title="Missing Configuration",
        description="A required configuration file or value is missing.",
        suggestions=[
            "Check that all required configuration files exist",
            "Run 'foundry config new --env <env>' to create a new environment",
            "Verify the config directory structure matches expected layout",
        ],
    ),
    # Provider errors (IF-PROVIDER-XXX)
    "IF-PROVIDER-001": ErrorInfo(
        code="IF-PROVIDER-001",
        title="Provider Not Found",
        description="The requested provider is not registered or available.",
        suggestions=[
            "Check that the provider name is spelled correctly",
            "Verify the provider plugin is installed",
            "Check provider configuration in your environment",
        ],
    ),
    "IF-PROVIDER-002": ErrorInfo(
        code="IF-PROVIDER-002",
        title="Provider Initialization Failed",
        description="The provider failed to initialize properly.",
        suggestions=[
            "Check provider credentials and configuration",
            "Verify network connectivity to the provider",
            "Check provider-specific environment variables",
        ],
    ),
    "IF-PROVIDER-003": ErrorInfo(
        code="IF-PROVIDER-003",
        title="Unsupported Resource Type",
        description="The provider does not support this resource type.",
        suggestions=[
            "Check the provider documentation for supported resources",
            "Verify the resource type name is correct",
            "Consider using a different provider for this resource",
        ],
    ),
    # Runner errors (IF-RUNNER-XXX)
    "IF-RUNNER-001": ErrorInfo(
        code="IF-RUNNER-001",
        title="Terraform Execution Failed",
        description="Terraform command failed during execution.",
        suggestions=[
            "Check the Terraform output above for specific errors",
            "Verify Terraform is installed and accessible",
            "Run 'terraform init' in the generated directory",
            "Check provider credentials are set correctly",
        ],
    ),
    "IF-RUNNER-002": ErrorInfo(
        code="IF-RUNNER-002",
        title="Ansible Execution Failed",
        description="Ansible playbook failed during execution.",
        suggestions=[
            "Check the Ansible output for specific task failures",
            "Verify SSH connectivity to target hosts",
            "Check that required Ansible collections are installed",
        ],
    ),
    "IF-RUNNER-003": ErrorInfo(
        code="IF-RUNNER-003",
        title="Deployment Failed",
        description="The deployment operation failed.",
        suggestions=[
            "Check the error output for specific failure reasons",
            "Verify all prerequisites are met",
            "Try running with --debug for more details",
        ],
    ),
    "IF-RUNNER-004": ErrorInfo(
        code="IF-RUNNER-004",
        title="Rollback Failed",
        description="The rollback operation failed.",
        suggestions=[
            "Check the state database for valid rollback points",
            "Verify the target deployment ID exists",
            "Try manual rollback using the generated files",
        ],
    ),
    # State errors (IF-STATE-XXX)
    "IF-STATE-001": ErrorInfo(
        code="IF-STATE-001",
        title="State Operation Failed",
        description="A state management operation failed.",
        suggestions=[
            "Check the state database is accessible",
            "Verify file permissions on the state directory",
            "Run 'foundry state init' to reinitialize the state",
        ],
    ),
    "IF-STATE-002": ErrorInfo(
        code="IF-STATE-002",
        title="Deployment Not Found",
        description="The requested deployment does not exist in state.",
        suggestions=[
            "Run 'foundry state list' to see available deployments",
            "Check that the deployment ID is correct",
            "Verify you're using the correct environment",
        ],
    ),
    "IF-STATE-003": ErrorInfo(
        code="IF-STATE-003",
        title="Resource Not Found",
        description="The requested resource does not exist in state.",
        suggestions=[
            "Run 'foundry state resources' to list tracked resources",
            "Verify the resource name is correct",
            "Check if the resource was previously deleted",
        ],
    ),
    "IF-STATE-004": ErrorInfo(
        code="IF-STATE-004",
        title="State Inconsistency",
        description="The state database is inconsistent with actual resources.",
        suggestions=[
            "Run 'foundry infra drift --env <env>' to detect drift",
            "Consider running 'foundry state reset' (use with caution)",
            "Check for concurrent modifications to infrastructure",
        ],
    ),
    # Credential errors (IF-CREDENTIAL-XXX)
    "IF-CREDENTIAL-001": ErrorInfo(
        code="IF-CREDENTIAL-001",
        title="Missing Credentials",
        description="Required credentials are not configured.",
        suggestions=[
            "Set the required environment variables",
            "Check the secrets/ directory for credential files",
            "Verify SOPS/age keys are configured for encrypted secrets",
        ],
    ),
    "IF-CREDENTIAL-002": ErrorInfo(
        code="IF-CREDENTIAL-002",
        title="Invalid Credentials",
        description="The provided credentials are invalid or malformed.",
        suggestions=[
            "Verify credential values are correct",
            "Check for typos in environment variable names",
            "Ensure API keys/tokens have not expired",
        ],
    ),
    # Secret errors (IF-SECRET-XXX)
    "IF-SECRET-001": ErrorInfo(
        code="IF-SECRET-001",
        title="Secret Not Found",
        description="The requested secret does not exist.",
        suggestions=[
            "Check that the secret file exists in secrets/<env>/",
            "Verify the secret name is spelled correctly",
            "Run 'foundry secrets init' to set up secrets directory",
        ],
    ),
    "IF-SECRET-002": ErrorInfo(
        code="IF-SECRET-002",
        title="Secret Decryption Failed",
        description="Failed to decrypt the secret.",
        suggestions=[
            "Verify SOPS_AGE_KEY_FILE is set correctly",
            "Check that your age key matches the encrypted secret",
            "Ensure the secret file is properly encrypted with SOPS",
        ],
    ),
    # Policy errors (IF-POLICY-XXX)
    "IF-POLICY-001": ErrorInfo(
        code="IF-POLICY-001",
        title="Policy Violation",
        description="The operation violates one or more policies.",
        suggestions=[
            "Review the policy violations listed above",
            "Modify resources to comply with policies",
            "Contact your administrator if policies need updating",
        ],
    ),
    "IF-POLICY-002": ErrorInfo(
        code="IF-POLICY-002",
        title="Policy Not Found",
        description="The specified policy does not exist.",
        suggestions=[
            "Run 'foundry policy list' to see available policies",
            "Check that the policy name is correct",
            "Verify policies/ directory exists in config repo",
        ],
    ),
    # Validation errors (IF-VALIDATION-XXX)
    "IF-VALIDATION-001": ErrorInfo(
        code="IF-VALIDATION-001",
        title="Validation Failed",
        description="Resource validation failed.",
        suggestions=[
            "Review the validation errors listed above",
            "Check resource configuration against schema",
            "Run 'foundry config validate' for detailed validation",
        ],
    ),
    "IF-VALIDATION-002": ErrorInfo(
        code="IF-VALIDATION-002",
        title="Connectivity Validation Failed",
        description="Provider connectivity check failed.",
        suggestions=[
            "Verify network connectivity to the provider",
            "Check firewall rules and security groups",
            "Ensure provider API endpoints are accessible",
        ],
    ),
    "IF-VALIDATION-003": ErrorInfo(
        code="IF-VALIDATION-003",
        title="Reference Validation Failed",
        description="A resource reference is invalid.",
        suggestions=[
            "Check that referenced resources exist",
            "Verify resource names match exactly (case-sensitive)",
            "Review dependency graph with 'foundry analyze dependencies'",
        ],
    ),
    "IF-VALIDATION-004": ErrorInfo(
        code="IF-VALIDATION-004",
        title="Schema Validation Failed",
        description="Data does not match the expected schema.",
        suggestions=[
            "Review the schema requirements in documentation",
            "Check for missing required fields",
            "Verify data types match expected schema",
        ],
    ),
    # Dependency errors (IF-DEPENDENCY-XXX)
    "IF-DEPENDENCY-001": ErrorInfo(
        code="IF-DEPENDENCY-001",
        title="Circular Dependency Detected",
        description="Resources have circular dependencies that cannot be resolved.",
        suggestions=[
            "Run 'foundry analyze graph --env <env>' to visualize dependencies",
            "Break the circular dependency by restructuring resources",
            "Use explicit dependency ordering if needed",
        ],
    ),
    "IF-DEPENDENCY-002": ErrorInfo(
        code="IF-DEPENDENCY-002",
        title="Missing Dependency",
        description="A required dependency is not available.",
        suggestions=[
            "Check that dependent resources are defined",
            "Verify resource names in depends_on are correct",
            "Ensure dependencies are in the same environment",
        ],
    ),
    # API errors (IF-API-XXX)
    "IF-API-001": ErrorInfo(
        code="IF-API-001",
        title="API Request Failed",
        description="An API request to an external service failed.",
        suggestions=[
            "Check network connectivity",
            "Verify API credentials are valid",
            "Check if the service is experiencing issues",
        ],
    ),
    "IF-API-002": ErrorInfo(
        code="IF-API-002",
        title="Connection Failed",
        description="Failed to connect to the remote service.",
        suggestions=[
            "Verify the service URL is correct",
            "Check network connectivity and firewall rules",
            "Ensure the service is running and accessible",
        ],
    ),
    "IF-API-003": ErrorInfo(
        code="IF-API-003",
        title="Authentication Failed",
        description="API authentication failed.",
        suggestions=[
            "Verify your API credentials are correct",
            "Check if credentials have expired",
            "Ensure the API key has required permissions",
        ],
    ),
    "IF-API-004": ErrorInfo(
        code="IF-API-004",
        title="Request Timeout",
        description="The API request timed out.",
        suggestions=[
            "Try the operation again",
            "Check if the service is overloaded",
            "Consider increasing timeout settings",
        ],
    ),
    # Template errors (IF-TEMPLATE-XXX)
    "IF-TEMPLATE-001": ErrorInfo(
        code="IF-TEMPLATE-001",
        title="Template Rendering Failed",
        description="Failed to render a configuration template.",
        suggestions=[
            "Check template syntax for errors",
            "Verify all required variables are provided",
            "Review Jinja2 template documentation",
        ],
    ),
    # Plugin errors (IF-PLUGIN-XXX)
    "IF-PLUGIN-001": ErrorInfo(
        code="IF-PLUGIN-001",
        title="Plugin Discovery Failed",
        description="Failed to discover plugins.",
        suggestions=[
            "Check that plugins are properly installed",
            "Verify entry point configuration",
            "Reinstall the package if needed",
        ],
    ),
    "IF-PLUGIN-002": ErrorInfo(
        code="IF-PLUGIN-002",
        title="Plugin Load Failed",
        description="Failed to load a plugin.",
        suggestions=[
            "Check plugin dependencies are installed",
            "Verify plugin version compatibility",
            "Check for import errors in the plugin",
        ],
    ),
    "IF-PLUGIN-003": ErrorInfo(
        code="IF-PLUGIN-003",
        title="Plugin Validation Failed",
        description="Plugin validation failed.",
        suggestions=[
            "Ensure plugin implements required interface",
            "Check plugin configuration",
            "Review plugin documentation",
        ],
    ),
    # System/IO errors (IF-SYSTEM-XXX)
    "IF-SYSTEM-001": ErrorInfo(
        code="IF-SYSTEM-001",
        title="File Not Found",
        description="A required file or directory does not exist.",
        suggestions=[
            "Check that the file path is correct",
            "Verify the file exists and is readable",
            "Make sure you're running from the correct directory",
        ],
    ),
    "IF-SYSTEM-002": ErrorInfo(
        code="IF-SYSTEM-002",
        title="Permission Denied",
        description="Insufficient permissions to access a file or resource.",
        suggestions=[
            "Check file permissions",
            "Try running with appropriate access rights",
            "Verify the file is not locked by another process",
        ],
    ),
    "IF-SYSTEM-003": ErrorInfo(
        code="IF-SYSTEM-003",
        title="IO Error",
        description="An input/output operation failed.",
        suggestions=[
            "Check disk space availability",
            "Verify the storage device is working properly",
            "Check for file system errors",
        ],
    ),
    "IF-SYSTEM-004": ErrorInfo(
        code="IF-SYSTEM-004",
        title="Network Error",
        description="A network operation failed.",
        suggestions=[
            "Check your network connection",
            "Verify the remote service is reachable",
            "Check firewall and proxy settings",
        ],
    ),
    # General error (IF-GENERAL-XXX)
    "IF-GENERAL-001": ErrorInfo(
        code="IF-GENERAL-001",
        title="Unknown Error",
        description="An unexpected error occurred.",
        suggestions=[
            "Run with --debug for full error details",
            "Check the logs for more information",
            "Report the issue if it persists",
        ],
    ),
}

# Mapping from exception class names to error codes
_EXCEPTION_TO_CODE: dict[str, str] = {
    # Configuration errors
    "EnvironmentNotFoundError": "IF-CONFIG-001",
    "InvalidConfigurationError": "IF-CONFIG-002",
    "MissingConfigurationError": "IF-CONFIG-003",
    "ConfigurationError": "IF-CONFIG-002",  # Generic fallback
    # Provider errors
    "ProviderNotFoundError": "IF-PROVIDER-001",
    "ProviderInitializationError": "IF-PROVIDER-002",
    "UnsupportedResourceTypeError": "IF-PROVIDER-003",
    "ProviderError": "IF-PROVIDER-002",  # Generic fallback
    # Runner/Deployment errors
    "TerraformError": "IF-RUNNER-001",
    "AnsibleError": "IF-RUNNER-002",
    "DeploymentError": "IF-RUNNER-003",
    "RollbackError": "IF-RUNNER-004",
    # State errors
    "StateError": "IF-STATE-001",
    "DeploymentNotFoundError": "IF-STATE-002",
    "ResourceNotFoundError": "IF-STATE-003",
    "StateInconsistencyError": "IF-STATE-004",
    # Credential errors
    "MissingCredentialError": "IF-CREDENTIAL-001",
    "InvalidCredentialError": "IF-CREDENTIAL-002",
    "CredentialError": "IF-CREDENTIAL-001",  # Generic fallback
    # Secret errors
    "SecretNotFoundError": "IF-SECRET-001",
    "SecretDecryptionError": "IF-SECRET-002",
    "SecretError": "IF-SECRET-001",  # Generic fallback
    # Policy errors
    "PolicyViolationError": "IF-POLICY-001",
    "PolicyNotFoundError": "IF-POLICY-002",
    "PolicyError": "IF-POLICY-001",  # Generic fallback
    # Validation errors
    "ValidationError": "IF-VALIDATION-001",
    "ConnectivityValidationError": "IF-VALIDATION-002",
    "ReferenceValidationError": "IF-VALIDATION-003",
    "SchemaValidationError": "IF-VALIDATION-004",
    # Dependency errors
    "CircularDependencyError": "IF-DEPENDENCY-001",
    "MissingDependencyError": "IF-DEPENDENCY-002",
    "DependencyError": "IF-DEPENDENCY-001",  # Generic fallback
    # API errors
    "APIError": "IF-API-001",
    "ConnectionError": "IF-API-002",
    "AuthenticationError": "IF-API-003",
    "TimeoutError": "IF-API-004",
    # Template errors
    "TemplateError": "IF-TEMPLATE-001",
    # Plugin errors
    "PluginDiscoveryError": "IF-PLUGIN-001",
    "PluginLoadError": "IF-PLUGIN-002",
    "PluginValidationError": "IF-PLUGIN-003",
    "PluginNotFoundError": "IF-PLUGIN-002",
    "PluginConflictError": "IF-PLUGIN-002",
    "PluginTypeError": "IF-PLUGIN-002",
    "PluginVersionError": "IF-PLUGIN-002",
    "PluginError": "IF-PLUGIN-002",  # Generic fallback
    # System/IO errors (Python built-in exceptions)
    "FileNotFoundError": "IF-SYSTEM-001",
    "PermissionError": "IF-SYSTEM-002",
    "IOError": "IF-SYSTEM-003",
    "OSError": "IF-SYSTEM-003",
}


def get_error_code(exc: Exception) -> str:
    """Get the error code for an exception.

    Args:
        exc: The exception to look up

    Returns:
        The error code (e.g., IF-CONFIG-001) or IF-GENERAL-001 for unknown errors
    """
    exc_class_name = type(exc).__name__

    # Check direct mapping first
    if exc_class_name in _EXCEPTION_TO_CODE:
        return _EXCEPTION_TO_CODE[exc_class_name]

    # Check parent classes
    for cls in type(exc).__mro__:
        if cls.__name__ in _EXCEPTION_TO_CODE:
            return _EXCEPTION_TO_CODE[cls.__name__]

    return "IF-GENERAL-001"


def get_error_info(code: str) -> ErrorInfo | None:
    """Get error information for a code.

    Args:
        code: The error code (e.g., IF-CONFIG-001)

    Returns:
        ErrorInfo if found, None otherwise
    """
    return ERROR_CATALOG.get(code)


def format_error(
    exc: Exception,
    action: str | None = None,
    *,
    verbose: bool = False,
) -> str:
    """Format an exception with error code and suggestions.

    Args:
        exc: The exception to format
        action: Optional action description (e.g., "Plan failed")
        verbose: Include full description if True

    Returns:
        Formatted error message with code and suggestions
    """
    code = get_error_code(exc)
    info = get_error_info(code)

    if info is None:
        # Fallback for unknown codes
        info = ERROR_CATALOG["IF-GENERAL-001"]

    # Get the original message
    original_message = getattr(exc, "message", None) or str(exc)

    # Add action prefix if provided
    if action:
        original_message = f"{action}: {original_message}"

    return info.format_message(original_message, verbose=verbose)


def list_error_codes(category: ErrorCategory | None = None) -> list[ErrorInfo]:
    """List all error codes, optionally filtered by category.

    Args:
        category: Optional category to filter by

    Returns:
        List of ErrorInfo objects
    """
    if category is None:
        return list(ERROR_CATALOG.values())

    prefix = f"IF-{category.value}-"
    return [info for code, info in ERROR_CATALOG.items() if code.startswith(prefix)]


__all__ = [
    "ERROR_CATALOG",
    "ErrorCategory",
    "ErrorInfo",
    "format_error",
    "get_error_code",
    "get_error_info",
    "list_error_codes",
]
