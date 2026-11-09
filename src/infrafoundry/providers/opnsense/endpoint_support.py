"""Check the endpoints a resource type needs against an OPNsense version (#1239).

The check reads the specs bundled with ``opnsense-openapi``; it never calls the box
except to read its version in :func:`check_box`. ``interfaces/assign_settings/*``
(``EndpointKind.EXTENSION``) is skipped because stock OPNsense does not serve it, and so
is every ``acmeclient/*`` endpoint (``EndpointKind.PLUGIN``, #790): the specs cover core
only and the ``os-acme-client`` plugin is installed by ``system.firmware``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from opnsense_openapi import endpoint_exists, is_version_covered, newest_spec_version

from infrafoundry.core.exceptions import APIError

from . import endpoints
from .api_client import OPNsenseClient

logger = logging.getLogger(__name__)


@dataclass
class EndpointSupport:
    """Result of an endpoint-support check.

    Attributes:
        version: The OPNsense version checked, or ``None`` when it could not be read.
        errors: Resource types whose endpoints the version lacks.
        warnings: Reasons the check was skipped or approximate.
    """

    version: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_resource_types(version: str, resource_types: Iterable[str]) -> EndpointSupport:
    """Check that each resource type's endpoints exist in the spec for ``version``.

    Args:
        version: OPNsense version (e.g. ``"26.1.6_2"``).
        resource_types: Resource type keys, e.g. ``"firewall.rules"``. Types absent
            from the registry are ignored; duplicates are checked once.

    Returns:
        An :class:`EndpointSupport` with one error per missing ``(type, endpoint)``.
    """
    result = EndpointSupport(version=version)
    types = [t for t in dict.fromkeys(resource_types) if t in endpoints.RESOURCE_TYPE_ENDPOINTS]
    if not types:
        return result

    if not is_version_covered(version):
        try:
            newest = newest_spec_version()
        except FileNotFoundError:  # pragma: no cover - the package always bundles specs
            newest = "unknown"
        result.warnings.append(
            f"OPNsense {version} has no bundled opnsense-openapi spec (newest is {newest}); "
            "checking endpoints against the nearest older spec"
        )

    try:
        for resource_type in types:
            for endpoint in endpoints.RESOURCE_TYPE_ENDPOINTS[resource_type]:
                if endpoint.kind is not endpoints.EndpointKind.STOCK:
                    continue
                if not endpoint_exists(endpoint.sample_path(), endpoint.method, version=version):
                    result.errors.append(
                        f"opnsense resource type '{resource_type}' needs {endpoint}, "
                        f"which OPNsense {version} does not serve (opnsense-openapi spec)"
                    )
    except FileNotFoundError:
        return EndpointSupport(
            version=version,
            warnings=[
                f"no opnsense-openapi spec covers OPNsense {version}; endpoint check skipped"
            ],
        )
    return result


def check_box(client: OPNsenseClient, resource_types: Iterable[str]) -> EndpointSupport:
    """Read the box's version and check the resource types against it.

    Args:
        client: Client for the box to check.
        resource_types: Resource type keys in scope. Nothing is called when empty.

    Returns:
        The check result; a warning (and no errors) when the version cannot be read.
    """
    types = list(resource_types)
    if not types:
        return EndpointSupport()
    try:
        version = client.detect_version()
    except APIError as exc:
        logger.warning("Could not read the OPNsense version: %s", exc)
        return EndpointSupport(
            warnings=["could not read the OPNsense version; endpoint check skipped"]
        )
    return check_resource_types(version, types)
