"""CARP VIP status for OPNsense, read-only (#1393).

``GET diagnostics/interface/getVipStatus`` returns (shape probed on a single node
with no CARP VIPs; wording generic):

- ``rows``: one object per CARP VIP with ``interface``, ``vhid``, ``advbase``,
  ``advskew``, ``subnet``, ``status`` (``MASTER``, ``BACKUP``, ``INIT`` or
  ``DISABLED``), ``mode`` and ``vhid_txt``.
- ``carp``: ``demotion``, ``allow``, ``maintenancemode`` and ``status_msg``.

``diagnostics/interface/carpStatus/*`` is a WRITE (it changes the node's CARP
state). Nothing here may call it.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.exceptions import APIError

from .. import endpoints
from .base import BaseService

VipKey = tuple[str, str]


def _text(value: Any) -> str:
    """Return ``value`` as a stripped string, ``""`` for ``None``."""
    return "" if value is None else str(value).strip()


def vip_key(row: dict[str, Any]) -> VipKey:
    """Return the ``(vhid, subnet)`` key that identifies a CARP VIP row."""
    return (_text(row.get("vhid")), _text(row.get("subnet")))


def carp_vip_keys(status: dict[str, Any]) -> set[VipKey]:
    """Return the ``(vhid, subnet)`` keys of every VIP row in a status document.

    Non-dict rows and a non-list ``rows`` value are ignored.
    """
    rows = status.get("rows")
    if not isinstance(rows, list):
        return set()
    return {vip_key(row) for row in rows if isinstance(row, dict)}


def missing_carp_vips(primary: dict[str, Any], backup: dict[str, Any]) -> list[VipKey]:
    """Return the primary's CARP VIP keys that are absent on the backup, sorted."""
    return sorted(carp_vip_keys(primary) - carp_vip_keys(backup))


class CarpStatusService(BaseService):
    """Service for the read-only CARP VIP status."""

    def vip_status(self) -> dict[str, Any]:
        """Fetch the CARP VIP status document.

        Returns:
            The reply, with ``rows`` and ``carp`` keys.

        Raises:
            APIError: If the reply is not an object.
        """
        ep = endpoints.DIAGNOSTICS_VIP_STATUS
        response = self.client.request(ep.method, ep.path())
        if not isinstance(response, dict):
            raise APIError(
                f"OPNsense {ep.path()} returned an unexpected reply",
                response="",
                provider="opnsense",
            )
        return response
