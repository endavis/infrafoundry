"""OPNsense credential loader."""

from typing import override

from infrafoundry.core.credential_loader.base_loader import BaseCredentialLoader


class OPNsenseCredentialLoader(BaseCredentialLoader):
    """Loads OPNsense-specific credentials."""

    @property
    @override
    def provider_name(self) -> str:
        """Return the provider name."""
        return "opnsense"

    @property
    @override
    def credential_file(self) -> str:
        """Return the credential filename."""
        return "opnsense.yaml"

    @property
    @override
    def field_mapping(self) -> dict[str, str]:
        """Return mapping of OPNsense secret keys to environment variables."""
        return {
            "opnsense_api_url": "OPNSENSE_API_URL",
            "opnsense_api_key": "OPNSENSE_API_KEY",
            "opnsense_api_secret": "OPNSENSE_API_SECRET",  # nosec B105 - env var name, not a secret
        }
