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
