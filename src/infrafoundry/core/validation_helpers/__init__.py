"""Validation helpers for infrastructure provider validation.

This package provides specialized validators for common validation tasks:
- Credential validation (configuration + environment variables)
- API connectivity testing
- Resource reference validation
- Validation report helpers

Main classes:
    - BaseProviderValidator: Unified interface composing all validators
    - CredentialValidator: Validates provider credentials
    - ConnectivityValidator: Tests API/HTTP connectivity
    - ResourceValidator: Validates resource references
    - ValidationReportHelper: Convenience methods for reporting

Example:
    >>> from infrafoundry.core.validation_helpers import BaseProviderValidator
    >>> validator = BaseProviderValidator("proxmox", env_config, report)
    >>> credentials = validator.validate_credentials(["api_url", "api_token"])
    >>> if credentials:
    ...     validator.check_api_connectivity(credentials['api_url'])
"""

from infrafoundry.core.validation_helpers.api_validator import BaseAPIValidator
from infrafoundry.core.validation_helpers.base_validator import BaseProviderValidator
from infrafoundry.core.validation_helpers.connectivity_validator import ConnectivityValidator
from infrafoundry.core.validation_helpers.credential_validator import CredentialValidator
from infrafoundry.core.validation_helpers.report_helper import ValidationReportHelper
from infrafoundry.core.validation_helpers.resource_validator import ResourceValidator
from infrafoundry.core.validation_helpers.terraform_secrets_validator import (
    validate_terraform_secrets_references,
)

__all__ = [
    "BaseAPIValidator",
    "BaseProviderValidator",
    "ConnectivityValidator",
    "CredentialValidator",
    "ResourceValidator",
    "ValidationReportHelper",
    "validate_terraform_secrets_references",
]
