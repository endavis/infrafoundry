"""Proxmox credential loader."""

from typing import override

from infrafoundry.core.credential_loader.base_loader import BaseCredentialLoader


class ProxmoxCredentialLoader(BaseCredentialLoader):
    """Loads Proxmox-specific credentials."""

    @property
    @override
    def provider_name(self) -> str:
        """Return the provider name."""
        return "proxmox"

    @property
    @override
    def credential_file(self) -> str:
        """Return the credential filename."""
        return "proxmox.yaml"

    @property
    @override
    def field_mapping(self) -> dict[str, str]:
        """Return mapping of Proxmox secret keys to environment variables."""
        return {
            "proxmox_api_url": "PROXMOX_API_URL",
            "proxmox_api_token_id": "PROXMOX_API_TOKEN_ID",  # nosec B105
            "proxmox_api_token_secret": "PROXMOX_API_TOKEN_SECRET",  # nosec B105
        }
