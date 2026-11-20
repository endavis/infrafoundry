"""Compartment reference resolution for the OCI provider.

A ``compartment`` or ``parent`` field holds either an OCID or the name of a
``compartment`` resource in the environment. The provider and the validator
share these helpers so both resolve a reference the same way.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable

from infrafoundry.core.exceptions import ConfigurationError
from infrafoundry.core.provider import ResourceConfig

DEFAULT_COMPARTMENT_EXPR = "var.oci_compartment_ocid"
DEFAULT_PARENT_EXPR = "var.oci_tenancy_ocid"

_OCID_PREFIX = "ocid1."


def is_ocid(value: str) -> bool:
    """Return True when ``value`` looks like an OCID rather than a resource name."""
    return value.startswith(_OCID_PREFIX)


def terraform_name(name: str) -> str:
    """Return the Terraform resource name used for an InfraFoundry resource name."""
    return str(name).replace("-", "_")


def _resolve(
    ref: str | None,
    compartment_names: Collection[str],
    default: str,
    *,
    field: str,
) -> str:
    if not ref:
        return default
    if is_ocid(ref):
        return f'"{ref}"'
    if ref in compartment_names:
        return f"oci_identity_compartment.{terraform_name(ref)}.id"
    raise ConfigurationError(
        f"OCI {field} '{ref}' is neither an OCID nor a defined compartment resource"
    )


def compartment_id_expr(ref: str | None, compartment_names: Collection[str]) -> str:
    """Return the Terraform expression for a resource's ``compartment`` field.

    Args:
        ref: A compartment resource name, an OCID, or None.
        compartment_names: Names of the compartment resources in scope.

    Returns:
        ``var.oci_compartment_ocid`` without a reference, a quoted literal for an
        OCID, or ``oci_identity_compartment.<name>.id`` for a resource name.

    Raises:
        ConfigurationError: If ``ref`` is a name that is not in ``compartment_names``.
    """
    return _resolve(ref, compartment_names, DEFAULT_COMPARTMENT_EXPR, field="compartment")


def parent_id_expr(ref: str | None, compartment_names: Collection[str]) -> str:
    """Return the Terraform expression for a compartment's ``parent`` field.

    Same as :func:`compartment_id_expr`, but the default is the tenancy root.

    Raises:
        ConfigurationError: If ``ref`` is a name that is not in ``compartment_names``.
    """
    return _resolve(ref, compartment_names, DEFAULT_PARENT_EXPR, field="parent")


def find_parent_cycles(compartments: Iterable[ResourceConfig]) -> set[str]:
    """Return the names of compartments that sit on a ``parent`` cycle.

    A parent that is an OCID or an unknown name ends the chain and is not a cycle.
    """
    parents: dict[str, str] = {}
    for comp in compartments:
        parent = comp.config.get("parent")
        parents[comp.name] = parent if isinstance(parent, str) else ""

    on_cycle: set[str] = set()
    for start in parents:
        seen: list[str] = []
        current = start
        while current in parents and current not in seen:
            seen.append(current)
            current = parents[current]
        if current in seen:
            on_cycle.update(seen[seen.index(current) :])
    return on_cycle
