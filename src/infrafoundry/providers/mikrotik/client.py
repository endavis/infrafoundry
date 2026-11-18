"""Minimal RouterOS REST client (RouterOS 7 and later).

Only reads and ``/rest/execute`` are implemented here. The write verbs (PUT to
create, PATCH to update, DELETE to remove) are added with apply (#1483) after they
are verified on a RouterOS CHR virtual machine.
"""

from __future__ import annotations

from typing import Any, Protocol

import requests

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


class RouterOSClient:
    """REST client over a ``requests.Session`` with HTTP basic auth."""

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

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Send one request and return the decoded JSON body.

        Raises:
            RouterOSConnectionError: On a transport failure.
            RouterOSAPIError: On a non-success status.
        """
        url = self._base + path.strip("/")
        try:
            response = self._session.request(method, url, timeout=self._timeout, **kwargs)
        except requests.RequestException as exc:
            raise RouterOSConnectionError(
                f"Could not reach RouterOS at {self._base}: {type(exc).__name__}"
            ) from exc
        if response.status_code >= 400:
            raise RouterOSAPIError(self._error_text(response, path), response.status_code)
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
