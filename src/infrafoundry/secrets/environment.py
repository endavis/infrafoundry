"""Build the per-environment ``SecretResolver`` and resolve secret references against it.

Every place that resolves ``secret://`` values from an environment (provider settings, OPNsense
component configs, collector devices, ``terraform_secrets`` and the host Tailscale auth ref) goes
through this module, so a backend added to ``settings.yaml`` works everywhere at once.

Backends configured for an environment: ``env_secrets`` (the decrypted ``secrets.yaml``) always,
and ``bitwarden`` when ``secret_backends.bitwarden`` is set. ``env`` and ``file`` are deliberately
not opened to config fields or to the Terraform/Ansible bridges.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from infrafoundry.secrets.resolver import (
    SecretResolutionError,
    SecretResolver,
    is_secret_uri,
    parse_secret_uri,
)

if TYPE_CHECKING:
    from types import TracebackType

    from infrafoundry.core.config.models import EnvironmentConfig


def configured_backends(env_config: EnvironmentConfig) -> frozenset[str]:
    """Return the ``secret://`` backend names configured for the environment."""
    names = {"env_secrets"}
    backends = getattr(env_config, "secret_backends", None)
    if backends is not None and backends.bitwarden is not None:
        names.add("bitwarden")
    return frozenset(names)


def build_secret_resolver(env_config: EnvironmentConfig) -> SecretResolver:
    """Return a resolver configured for the environment.

    Backends are instantiated on first use, so a ``bitwarden`` block costs nothing (no ``bw``
    call, no credentials needed) until a ``secret://bitwarden/...`` value is resolved.

    Args:
        env_config: The environment, with its decrypted ``secrets`` populated.

    Returns:
        A resolver; the caller closes it.
    """
    resolver = SecretResolver()
    env_secrets = env_config.secrets if env_config.secrets is not None else {}
    resolver.configure_backend("env_secrets", {"secrets": env_secrets})
    backends = env_config.secret_backends
    if backends is not None and backends.bitwarden is not None:
        config: dict[str, Any] = backends.bitwarden.model_dump()
        config["env_secrets"] = env_secrets
        resolver.configure_backend("bitwarden", config)
    return resolver


class SecretRefLookup:
    """Resolve ``secret://`` URIs and plain dotted refs for the Terraform/Ansible bridges.

    The decrypted secrets are flattened lazily and the resolver is built only when a URI is
    looked up, so a run with only dotted refs never touches a vault. ``package.`` and
    ``outputs.`` refs are not handled here.

    Example:
        >>> with SecretRefLookup(env_config) as lookup:  # doctest: +SKIP
        ...     value = lookup.lookup("secret://env_secrets/db/password")
    """

    def __init__(self, env_config: EnvironmentConfig) -> None:
        """Bind the lookup to an environment."""
        self._env_config = env_config
        self._flat: dict[str, str] | None = None
        self._resolver: SecretResolver | None = None

    def __enter__(self) -> SecretRefLookup:
        """Enter the context."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the resolver, if one was built."""
        self.close()

    def close(self) -> None:
        """Close the resolver, if one was built."""
        if self._resolver is not None:
            self._resolver.close()
            self._resolver = None

    def _flat_secrets(self) -> dict[str, str]:
        if self._flat is None:
            from infrafoundry.core.secrets.secret_manager import SecretManager

            self._flat = SecretManager.flatten_dict(self._env_config.secrets)
        return self._flat

    def problem(self, ref: str) -> str | None:
        """Return why ``ref`` cannot resolve, checked offline, or ``None`` when it looks fine.

        A ``bitwarden`` URI is checked for shape and a configured backend only; the vault is
        queried at apply time.
        """
        if not is_secret_uri(ref):
            if ref in self._flat_secrets():
                return None
            return f"not present in env '{self._env_config.name}' secrets"
        try:
            backend, key = parse_secret_uri(ref)
        except SecretResolutionError:
            return "malformed secret URI, expected secret://<backend>/<key>"
        allowed = configured_backends(self._env_config)
        if backend not in allowed:
            return f"backend '{backend}' is not configured (configured: {sorted(allowed)})"
        if backend == "env_secrets":
            node: Any = self._env_config.secrets or {}
            for part in key.split("/"):
                if not isinstance(node, dict) or part not in node:
                    return f"not present in env '{self._env_config.name}' secrets"
                node = node[part]
            if isinstance(node, dict) or node is None:
                return f"not present in env '{self._env_config.name}' secrets"
            return None
        if "/" not in key or key.startswith("/") or key.endswith("/"):
            return "bitwarden key must be <item>/<field>"
        return None

    def lookup(self, ref: str) -> str:
        """Return the value of ``ref``.

        Raises:
            KeyError: If it does not resolve. The message never carries a value.
        """
        if not is_secret_uri(ref):
            flat = self._flat_secrets()
            if ref not in flat:
                raise KeyError(
                    f"terraform_secrets reference '{ref}' is not present in "
                    f"env '{self._env_config.name}' secrets. "
                    f"Available top-level keys: "
                    f"{sorted({k.split('.')[0] for k in flat})}"
                )
            return flat[ref]
        reason = self.problem(ref)
        if reason is not None:
            raise KeyError(reason)
        if self._resolver is None:
            self._resolver = build_secret_resolver(self._env_config)
        try:
            return self._resolver.resolve(ref)
        except SecretResolutionError as exc:
            raise KeyError(str(exc)) from None
