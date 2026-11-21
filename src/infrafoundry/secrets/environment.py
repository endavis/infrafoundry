"""Build the per-environment ``SecretResolver`` and resolve secret references against it.

Every place that resolves ``secret://`` values from an environment (provider settings, OPNsense
component configs, collector devices, ``terraform_secrets`` and the host Tailscale auth ref) goes
through this module, so a backend added to ``settings.yaml`` works everywhere at once.

Backends configured for an environment: ``env_secrets`` (the decrypted ``secrets.yaml``) always,
and ``bitwarden`` when ``secret_backends.bitwarden`` is set. ``env`` and ``file`` are deliberately
not opened to config fields or to the Terraform/Ansible bridges.

Provider settings resolve at each consumer, never when the environment config loads, so ``bw``
starts only when a bitwarden URI is actually resolved. :func:`resolved_provider_settings` and
:func:`with_resolved_provider_settings` hand a reader resolved copies; the original, possibly
cached, ``EnvironmentConfig`` is never changed. :func:`provider_settings_secret_problems` is the
offline counterpart for readers that only check presence or shape.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from infrafoundry.core.provider_instances import split_provider_id
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


def _contains_secret_uri(value: Any) -> bool:
    """Return True when ``value`` holds a ``secret://`` string at any depth."""
    if isinstance(value, str):
        return is_secret_uri(value)
    if isinstance(value, Mapping):
        return any(_contains_secret_uri(v) for v in value.values())
    if isinstance(value, list | tuple):
        return any(_contains_secret_uri(v) for v in value)
    return False


def resolve_secret_settings(
    env_config: EnvironmentConfig, settings: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """Return a copy of ``settings`` with every ``secret://`` URI resolved, in memory only.

    A mapping without a URI is deep-copied and no resolver is built, so no vault is contacted.

    Args:
        env_config: The environment, with its decrypted ``secrets`` populated.
        settings: Any settings mapping, or ``None``.

    Returns:
        A new dict, or ``None`` when ``settings`` is ``None``.

    Raises:
        SecretResolutionError: If a URI cannot be resolved. The message names the URI, never
            a value.
    """
    if settings is None:
        return None
    if not _contains_secret_uri(settings):
        return copy.deepcopy(dict(settings))
    resolver = build_secret_resolver(env_config)
    try:
        return resolver.resolve_config(dict(settings))
    finally:
        resolver.close()


def resolved_provider_settings(
    env_config: EnvironmentConfig, provider_name: str
) -> dict[str, Any] | None:
    """Return ``provider_settings[<base>]`` with its ``secret://`` URIs resolved.

    ``opnsense@fw-b`` reads the ``opnsense`` block. Values nested under ``firewalls:`` and
    ``clusters:`` are covered.

    Returns:
        The resolved settings, or ``None`` when the provider has no settings.

    Raises:
        SecretResolutionError: If a URI cannot be resolved.
    """
    base, _ = split_provider_id(provider_name)
    raw = (env_config.provider_settings or {}).get(base)
    if raw is None:
        return None
    return resolve_secret_settings(env_config, raw)


def with_resolved_provider_settings(
    env_config: EnvironmentConfig, provider_name: str
) -> EnvironmentConfig:
    """Return a copy of ``env_config`` whose ``provider_settings[<base>]`` is resolved.

    The original object, which a ``ConfigManager`` may have cached, is not changed.

    Raises:
        SecretResolutionError: If a URI cannot be resolved.
    """
    base, _ = split_provider_id(provider_name)
    resolved = resolved_provider_settings(env_config, base)
    if resolved is None:
        return env_config.model_copy()
    settings = {**(env_config.provider_settings or {}), base: resolved}
    return env_config.model_copy(update={"provider_settings": settings})


def resolved_environment_data(env_config: EnvironmentConfig, provider_name: str) -> dict[str, Any]:
    """Return ``env_config.model_dump()`` with the provider's settings secret-resolved.

    For consumers that take the environment as plain data (the Proxmox exporter and dumper).

    Raises:
        SecretResolutionError: If a URI cannot be resolved.
    """
    base, _ = split_provider_id(provider_name)
    data: dict[str, Any] = env_config.model_dump()
    settings = data.get("provider_settings") or {}
    resolved = resolve_secret_settings(env_config, settings.get(base))
    if resolved is not None:
        data["provider_settings"] = {**settings, base: resolved}
    return data


def provider_settings_secret_problems(
    env_config: EnvironmentConfig, provider_name: str, *, check_presence: bool = True
) -> list[str]:
    """Check the provider's settings URIs offline: shape and configured backend only.

    With ``check_presence`` False an ``env_secrets`` path is not looked up either.

    Returns:
        Messages ``provider_settings.<base>.<path>: '<uri>': <problem>``; never a value.
    """
    base, _ = split_provider_id(provider_name)
    raw = (env_config.provider_settings or {}).get(base)
    if not raw:
        return []
    problems: list[str] = []
    lookup = SecretRefLookup(env_config)

    def walk(node: Any, path: str) -> None:
        if isinstance(node, str):
            if is_secret_uri(node):
                reason = lookup.problem(node, check_presence=check_presence)
                if reason is not None:
                    problems.append(f"provider_settings.{path}: '{node}': {reason}")
        elif isinstance(node, Mapping):
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list | tuple):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(raw, base)
    lookup.close()
    return problems


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

    def problem(self, ref: str, *, check_presence: bool = True) -> str | None:
        """Return why ``ref`` cannot resolve, checked offline, or ``None`` when it looks fine.

        A ``bitwarden`` URI is checked for shape and a configured backend only; the vault is
        queried at apply time. With ``check_presence`` False an ``env_secrets`` URI is checked
        for shape and backend only, not for the path in the decrypted secrets.
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
            if not check_presence:
                return None
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
