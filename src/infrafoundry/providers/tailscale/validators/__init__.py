"""Specialized validators for Tailscale resources."""

from infrafoundry.providers.tailscale.validators.acl_validator import AclValidator
from infrafoundry.providers.tailscale.validators.credentials_validator import (
    CredentialsValidator,
)
from infrafoundry.providers.tailscale.validators.device_validator import (
    DeviceReferenceValidator,
)
from infrafoundry.providers.tailscale.validators.dns_validator import DnsValidator
from infrafoundry.providers.tailscale.validators.naming_validator import NamingValidator
from infrafoundry.providers.tailscale.validators.tailnet_key_validator import (
    TailnetKeyValidator,
)

__all__ = [
    "AclValidator",
    "CredentialsValidator",
    "DeviceReferenceValidator",
    "DnsValidator",
    "NamingValidator",
    "TailnetKeyValidator",
]
