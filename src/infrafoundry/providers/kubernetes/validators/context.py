"""Validation contexts for the Kubernetes sub-validators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from infrafoundry.core.validation import ValidationContext

if TYPE_CHECKING:
    from infrafoundry.core.provider import ResourceConfig


@dataclass(frozen=True, kw_only=True)
class KubeconfigContext(ValidationContext):
    """Context for validating a kubeconfig and testing API connectivity.

    Attributes:
        kubeconfig_path: Path to the kubeconfig file, or None for the default.
        context_override: Context name to use instead of ``current-context``.
    """

    kubeconfig_path: str | None
    context_override: str | None = None


@dataclass(frozen=True, kw_only=True)
class KubernetesHelmContext(ValidationContext):
    """Context for validating helm release resources.

    Attributes:
        helm_releases: Helm release resources to validate.
    """

    helm_releases: list[ResourceConfig] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class KubernetesApiContext(ValidationContext):
    """Context for validators that query the Kubernetes API.

    Attributes:
        server_url: Kubernetes API server URL.
        headers: HTTP headers with authorization.
        verify_ssl: Whether to verify SSL certificates.
        referenced_namespaces: Namespaces referenced by resources.
        config_namespaces: Namespaces defined in the configuration.
        manifests: Manifest resources to check for CRD requirements.
    """

    server_url: str
    headers: dict[str, str]
    verify_ssl: bool
    referenced_namespaces: set[str] = field(default_factory=set)
    config_namespaces: set[str] = field(default_factory=set)
    manifests: list[ResourceConfig] = field(default_factory=list)
