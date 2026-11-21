"""Secret sources for ``infra doctor`` (#1567).

Lists, for the resources a scoped ``infra doctor`` run covers, where each secret reference
resolves from: the owning package's ``secrets.yaml`` (``package.<key>``), another provider's
Terraform outputs at apply time (``outputs.<provider>.<output>``), or the environment's
``secrets.yaml``. Rows hold the reference and its source, never a secret value.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from rich.markup import escape

from infrafoundry.core.package_secret_refs import is_package_ref, package_ref_problem
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_instances import split_provider_id
from infrafoundry.core.provider_mixins import is_output_ref
from infrafoundry.core.secrets.secret_manager import DEFAULT_SECRETS_FILENAME, SecretManager
from infrafoundry.core.terraform_outputs import parse_output_ref
from infrafoundry.core.validation_helpers.terraform_secrets_validator import output_ref_problem
from infrafoundry.providers.kubernetes.secret_refs import SECRET_MAP_FIELDS, shape_errors

from ...utils import console

_KUBERNETES = "kubernetes"
_NONE = "-"


class SourceStatus(StrEnum):
    """Whether a secret reference resolves."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    APPLY_TIME = "apply_time"


@dataclass(frozen=True)
class SecretSourceRow:
    """One secret reference of one resource and where it resolves from.

    Holds no secret value, only the reference and its source.
    """

    resource: str
    provider: str
    field: str
    ref: str
    source: str
    status: SourceStatus
    reason: str | None = None


_SYMBOL = {
    SourceStatus.RESOLVED: ("green", "✓"),
    SourceStatus.UNRESOLVED: ("red", "✗"),
    SourceStatus.APPLY_TIME: ("dim", "-"),
}


def _unresolved(
    resource: ResourceConfig, field: str, ref: str, reason: str, source: str = _NONE
) -> SecretSourceRow:
    return SecretSourceRow(
        resource.name, resource.provider, field, ref, source, SourceStatus.UNRESOLVED, reason
    )


def _collect_fields(
    resource: ResourceConfig,
) -> tuple[list[tuple[str, str]], list[SecretSourceRow]]:
    """Return ``(field, ref)`` pairs to classify, and rows for malformed fields."""
    config = resource.config or {}
    pairs: list[tuple[str, str]] = []
    bad: list[SecretSourceRow] = []

    refs = config.get("terraform_secrets")
    if refs is not None and not isinstance(refs, list):
        bad.append(
            _unresolved(
                resource,
                "terraform_secrets",
                _NONE,
                f"Resource '{resource.name}' has a non-list terraform_secrets value: "
                f"{type(refs).__name__}",
            )
        )
    elif isinstance(refs, list):
        for i, ref in enumerate(refs):
            field = f"terraform_secrets[{i}]"
            if isinstance(ref, str):
                pairs.append((field, ref))
            else:
                bad.append(
                    _unresolved(
                        resource,
                        field,
                        f"<non-string: {type(ref).__name__}>",
                        f"Resource '{resource.name}' terraform_secrets entry {i} is not a string",
                    )
                )

    if split_provider_id(resource.provider)[0] != _KUBERNETES:
        return pairs, bad
    errors = shape_errors(resource)
    if errors:
        bad.extend(_unresolved(resource, f"{resource.type} fields", _NONE, m) for m in errors)
    elif resource.type == "secrets":
        for map_field in SECRET_MAP_FIELDS:
            mapping = config.get(map_field)
            if isinstance(mapping, dict):
                pairs.extend((f"{map_field}.{k}", v) for k, v in mapping.items())
    elif resource.type == "helm_releases":
        entries = config.get("set_sensitive")
        if isinstance(entries, list):
            for i, entry in enumerate(entries):
                if isinstance(entry, dict) and isinstance(entry.get("value_secret"), str):
                    pairs.append((f"set_sensitive[{i}].value_secret", entry["value_secret"]))
    return pairs, bad


def collect_secret_sources(
    resources: list[ResourceConfig],
    env_name: str,
    env_secrets: Callable[[], dict[str, Any] | None],
) -> list[SecretSourceRow]:
    """Return one row per secret reference of the given resources.

    Args:
        resources: Resources in scope.
        env_name: Environment name, used to build source paths.
        env_secrets: Loader for the environment's secrets dict. Called at most once, and
            only when a reference falls back to the environment's secrets file.

    Returns:
        Rows in resource order; never holds a secret value.
    """
    flat: dict[str, str] | None = None
    rows: list[SecretSourceRow] = []
    for resource in resources:
        pairs, bad = _collect_fields(resource)
        rows.extend(bad)
        for field, ref in pairs:
            if is_package_ref(ref):
                source = (
                    f"envs/{env_name}/{resource.package_path}/{DEFAULT_SECRETS_FILENAME}"
                    if resource.package_path
                    else _NONE
                )
                problem = package_ref_problem(resource, ref)
                if problem is not None:
                    rows.append(_unresolved(resource, field, ref, problem, source))
                else:
                    rows.append(
                        SecretSourceRow(
                            resource.name,
                            resource.provider,
                            field,
                            ref,
                            source,
                            SourceStatus.RESOLVED,
                        )
                    )
            elif is_output_ref(ref):
                base = split_provider_id(resource.provider)[0]
                problem = output_ref_problem(base, ref, base == _KUBERNETES)
                if problem is not None:
                    rows.append(_unresolved(resource, field, ref, problem))
                else:
                    rows.append(
                        SecretSourceRow(
                            resource.name,
                            resource.provider,
                            field,
                            ref,
                            f"outputs of {parse_output_ref(ref).provider} (apply time)",
                            SourceStatus.APPLY_TIME,
                        )
                    )
            else:
                if flat is None:
                    flat = SecretManager.flatten_dict(env_secrets())
                source = f"envs/{env_name}/{DEFAULT_SECRETS_FILENAME}"
                if ref in flat:
                    rows.append(
                        SecretSourceRow(
                            resource.name,
                            resource.provider,
                            field,
                            ref,
                            source,
                            SourceStatus.RESOLVED,
                        )
                    )
                else:
                    reason = (
                        f"Resource '{resource.name}' references unknown secret key '{ref}'. "
                        f"Ensure each dotted path exists in the env's secrets file."
                    )
                    rows.append(_unresolved(resource, field, ref, reason, source))
    return rows


def print_secret_sources(rows: list[SecretSourceRow], scope_label: str) -> None:
    """Print the secret-sources section of ``infra doctor``.

    Args:
        rows: Rows from :func:`collect_secret_sources`.
        scope_label: Description of the scope, e.g. ``package example-app``.
    """
    console.print(f"\n[bold]Secret sources ({escape(scope_label)}):[/bold]", highlight=False)
    if not rows:
        console.print("  no secret references", highlight=False)
    for row in rows:
        style, symbol = _SYMBOL[row.status]
        line = (
            f"  [{style}]{symbol}[/{style}] {escape(row.resource)} {escape(row.field)} "
            f"{escape(row.ref)} -> {escape(row.source)}"
        )
        if row.reason:
            line += f": {escape(row.reason)}"
        console.print(line, highlight=False)
    counts = [
        (sum(r.status is SourceStatus.RESOLVED for r in rows), "resolved"),
        (sum(r.status is SourceStatus.APPLY_TIME for r in rows), "at apply time"),
        (sum(r.status is SourceStatus.UNRESOLVED for r in rows), "unresolved"),
    ]
    summary = ", ".join(f"{n} {label}" for n, label in counts if n)
    if summary:
        console.print(f"Secret sources: {escape(summary)}", highlight=False)


def secret_sources_json(rows: list[SecretSourceRow], scope_label: str) -> dict[str, Any]:
    """Return the JSON-serializable form of the secret sources.

    Args:
        rows: Rows from :func:`collect_secret_sources`.
        scope_label: Description of the scope.

    Returns:
        ``{"scope": ..., "rows": [...]}`` with each row's status as its string value.
    """
    return {
        "scope": scope_label,
        "rows": [
            {
                "resource": r.resource,
                "provider": r.provider,
                "field": r.field,
                "ref": r.ref,
                "source": r.source,
                "status": r.status.value,
                "reason": r.reason,
            }
            for r in rows
        ],
    }
