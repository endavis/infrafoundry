"""Kubernetes credential loader."""

from typing import override

from infrafoundry.core.credential_loader.base_loader import BaseCredentialLoader


class KubernetesCredentialLoader(BaseCredentialLoader):
    """Loads Kubernetes-specific credentials."""

    @property
    @override
    def provider_name(self) -> str:
        """Return the provider name."""
        return "kubernetes"

    @property
    @override
    def credential_file(self) -> str:
        """Return the credential filename."""
        return "kubernetes.yaml"

    @property
    @override
    def field_mapping(self) -> dict[str, str]:
        """Return mapping of Kubernetes secret keys to environment variables."""
        return {
            "kubeconfig": "KUBECONFIG",
        }
