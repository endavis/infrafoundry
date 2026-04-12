"""Credential loader package for InfraFoundry."""

import logging

from infrafoundry.core.credential_loader.base_loader import (
    BaseCredentialLoader,
    CredentialLoaderError,
)
from infrafoundry.core.credential_loader.credential_loader import CredentialLoader
from infrafoundry.core.credential_loader.kubernetes_loader import KubernetesCredentialLoader

logger = logging.getLogger(__name__)

__all__ = [
    "BaseCredentialLoader",
    "CredentialLoader",
    "CredentialLoaderError",
    "KubernetesCredentialLoader",
    "logger",
]
