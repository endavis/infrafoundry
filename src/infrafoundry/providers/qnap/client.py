"""JSON client for a QNAP QSW-M series switch's web API (ADR-0038).

The switch serves ``/api/v1`` over HTTPS with a self-signed certificate. The client pins
the certificate by its SHA-256 fingerprint, checked during the TLS handshake before any
request byte is written (:mod:`infrafoundry.core.tls_pin`). ``verify_ssl: false`` is the
only way to skip the pin and logs a warning on every connection.

Every reply is an envelope ``{"error_code", "error_message", "result"}``; the HTTP status
can be 200 with a non-200 ``error_code``. A login is one ``POST users/login`` and a refusal
is never retried, because the lockout behaviour of the switch is unknown. The password, its
encoded form and the session token never reach a log line, an error message or a ``repr``.
The API is reverse-engineered from the web UI and not documented by the vendor.
"""

from __future__ import annotations

import base64
import http.client
import json
import logging
import struct
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from typing import Any, Protocol

from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.tls_pin import PinnedHTTPSConnection

from .settings import QnapSettings

logger = logging.getLogger(__name__)

API_BASE = "/api/v1/"
PLAIN_BASE = "/api/"
LIVE_TIMEOUT = 5.0


class QnapError(InfraFoundryError):
    """A request to the switch's web API failed."""


class QnapAuthError(QnapError):
    """The login (or the session token) was refused. A login is never retried."""


class QnapTlsPinError(QnapError):
    """The switch's certificate does not match the configured fingerprint."""


class QnapApiDriftError(QnapError):
    """The switch's reply does not have the shape this client expects."""


class QnapApiError(QnapError):
    """The switch answered with a non-200 ``error_code``."""

    def __init__(self, endpoint: str, error_code: int) -> None:
        """Initialize the error.

        Args:
            endpoint: The path that failed.
            error_code: The envelope's ``error_code``.
        """
        super().__init__(f"the switch rejected '{endpoint}' (error code {error_code})")
        self.endpoint = endpoint
        self.error_code = error_code


class QnapUnreachableError(QnapError):
    """The switch could not be reached (refused, dropped or no answer)."""


class QnapTimeoutError(QnapUnreachableError):
    """The switch did not answer within the timeout."""


def ez_encode(password: str) -> str:
    """Encode a password as the web UI does: base64 of its UTF-16 units masked to 8 bits.

    Args:
        password: The clear-text password.
    """
    data = password.encode("utf-16-le")
    units = struct.unpack(f"<{len(data) // 2}H", data)
    return base64.b64encode(bytes(unit & 0xFF for unit in units)).decode("ascii")


class QnapReader(Protocol):
    """What readers of the switch need from the client (tests substitute a fake)."""

    def get(self, path: str, *, timeout: float | None = None) -> Any:
        """Return the ``result`` of a GET under ``/api/v1/``."""
        ...

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """Return the ``result`` of a POST under ``/api/v1/``."""
        ...


ConnectionFactory = Callable[[QnapSettings, float], http.client.HTTPSConnection]


def _pin_error() -> Exception:
    return QnapTlsPinError(
        "the switch's certificate does not match tls_fingerprint; if the switch was "
        "reset or its certificate was regenerated, re-pin tls_fingerprint"
    )


def _default_factory(settings: QnapSettings, timeout: float) -> http.client.HTTPSConnection:
    if settings.fingerprint is None:
        logger.warning("verify_ssl is false for the switch web API: its certificate is not checked")
    return PinnedHTTPSConnection(
        settings.host,
        settings.port,
        fingerprint=settings.fingerprint,
        timeout=timeout,
        on_mismatch=_pin_error,
    )


class QnapClient:
    """Calls the switch's JSON API over a pinned HTTPS connection."""

    def __init__(
        self, settings: QnapSettings, *, connection_factory: ConnectionFactory | None = None
    ) -> None:
        """Initialize the client.

        Args:
            settings: Settings for one switch.
            connection_factory: Builds a connection for a timeout; replaced in tests.
        """
        self._settings = settings
        self._factory = connection_factory or _default_factory
        self._token: str | None = None

    def __repr__(self) -> str:
        """Show the target only; credentials and the token are never part of it."""
        return f"QnapClient(host={self._settings.host!r}, port={self._settings.port})"

    def _exchange(
        self,
        method: str,
        endpoint: str,
        payload: bytes | None,
        *,
        auth: bool,
        timeout: float | None,
        content_json: bool,
    ) -> tuple[int, bytes]:
        """Send one request and return ``(HTTP status, body)``; maps transport errors."""
        headers: dict[str, str] = {}
        if content_json:
            headers["Content-Type"] = "application/json;charset=UTF-8"
        if auth and self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        connection = self._factory(
            self._settings, float(timeout if timeout is not None else self._settings.timeout)
        )
        try:
            connection.request(method, endpoint, body=payload, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            status = response.status
        except QnapError:
            raise
        except TimeoutError as exc:
            raise QnapTimeoutError(f"the switch did not answer '{endpoint}' in time") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise QnapUnreachableError(
                f"the switch at {self._settings.host} could not be reached: {type(exc).__name__}"
            ) from exc
        finally:
            connection.close()
        return status, raw

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        auth: bool = True,
        timeout: float | None = None,
        base: str = API_BASE,
    ) -> Any:
        endpoint = f"{base}{path}"
        payload = json.dumps(body).encode() if body is not None else None
        status, raw = self._exchange(
            method, endpoint, payload, auth=auth, timeout=timeout, content_json=True
        )
        try:
            document = json.loads(raw)
        except ValueError as exc:
            if status == 401:
                raise QnapAuthError(f"the switch refused '{endpoint}' (HTTP 401)") from exc
            raise QnapApiDriftError(
                f"the switch's reply to '{endpoint}' is not JSON (HTTP {status})"
            ) from exc
        if not isinstance(document, dict):
            raise QnapApiDriftError(f"the switch's reply to '{endpoint}' is not a JSON object")
        code = document.get("error_code")
        if isinstance(code, bool) or not isinstance(code, int):
            raise QnapApiDriftError(f"the switch's reply to '{endpoint}' has no integer error_code")
        if code == 401:
            raise QnapAuthError(f"the switch refused '{endpoint}' (error code 401)")
        if code != 200:
            raise QnapApiError(endpoint, code)
        if "result" not in document:
            raise QnapApiDriftError(f"the switch's reply to '{endpoint}' has no 'result'")
        return document["result"]

    def login(self) -> None:
        """Log in once and keep the token; a refusal is never retried.

        Raises:
            QnapAuthError: If the switch refused the login.
            QnapApiDriftError: If the reply carries no token.
        """
        body = {
            "username": self._settings.username,
            "password": ez_encode(self._settings.password),
        }
        try:
            result = self._request("POST", "users/login", body, auth=False)
        except (QnapAuthError, QnapApiError) as exc:
            raise QnapAuthError(
                "the switch refused the login; not retrying, because its lockout "
                "behaviour is unknown. Check username and password"
            ) from exc
        if not isinstance(result, str) or not result:
            raise QnapApiDriftError("the switch's 'users/login' reply has no token")
        self._token = result

    def logout(self) -> None:
        """End the session; the token is dropped even if the request fails."""
        try:
            self._request("POST", "users/exit", {})
        finally:
            self._token = None

    def renew(self) -> None:
        """Replace the token with a fresh one (``GET users/login`` with the old token)."""
        result = self._request("GET", "users/login")
        if not isinstance(result, str) or not result:
            raise QnapApiDriftError("the switch's token renewal reply has no token")
        self._token = result

    @contextmanager
    def session(self) -> Iterator[None]:
        """Log in once, yield, and always log out afterwards."""
        self.login()
        try:
            yield
        finally:
            with suppress(QnapError):
                self.logout()

    def get(self, path: str, *, timeout: float | None = None) -> Any:
        """Return the ``result`` of ``GET /api/v1/<path>``.

        Args:
            path: Path below ``/api/v1/``.
            timeout: Socket timeout for this call; the settings' ``timeout`` by default.
        """
        return self._request("GET", path, timeout=timeout)

    def get_raw(self, path: str, *, timeout: float | None = None) -> bytes:
        """Return the body of ``GET /api/v1/<path>`` for a binary download.

        Used for the native configuration export, which is not a JSON envelope.

        Args:
            path: Path below ``/api/v1/``.
            timeout: Socket timeout for this call; the settings' ``timeout`` by default.

        Raises:
            QnapAuthError: If the switch refused the session token.
            QnapApiError: If the switch answered with a JSON envelope carrying an error code.
            QnapApiDriftError: If the reply is not a download (JSON success, HTML, empty or
                a non-200 status).
        """
        endpoint = f"{API_BASE}{path}"
        status, raw = self._exchange(
            "GET", endpoint, None, auth=True, timeout=timeout, content_json=False
        )
        if status == 401:
            raise QnapAuthError(f"the switch refused '{endpoint}' (HTTP 401)")
        head = raw.lstrip()[:15].lower()
        if head.startswith(b"{"):
            try:
                document = json.loads(raw)
            except ValueError:
                document = None
            code = document.get("error_code") if isinstance(document, dict) else None
            if isinstance(code, int) and not isinstance(code, bool):
                if code == 401:
                    raise QnapAuthError(f"the switch refused '{endpoint}' (error code 401)")
                if code != 200:
                    raise QnapApiError(endpoint, code)
                raise QnapApiDriftError(
                    f"the switch's reply to '{endpoint}' is JSON, not a download"
                )
        if head.startswith((b"<!doctype html", b"<html")):
            raise QnapApiDriftError(f"the switch's reply to '{endpoint}' is a web page")
        if status != 200:
            raise QnapApiDriftError(f"the switch's reply to '{endpoint}' is HTTP {status}")
        if not raw:
            raise QnapApiDriftError(f"the switch's reply to '{endpoint}' is empty")
        return raw

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """Return the ``result`` of ``POST /api/v1/<path>``.

        Args:
            path: Path below ``/api/v1/``.
            body: JSON body; ``{}`` by default.
        """
        return self._request("POST", path, body if body is not None else {})

    def about(self) -> dict[str, Any]:
        """Return ``/api/about`` (no login needed): hostname, model and product."""
        result = self._request("GET", "about", auth=False, base=PLAIN_BASE)
        if not isinstance(result, dict):
            raise QnapApiDriftError("the switch's '/api/about' reply is not an object")
        return result

    def live(self) -> bool:
        """Return True when ``/api/live`` answers; False on any failure (no login needed)."""
        try:
            self._request("GET", "live", auth=False, timeout=LIVE_TIMEOUT, base=PLAIN_BASE)
        except QnapError:
            return False
        return True

    def probe_tls(self) -> None:
        """Complete one TLS handshake (and the pin check) without sending a request.

        Raises:
            QnapUnreachableError: If the switch does not answer.
            QnapTlsPinError: If the certificate does not match the pin.
        """
        connection = self._factory(self._settings, float(self._settings.timeout))
        try:
            connection.connect()
        except QnapError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise QnapUnreachableError(
                f"the switch at {self._settings.host} could not be reached: {type(exc).__name__}"
            ) from exc
        finally:
            connection.close()


__all__ = [
    "QnapApiDriftError",
    "QnapApiError",
    "QnapAuthError",
    "QnapClient",
    "QnapError",
    "QnapReader",
    "QnapTimeoutError",
    "QnapTlsPinError",
    "QnapUnreachableError",
    "ez_encode",
]
