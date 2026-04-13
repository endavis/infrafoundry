"""Custom Jinja2 filters for InfraFoundry configuration rendering.

Provides unit-conversion and formatting filters for blueprint templates,
plus a factory function that creates a Jinja2 environment with all filters
pre-registered.
"""

from __future__ import annotations

import hashlib
from typing import Any

import jinja2


def generate_mac(value: str) -> str:
    """Generate a deterministic locally-administered MAC address from a string.

    Uses SHA-256 to hash the input, then formats the first 5 bytes as a
    MAC address with a fixed ``02`` first octet (locally administered,
    unicast).

    Args:
        value: Input string to derive the MAC address from.

    Returns:
        MAC address in the format ``02:xx:xx:xx:xx:xx``.
    """
    digest = hashlib.sha256(value.encode()).digest()
    return "02:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}".format(*digest[:5])


def to_mib(value: int | float | str) -> int:
    """Convert GB to MiB.

    Args:
        value: Size in GB.

    Returns:
        Size in MiB as an integer.
    """
    return int(float(value) * 1024)


def to_gib(value: int | float | str) -> float:
    """Convert MiB to GiB.

    Args:
        value: Size in MiB.

    Returns:
        Size in GiB as a float.
    """
    return float(value) / 1024


def to_gb(value: int | float | str) -> float:
    """Convert MiB to GB (alias for ``to_gib``).

    Args:
        value: Size in MiB.

    Returns:
        Size in GiB as a float.
    """
    return to_gib(value)


def bool_to_tf(value: Any) -> str:
    """Convert a value to a Terraform boolean string.

    Truthy values produce ``"true"``, falsy values produce ``"false"``.

    Args:
        value: Any value that can be evaluated for truthiness.

    Returns:
        ``"true"`` or ``"false"``.
    """
    return "true" if value else "false"


def cidr_ip(value: str) -> str:
    """Extract the IP address from a CIDR notation string.

    Args:
        value: CIDR string (e.g., ``"10.0.0.1/24"``).

    Returns:
        The IP portion (e.g., ``"10.0.0.1"``).
    """
    return value.split("/")[0]


def cidr_prefix(value: str) -> str:
    """Extract the prefix length from a CIDR notation string.

    Args:
        value: CIDR string (e.g., ``"10.0.0.1/24"``).

    Returns:
        The prefix length as a string (e.g., ``"24"``).
    """
    return value.split("/")[1]


# Registry of all custom filters. New filters should be added here.
_FILTERS: dict[str, Any] = {
    "generate_mac": generate_mac,
    "to_mib": to_mib,
    "to_gib": to_gib,
    "to_gb": to_gb,
    "bool_to_tf": bool_to_tf,
    "cidr_ip": cidr_ip,
    "cidr_prefix": cidr_prefix,
}


def create_jinja2_env(
    undefined: type[jinja2.Undefined] | None = None,
) -> jinja2.Environment:
    """Create a Jinja2 environment with all InfraFoundry filters registered.

    Centralizes filter registration so new filters only need to be added
    to the ``_FILTERS`` dict above.

    Args:
        undefined: Jinja2 undefined class to use. Defaults to
            ``jinja2.Undefined`` (permissive) when ``None``.

    Returns:
        Configured Jinja2 environment with all filters registered.
    """
    if undefined is None:
        undefined = jinja2.Undefined

    env = jinja2.Environment(undefined=undefined)  # nosec B701
    env.filters.update(_FILTERS)
    return env
