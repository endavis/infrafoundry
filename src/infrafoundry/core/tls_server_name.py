"""A ``requests`` adapter that validates a device certificate against a fixed host name.

Devices are reached by an address (often an IP literal) while their Let's Encrypt
certificate names a DNS name. Shared by the providers that install certificates over their
own API (MikroTik #1683, ONTAP #1684).
"""

from __future__ import annotations

from typing import Any

from requests.adapters import HTTPAdapter


class ServerNameAdapter(HTTPAdapter):
    """Send SNI and check the certificate's host name against a fixed name, not the URL host."""

    def __init__(self, server_name: str) -> None:
        """Initialize the adapter.

        Args:
            server_name: The host name for SNI and the host name check.
        """
        self._server_name = server_name
        super().__init__()

    def init_poolmanager(
        self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any
    ) -> None:
        """Create the pool manager with the fixed server name for SNI and host name checks."""
        super().init_poolmanager(
            connections,
            maxsize,
            block=block,
            server_hostname=self._server_name,
            assert_hostname=self._server_name,
            **pool_kwargs,
        )
