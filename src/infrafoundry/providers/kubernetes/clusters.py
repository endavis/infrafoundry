"""Several Kubernetes clusters per environment (#1539, ADR-0030).

``provider_settings.kubernetes`` is either the flat shape (``kubeconfig_path`` and
``context``) describing one cluster, or a ``clusters:`` map naming each one:

.. code-block:: yaml

    provider_settings:
      kubernetes:
        primary: edge
        clusters:
          edge: {kubeconfig_path: ~/.kube/edge.yaml}
          cloud: {kubeconfig_path: ~/.kube/cloud.yaml, context: cloud-admin}

Each cluster is a provider instance (``kubernetes`` for the primary,
``kubernetes@<name>`` for the others, see :mod:`infrafoundry.core.provider_instances`).
:func:`cluster_settings` turns the provider id back into the flat settings dict the
rest of the provider already understands.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from infrafoundry.core.provider_instances import (
    instance_settings,
    is_primary_id,
    raw_provider_settings,
    validate_instance_map,
)

logger = logging.getLogger(__name__)

BASE_PROVIDER = "kubernetes"
CLUSTERS_KEY = "clusters"
PRIMARY_KEY = "primary"

#: Keys that identify one cluster; they cannot be shared defaults.
_PER_CLUSTER_KEYS = ("kubeconfig_path", "context")

#: Holds ``"kubeconfig"`` once the ignored-``KUBECONFIG`` warning has been logged.
_WARNED: set[str] = set()


def cluster_settings(settings_or_env_config: Any, provider_name: str) -> dict[str, Any] | None:
    """Resolve the flat settings dict for one cluster.

    Args:
        settings_or_env_config: The ``kubernetes`` provider settings dict, or an
            environment config exposing ``get_provider_settings``.
        provider_name: ``kubernetes`` (the primary) or ``kubernetes@<name>``.

    Returns:
        With no ``clusters:`` map, the settings unchanged (``None`` stays ``None``).
        Otherwise the cluster's entry. An undeclared or ambiguous cluster yields an
        empty dict.
    """
    return instance_settings(BASE_PROVIDER, settings_or_env_config, provider_name)


def clusters_declared(settings_or_env_config: Any) -> bool:
    """Return whether ``provider_settings.kubernetes`` declares a ``clusters:`` map."""
    settings = raw_provider_settings(settings_or_env_config, BASE_PROVIDER)
    return isinstance(settings, dict) and CLUSTERS_KEY in settings


def allows_env_override(provider_name: str) -> bool:
    """Return whether ``KUBERNETES_*`` env overrides may apply (the primary only)."""
    return is_primary_id(provider_name)


def validate_clusters_settings(settings: dict[str, Any] | None) -> list[str]:
    """Return the shape errors in ``provider_settings.kubernetes`` (empty when valid).

    Args:
        settings: The ``kubernetes`` provider settings; ``None`` or flat settings are valid.
    """
    return validate_instance_map(BASE_PROVIDER, settings, _PER_CLUSTER_KEYS)


def kubeconfig_env_override(settings_or_env_config: Any) -> str | None:
    """Return the first non-empty ``KUBECONFIG`` entry that may override a kubeconfig path.

    With a flat configuration ``KUBECONFIG`` overrides ``kubeconfig_path``. Once
    ``clusters:`` is declared it is ignored for every cluster, the primary included,
    so a shell pointing at one cluster cannot redirect another cluster's resources
    (ADR-0030). A WARNING is logged once per process when that happens.

    Args:
        settings_or_env_config: The ``kubernetes`` provider settings dict, or an
            environment config exposing ``get_provider_settings``.

    Returns:
        The kubeconfig path, or ``None`` when unset or ignored.
    """
    value = os.environ.get("KUBECONFIG", "")
    path = next((p for p in value.split(os.pathsep) if p), None)
    if path is None:
        return None
    if not clusters_declared(settings_or_env_config):
        return path
    if "kubeconfig" not in _WARNED:
        _WARNED.add("kubeconfig")
        logger.warning(
            "KUBECONFIG is set but ignored because provider_settings.kubernetes.clusters "
            "is declared; each cluster uses its own kubeconfig_path"
        )
    return None
