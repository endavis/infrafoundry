"""Package-scoped secret references (``package.<key>``).

A ``package.``-prefixed secret reference resolves against the ``variables:`` of the
``secrets.yaml`` in the package that defines the resource, and nothing else. It never
falls back to the environment's secrets file and never reaches another package.

The helpers here are pure (no I/O): the loader attaches the raw ``secrets.yaml``
variables to each resource, and these functions read them from there. Messages name the
resource, the ref and the package, never a secret value.
"""

from __future__ import annotations

import re

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.secrets.secret_manager import SecretManager

#: Reserved prefix of a secret reference that names the owning package's ``secrets.yaml``.
PACKAGE_REF_PREFIX = "package."

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def is_package_ref(ref: str) -> bool:
    """Return True if a secret reference carries the reserved ``package.`` prefix."""
    return ref.startswith(PACKAGE_REF_PREFIX)


def package_ref_key(ref: str) -> str:
    """Return the key part of a ``package.<key>`` reference (may be empty or dotted)."""
    return ref[len(PACKAGE_REF_PREFIX) :]


def package_var_slug(package_path: str) -> str:
    """Return a Terraform-safe slug of a package path.

    The path is lowercased and every run of non-alphanumeric characters becomes ``_``.

    Args:
        package_path: Package directory relative to ``envs/<env>``, e.g.
            ``kubernetes/example-app``.

    Returns:
        The slug, e.g. ``kubernetes_example_app``.
    """
    return _NON_ALNUM_RE.sub("_", package_path.lower()).strip("_")


def package_secret_var_name(package_path: str, key: str) -> str:
    """Return the Terraform variable name for a package secret key.

    Args:
        package_path: Package directory relative to ``envs/<env>``.
        key: The key part of the ``package.<key>`` reference.

    Returns:
        ``package_<slug(package_path)>_<sanitized key>``.
    """
    sanitized_key = _NON_ALNUM_RE.sub("_", key.lower()).strip("_")
    return f"package_{package_var_slug(package_path)}_{sanitized_key}"


def _describe(resource: ResourceConfig) -> str:
    package = resource.package_name or resource.package_path
    where = f"package '{package}' ({resource.package_path})" if package else "no package"
    return f"resource '{resource.name}' ({where})"


def package_ref_problem(resource: ResourceConfig, ref: str) -> str | None:
    """Return why a ``package.`` reference cannot be resolved, or None when it can.

    Args:
        resource: The resource that carries the reference.
        ref: A reference starting with ``package.``.

    Returns:
        A message naming the resource, ref and package (never a value), or None.
    """
    if resource.package_path is None:
        return (
            f"Secret reference '{ref}' on resource '{resource.name}' needs a package: "
            f"'{PACKAGE_REF_PREFIX}' references resolve from the secrets.yaml of the package "
            f"that defines the resource, and this resource does not come from a package"
        )
    key = package_ref_key(ref)
    if not key:
        return f"Secret reference '{ref}' on {_describe(resource)} has an empty key"
    if resource.package_secrets is None:
        return f"Secret reference '{ref}' on {_describe(resource)}: the package has no secrets.yaml"
    flat = SecretManager.flatten_dict(resource.package_secrets)
    if key not in flat:
        return (
            f"Secret reference '{ref}' on {_describe(resource)}: key '{key}' is not in the "
            f"package's secrets.yaml variables. Available keys: {sorted(flat)}"
        )
    return None


def resolve_package_secret(resource: ResourceConfig, ref: str) -> str:
    """Resolve a ``package.<key>`` reference from the resource's own package.

    Args:
        resource: The resource that carries the reference.
        ref: A reference starting with ``package.``.

    Returns:
        The secret value as a string.

    Raises:
        KeyError: If the reference cannot be resolved. The message never holds a value.
    """
    problem = package_ref_problem(resource, ref)
    if problem is not None:
        raise KeyError(problem)
    flat = SecretManager.flatten_dict(resource.package_secrets)
    return flat[package_ref_key(ref)]
