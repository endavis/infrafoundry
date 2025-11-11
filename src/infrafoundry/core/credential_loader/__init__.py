"""Credential loader package for InfraFoundry."""

import logging

from infrafoundry.core.credential_loader.base_loader import BaseCredentialLoader
from infrafoundry.core.credential_loader.credential_loader import CredentialLoader
from infrafoundry.core.credential_loader.kubernetes_loader import KubernetesCredentialLoader
from infrafoundry.core.credential_loader.opnsense_loader import OPNsenseCredentialLoader
from infrafoundry.core.credential_loader.proxmox_loader import ProxmoxCredentialLoader

logger = logging.getLogger(__name__)

__all__ = [
    "BaseCredentialLoader",
    "CredentialLoader",
    "KubernetesCredentialLoader",
    "OPNsenseCredentialLoader",
    "ProxmoxCredentialLoader",
    "logger",
]
