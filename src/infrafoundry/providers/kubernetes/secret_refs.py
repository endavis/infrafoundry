"""Secret-backed values for the Kubernetes provider.

A ``secrets`` resource takes ``string_data_secrets`` and ``data_secrets`` maps (key to dotted
secret ref), and a ``helm_releases`` ``set_sensitive`` entry takes ``value_secret`` instead of
``value``. These helpers fold those refs into the resource's ``terraform_secrets`` list, so the
framework's existing secrets-to-``TF_VAR_*`` bridge declares and injects them. Pure functions,
no I/O.
"""

from __future__ import annotations

import copy
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_mixins import is_output_ref

SECRET_MAP_FIELDS: tuple[str, ...] = ("string_data_secrets", "data_secrets")

# Literal map each ``*_secrets`` map must not share a key with.
_LITERAL_SIBLINGS: dict[str, str] = {
    "string_data_secrets": "string_data",
    "data_secrets": "data",
}


def _secret_map(config: dict[str, Any], field: str) -> dict[str, Any]:
    value = config.get(field)
    return value if isinstance(value, dict) else {}


def _set_sensitive_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    entries = config.get("set_sensitive")
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]


def collect_value_secret_refs(resource: ResourceConfig) -> list[str]:
    """Return the ordered secret refs a resource's value-secret fields name.

    Args:
        resource: Resource to scan.

    Returns:
        Refs from ``string_data_secrets`` and ``data_secrets`` (``secrets`` type) and from
        every ``set_sensitive[*].value_secret`` (``helm_releases`` type), in order.
    """
    config = resource.config or {}
    refs: list[str] = []
    if resource.type == "secrets":
        for field in SECRET_MAP_FIELDS:
            refs.extend(r for r in _secret_map(config, field).values() if isinstance(r, str))
    elif resource.type == "helm_releases":
        refs.extend(
            e["value_secret"]
            for e in _set_sensitive_entries(config)
            if isinstance(e.get("value_secret"), str)
        )
    return refs


def with_terraform_secrets(resource: ResourceConfig) -> ResourceConfig:
    """Return a deep copy whose ``terraform_secrets`` also lists the value-secret refs.

    The input resource is not changed. Existing ``terraform_secrets`` entries come first;
    the result is de-duplicated in order.

    Args:
        resource: Resource to process.

    Returns:
        A copy with the merged ``config["terraform_secrets"]``.

    Raises:
        TypeError: If an existing ``terraform_secrets`` value is not a list.
    """
    copied = copy.deepcopy(resource)
    refs = collect_value_secret_refs(copied)
    existing = copied.config.get("terraform_secrets")
    if existing is not None and not isinstance(existing, list):
        raise TypeError(
            f"Resource '{resource.name}' has a non-list "
            f"terraform_secrets value: {type(existing).__name__}"
        )
    if not refs:
        return copied
    merged: dict[Any, None] = dict.fromkeys(existing or [])
    merged.update(dict.fromkeys(refs))
    copied.config["terraform_secrets"] = list(merged)
    return copied


def shape_errors(resource: ResourceConfig) -> list[str]:
    """Return messages for malformed value-secret fields on a resource.

    Args:
        resource: Resource to inspect.

    Returns:
        One message per problem; empty when the fields are well formed.
    """
    config = resource.config or {}
    errors: list[str] = []
    if resource.type == "secrets":
        for field in SECRET_MAP_FIELDS:
            if field not in config:
                continue
            mapping = config[field]
            if not isinstance(mapping, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()
            ):
                errors.append(
                    f"Secret '{resource.name}' '{field}' must map keys to dotted secret "
                    f"reference strings"
                )
                continue
            if field == "data_secrets":
                errors.extend(
                    f"Secret '{resource.name}' key '{key}' in 'data_secrets' uses an outputs "
                    f"reference; outputs are not base64, use 'string_data_secrets'"
                    for key, ref in mapping.items()
                    if is_output_ref(ref)
                )
            literal = config.get(_LITERAL_SIBLINGS[field])
            if isinstance(literal, dict):
                for key in mapping:
                    if key in literal:
                        errors.append(
                            f"Secret '{resource.name}' key '{key}' is in both "
                            f"'{_LITERAL_SIBLINGS[field]}' and '{field}'"
                        )
    elif resource.type == "helm_releases":
        for entry in _set_sensitive_entries(config):
            name = entry.get("name", "?")
            has_value = "value" in entry
            has_ref = "value_secret" in entry
            if has_value == has_ref:
                errors.append(
                    f"Helm release '{resource.name}' set_sensitive '{name}' needs exactly "
                    f"one of 'value' or 'value_secret'"
                )
            elif has_ref and not isinstance(entry["value_secret"], str):
                errors.append(
                    f"Helm release '{resource.name}' set_sensitive '{name}' "
                    f"'value_secret' must be a dotted secret reference string"
                )
    return errors
