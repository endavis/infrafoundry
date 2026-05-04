"""In-memory env-secrets backend.

This module provides a secret backend that reads secrets from an
in-memory dict supplied at construction time. The backend is the first
direct-API resource consumer of the ``SecretResolver`` system: the
``virtual_ips`` component manager configures an ``EnvSecretsBackend``
with the decrypted ``EnvironmentConfig.secrets`` dict (populated by
``SecretManager.populate_environment_config`` after SOPS decryption),
and resolves ``secret://env_secrets/<dotted/path>`` URIs in resource
configs at apply time.

The dotted-path lookup walks the dict by ``/``-split path:

    secret://env_secrets/opnsense/carp_passwords/lan_carp_1
    →  config["secrets"]["opnsense"]["carp_passwords"]["lan_carp_1"]

This mirrors the shape of the existing ``EnvSecretBackend`` (env-var
based) and ``FileSecretBackend`` (filesystem based); the only difference
is the source of secret material (a dict held in memory vs. environment
variables vs. files).

Example:
    >>> backend = EnvSecretsBackend(
    ...     {"secrets": {"opnsense": {"carp_passwords": {"lan_carp_1": "s3kr1t"}}}}
    ... )
    >>> backend.get_secret("opnsense/carp_passwords/lan_carp_1")
    's3kr1t'
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from infrafoundry.secrets.protocol import SecretBackendError, SecretNotFoundError

if TYPE_CHECKING:
    from infrafoundry.secrets.plugin_type import SecretBackendMetadata

logger = logging.getLogger(__name__)


class EnvSecretsBackend:
    """Secret backend that reads from an in-memory dict.

    The backend is constructed with a ``config`` dict containing a
    ``secrets`` key, whose value is the (already-decrypted) dict tree of
    secret material for the active environment. ``get_secret`` walks
    that tree by ``/``-split path. Non-string scalar values are coerced
    to strings on read so YAML integers / floats round-trip cleanly to
    callers that expect string secrets.

    Args:
        config: Backend configuration dict. Must contain a ``secrets``
            key (a dict; may be empty).

    Note:
        This is a read-only backend. Calling ``set_secret()`` or
        ``delete_secret()`` will raise ``NotImplementedError``.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize env-secrets backend.

        Args:
            config: Configuration dictionary with required key:
                - secrets: Dict tree of secret material.

        Raises:
            SecretBackendError: If ``secrets`` is missing or not a dict.

        Example:
            >>> backend = EnvSecretsBackend({"secrets": {"db": {"password": "x"}}})
        """
        secrets = config.get("secrets")
        if secrets is None:
            secrets = {}
        if not isinstance(secrets, dict):
            raise SecretBackendError(
                f"EnvSecretsBackend requires 'secrets' to be a dict, got {type(secrets).__name__}"
            )
        self.secrets: dict[str, Any] = secrets
        logger.debug("Initialized EnvSecretsBackend with %d top-level keys", len(self.secrets))

    def get_secret(self, key: str) -> str:
        """Retrieve a secret from the in-memory dict by ``/``-split path.

        Args:
            key: Secret key (e.g., ``"opnsense/carp_passwords/lan_carp_1"``).

        Returns:
            Secret value as a string. Non-string scalar values are
            coerced via ``str()`` so YAML integers / floats are usable
            without surprising the caller.

        Raises:
            SecretNotFoundError: If any segment of the path does not
                exist, or the resolved value is itself a dict (the
                operator named a sub-tree, not a leaf).
            SecretBackendError: If retrieval fails for any other reason.

        Example:
            >>> backend = EnvSecretsBackend(
            ...     {"secrets": {"opnsense": {"carp_passwords": {"lan_carp_1": "s3kr1t"}}}}
            ... )
            >>> backend.get_secret("opnsense/carp_passwords/lan_carp_1")
            's3kr1t'
        """
        try:
            parts = key.split("/")
            cursor: Any = self.secrets
            for part in parts:
                if not isinstance(cursor, dict) or part not in cursor:
                    logger.debug("Secret not found: %s (missing segment %r)", key, part)
                    raise SecretNotFoundError(
                        f"Secret '{key}' not found in env_secrets (missing segment '{part}')"
                    )
                cursor = cursor[part]

            if isinstance(cursor, dict):
                # Operator named a sub-tree, not a leaf.
                raise SecretNotFoundError(f"Secret '{key}' resolves to a dict, not a leaf value")

            logger.debug("Retrieved secret: %s", key)
            return str(cursor)

        except SecretNotFoundError:
            raise
        except Exception as e:
            raise SecretBackendError(f"Failed to retrieve secret '{key}': {e}") from e

    def list_secrets(self, prefix: str = "") -> list[str]:
        """List all leaf secret keys in the in-memory dict.

        Recursively walks the dict tree and returns the ``/``-joined
        path of every leaf (non-dict) value, optionally filtered by a
        prefix. Useful for discovery / audit; not used by the resolver
        on the hot path.

        Args:
            prefix: Optional prefix to filter secrets (e.g.,
                ``"opnsense/"``).

        Returns:
            Sorted list of leaf secret keys.

        Raises:
            SecretBackendError: If listing fails.

        Example:
            >>> backend = EnvSecretsBackend(
            ...     {"secrets": {"db": {"host": "localhost", "password": "secret"}}}
            ... )
            >>> backend.list_secrets()
            ['db/host', 'db/password']
        """
        try:
            keys: list[str] = []
            self._collect_leaf_keys(self.secrets, "", keys)
            if prefix:
                keys = [k for k in keys if k.startswith(prefix)]
            return sorted(keys)
        except Exception as e:
            raise SecretBackendError(f"Failed to list secrets: {e}") from e

    def _collect_leaf_keys(self, node: Any, current_path: str, accumulator: list[str]) -> None:
        """Recursively collect ``/``-joined paths to every leaf value.

        Args:
            node: Current sub-tree being walked.
            current_path: ``/``-joined path to ``node`` (empty at root).
            accumulator: List that leaf keys are appended to in-place.
        """
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{current_path}/{key}" if current_path else str(key)
                self._collect_leaf_keys(value, child_path, accumulator)
            return
        # Leaf — record the path.
        if current_path:
            accumulator.append(current_path)

    def health_check(self) -> bool:
        """Check if backend is accessible.

        For an in-memory backend, this always returns True since the
        secret material is held in memory and cannot become unreachable
        once constructed.

        Returns:
            True (always).

        Example:
            >>> backend = EnvSecretsBackend({"secrets": {}})
            >>> backend.health_check()
            True
        """
        return True


def register() -> SecretBackendMetadata:
    """Register the env-secrets secret backend.

    Returns:
        ``SecretBackendMetadata`` for the env_secrets backend.

    Example:
        >>> metadata = register()
        >>> print(metadata.name)
        'env_secrets'
    """
    from infrafoundry.secrets.plugin_type import SecretBackendMetadata

    return SecretBackendMetadata(
        name="env_secrets",
        version="1.0.0",
        description=(
            "Read secrets from an in-memory dict (e.g. EnvironmentConfig.secrets "
            "after SOPS decryption)"
        ),
        backend_class=EnvSecretsBackend,
        read_only=True,
        author="InfraFoundry Team",
        url="https://github.com/infrascloudy/infrafoundry",
    )
