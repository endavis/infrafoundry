"""Secret backend plugin system.

This module provides pluggable secret management for InfraFoundry.
"""

from infrafoundry.secrets.resolver import SecretResolver, get_resolver

__all__ = ["SecretResolver", "get_resolver"]
