"""Exception hierarchy for InfraFoundry.

Provides structured exceptions with rich context for better error handling
and debugging throughout the application.
"""

from __future__ import annotations

from typing import Any


class InfraFoundryError(Exception):
    """Base exception for all InfraFoundry errors.

    Provides structured error handling with optional context for debugging.
    All custom exceptions should inherit from this base class.
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Initialize error with message and optional context.

        Args:
            message: Human-readable error message
            context: Optional dictionary with additional error context
        """
        self.message = message
        self.context = context or {}
        super().__init__(message)

    def __str__(self) -> str:
        """Return string representation with context if available."""
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} ({context_str})"
        return self.message


# Configuration and Environment Errors


class ConfigurationError(InfraFoundryError):
    """Configuration-related errors."""


class EnvironmentNotFoundError(ConfigurationError):
    """Requested environment does not exist."""


class InvalidConfigurationError(ConfigurationError):
    """Configuration file is invalid or malformed."""


class MissingConfigurationError(ConfigurationError):
    """Required configuration is missing."""


# Provider Errors


class ProviderError(InfraFoundryError):
    """Provider operation failed."""


class ProviderNotFoundError(ProviderError):
    """Requested provider is not registered."""


class ProviderInitializationError(ProviderError):
    """Provider failed to initialize."""


class UnsupportedResourceTypeError(ProviderError):
    """Provider does not support the requested resource type."""


# API and Network Errors


class APIError(InfraFoundryError):
    """API call failed with error response."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: str | None = None,
        provider: str | None = None,
    ) -> None:
        """Initialize API error with HTTP context.

        Args:
            message: Error message
            status_code: HTTP status code if available
            response: Response body or error message
            provider: Provider name that encountered the error
        """
        context: dict[str, Any] = {}
        if status_code is not None:
            context["status_code"] = status_code
        if response is not None:
            context["response"] = response
        if provider is not None:
            context["provider"] = provider
        super().__init__(message, context)
        self.status_code = status_code
        self.response = response
        self.provider = provider


class ConnectionError(APIError):
    """Failed to connect to remote service."""


class AuthenticationError(APIError):
    """Authentication failed."""


class TimeoutError(APIError):
    """Operation timed out."""


# Validation Errors


class ValidationError(InfraFoundryError):
    """Validation failed."""


class ConnectivityValidationError(ValidationError):
    """Provider connectivity validation failed."""


class ReferenceValidationError(ValidationError):
    """Resource reference validation failed."""


class SchemaValidationError(ValidationError):
    """Data does not match expected schema."""


# State Management Errors


class StateError(InfraFoundryError):
    """State management operation failed."""


class DeploymentNotFoundError(StateError):
    """Requested deployment does not exist."""


class ResourceNotFoundError(StateError):
    """Requested resource does not exist."""


class StateInconsistencyError(StateError):
    """State database is inconsistent."""


# Deployment and Orchestration Errors


class DeploymentError(InfraFoundryError):
    """Deployment operation failed."""


class TerraformError(DeploymentError):
    """Terraform execution failed."""

    def __init__(
        self,
        message: str,
        exit_code: int | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> None:
        """Initialize Terraform error with execution context.

        Args:
            message: Error message
            exit_code: Terraform exit code
            stdout: Standard output from Terraform
            stderr: Standard error from Terraform
        """
        context: dict[str, Any] = {}
        if exit_code is not None:
            context["exit_code"] = exit_code
        if stdout is not None:
            context["stdout"] = stdout
        if stderr is not None:
            context["stderr"] = stderr
        super().__init__(message, context)
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class AnsibleError(DeploymentError):
    """Ansible execution failed."""


class RollbackError(DeploymentError):
    """Rollback operation failed."""


# Policy Errors


class PolicyError(InfraFoundryError):
    """Policy-related errors."""


class PolicyViolationError(PolicyError):
    """Policy check failed with violations."""

    def __init__(self, message: str, violations: list[dict[str, Any]] | None = None) -> None:
        """Initialize policy violation error.

        Args:
            message: Error message
            violations: List of policy violations
        """
        context = {"violation_count": len(violations) if violations else 0}
        super().__init__(message, context)
        self.violations = violations or []


class PolicyNotFoundError(PolicyError):
    """Requested policy does not exist."""


# Credential Errors


class CredentialError(InfraFoundryError):
    """Credential-related errors."""


class MissingCredentialError(CredentialError):
    """Required credential is missing."""


class InvalidCredentialError(CredentialError):
    """Credential is invalid or malformed."""


# Secret Management Errors


class SecretError(InfraFoundryError):
    """Secret management operation failed."""


class SecretNotFoundError(SecretError):
    """Requested secret does not exist."""


class SecretDecryptionError(SecretError):
    """Failed to decrypt secret."""


# Dependency Errors


class DependencyError(InfraFoundryError):
    """Dependency resolution failed."""


class CircularDependencyError(DependencyError):
    """Circular dependency detected."""


class MissingDependencyError(DependencyError):
    """Required dependency is missing."""


# Template Errors
class TemplateError(InfraFoundryError):
    """Template rendering or loading failed."""


__all__ = [
    # API/Network
    "APIError",
    "AnsibleError",
    "AuthenticationError",
    "CircularDependencyError",
    # Configuration
    "ConfigurationError",
    "ConnectionError",
    "ConnectivityValidationError",
    # Credentials
    "CredentialError",
    # Dependencies
    "DependencyError",
    # Deployment
    "DeploymentError",
    "DeploymentNotFoundError",
    "EnvironmentNotFoundError",
    "InfraFoundryError",
    "InvalidConfigurationError",
    "InvalidCredentialError",
    "MissingConfigurationError",
    "MissingCredentialError",
    "MissingDependencyError",
    # Policy
    "PolicyError",
    "PolicyNotFoundError",
    "PolicyViolationError",
    # Provider
    "ProviderError",
    "ProviderInitializationError",
    "ProviderNotFoundError",
    "ReferenceValidationError",
    "ResourceNotFoundError",
    "RollbackError",
    "SchemaValidationError",
    "SecretDecryptionError",
    # Secrets
    "SecretError",
    "SecretNotFoundError",
    # State
    "StateError",
    "StateInconsistencyError",
    # Template
    "TemplateError",
    "TerraformError",
    "TimeoutError",
    "UnsupportedResourceTypeError",
    # Validation
    "ValidationError",
]
