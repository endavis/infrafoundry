"""Minimal RouterOS REST client (RouterOS 7 and later).

Reads, ``/rest/execute`` and the write verbs are implemented here: PUT creates, PATCH
updates and DELETE removes a row. Error messages and logs never carry request bodies
or credentials.
"""

from __future__ import annotations

from typing import Any, Protocol

import requests
from requests.adapters import HTTPAdapter

from infrafoundry.core.exceptions import InfraFoundryError

from .settings import MikroTikSettings


class RouterOSAPIError(InfraFoundryError):
    """RouterOS answered with an error status. Carries the status and message, no credentials."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Initialize the error.

        Args:
            message: RouterOS's message and detail.
            status_code: HTTP status code.
        """
        super().__init__(message, {"status_code": status_code} if status_code else None)
        self.status_code = status_code


class RouterOSConnectionError(InfraFoundryError):
    """The device could not be reached."""


class RouterOSReader(Protocol):
    """What planning needs from a RouterOS client (the tests substitute a fake)."""

    def get(self, path: str) -> list[dict[str, str]]:
        """Return the rows under a REST path."""
        ...

    def execute(self, script: str) -> str:
        """Run a script on the device and return its output."""
        ...


class RouterOSWriter(RouterOSReader, Protocol):
    """What apply needs from a RouterOS client: the reads plus the write verbs."""

    def put(self, path: str, body: dict[str, str]) -> dict[str, str]:
        """Create a row under a REST path and return it (with its ``.id``)."""
        ...

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """Call an action endpoint under a REST path and return the decoded reply."""
        ...

    def patch(self, path: str, row_id: str, body: dict[str, str]) -> dict[str, str]:
        """Update the row ``row_id`` under a REST path and return it."""
        ...

    def delete(self, path: str, row_id: str) -> None:
        """Delete the row ``row_id`` under a REST path."""
        ...


class _ServerNameAdapter(HTTPAdapter):
    """Send SNI and check the certificate's host name against a fixed name, not the URL host.

    The device is reached by an address (often an IP literal) while its Let's Encrypt
    certificate names a DNS name.
    """

    def __init__(self, server_name: str) -> None:
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


class RouterOSClient:
    """REST client over a ``requests.Session`` with HTTP basic auth.

    ``verify_ssl`` alone decides certificate checking, except once the device holds an
    installed Let's Encrypt production certificate (``settings.tls_server_name``, #1683):
    then the CA chain and that host name are always checked.
    """

    def __init__(self, settings: MikroTikSettings) -> None:
        """Initialize the client.

        Args:
            settings: Connection settings (the password stays inside the session auth).
        """
        self._base = f"{settings.api_url.rstrip('/')}/rest/"
        self._timeout = settings.timeout
        self._session = requests.Session()
        self._session.auth = (settings.username, settings.password)
        self._session.verify = settings.verify_ssl
        self._validated = settings.tls_server_name is not None and settings.scheme == "https"
        if self._validated and settings.tls_server_name:
            self._session.verify = True
            self._session.mount(
                settings.api_url.rstrip("/"), _ServerNameAdapter(settings.tls_server_name)
            )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Send one request and return the decoded JSON body (``None`` for an empty body).

        Raises:
            RouterOSConnectionError: On a transport failure.
            RouterOSAPIError: On a non-success status.
        """
        url = self._base + path.strip("/")
        try:
            response = self._session.request(method, url, timeout=self._timeout, **kwargs)
        except requests.exceptions.SSLError as exc:
            if self._validated:
                raise RouterOSConnectionError(
                    f"The certificate RouterOS presented at {self._base} failed validation "
                    "(CA chain or host name). If the installed certificate is wrong or "
                    "expired, restore a working one on the device console, for example "
                    "'/ip service set api-ssl,www-ssl certificate=<name>', then run "
                    "'foundry certs issue' again."
                ) from exc
            raise RouterOSConnectionError(
                f"Could not reach RouterOS at {self._base}: {type(exc).__name__}"
            ) from exc
        except requests.RequestException as exc:
            raise RouterOSConnectionError(
                f"Could not reach RouterOS at {self._base}: {type(exc).__name__}"
            ) from exc
        if response.status_code >= 400:
            raise RouterOSAPIError(self._error_text(response, path), response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    @staticmethod
    def _error_text(response: requests.Response, path: str) -> str:
        """Build an error message from RouterOS's ``message``/``detail`` body."""
        text = f"RouterOS returned {response.status_code} for {path}"
        try:
            body = response.json()
        except ValueError:
            return text
        if isinstance(body, dict):
            parts = [str(body[k]) for k in ("message", "detail") if body.get(k)]
            if parts:
                text += ": " + " - ".join(parts)
        return text

    def get(self, path: str) -> list[dict[str, str]]:
        """Return the rows under ``path``; a single-object response is wrapped in a list.

        Args:
            path: REST path without the ``/rest/`` prefix, e.g. ``interface/bridge``.
        """
        data = self._request("GET", path)
        if data is None:
            return []
        if isinstance(data, dict):
            return [data]
        return list(data)

    def execute(self, script: str) -> str:
        """Run a console script through ``/rest/execute`` and return its output.

        Args:
            script: RouterOS script text.
        """
        data = self._request("POST", "execute", json={"script": script, "as-string": True})
        return str(data.get("ret", "")) if isinstance(data, dict) else ""

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """Call an action endpoint with ``POST`` and return the decoded JSON reply.

        Args:
            path: REST path without the ``/rest/`` prefix, e.g. ``system/reboot``.
            body: The call's arguments; an empty object when omitted.

        Returns:
            The decoded reply: a list, a dict or ``None`` for an empty reply.
        """
        return self._request("POST", path, json=body or {})

    def put(self, path: str, body: dict[str, str]) -> dict[str, str]:
        """Create a row with ``PUT`` and return it (the row carries its ``.id``).

        Args:
            path: REST path without the ``/rest/`` prefix, e.g. ``interface/bridge``.
            body: The row's fields as RouterOS strings.
        """
        data = self._request("PUT", path, json=body)
        return data if isinstance(data, dict) else {}

    def patch(self, path: str, row_id: str, body: dict[str, str]) -> dict[str, str]:
        """Update one row with ``PATCH``.

        Args:
            path: REST path without the ``/rest/`` prefix.
            row_id: The row's ``.id``.
            body: The fields to change as RouterOS strings.
        """
        data = self._request("PATCH", f"{path.strip('/')}/{row_id}", json=body)
        return data if isinstance(data, dict) else {}

    def delete(self, path: str, row_id: str) -> None:
        """Delete one row with ``DELETE``; the response body, if any, is ignored.

        Args:
            path: REST path without the ``/rest/`` prefix.
            row_id: The row's ``.id``.
        """
        self._request("DELETE", f"{path.strip('/')}/{row_id}")
