"""JSON-RPC client for a GL.iNet router's web API (ADR-0036).

The router serves ``POST /rpc`` over HTTPS with a self-signed certificate. The client
pins that certificate by its SHA-256 fingerprint and checks the pin during the TLS
handshake, before any request byte is written. ``verify_ssl: false`` is the only way
to skip the pin, and it logs a warning on every connection.

A session is one ``challenge`` plus one ``login``; a failed login is never retried
because the device locks out after repeated failures. Secrets (the password, the
crypt cipher, the login hash and the session id) never reach a log line, an error
message or a ``repr``.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import logging
import ssl
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from typing import Any

from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.providers.openwrt.glinet.crypt import UnsupportedCryptError, crypt
from infrafoundry.providers.openwrt.glinet.settings import GlinetWebSettings

logger = logging.getLogger(__name__)

RPC_PATH = "/rpc"
HASH_METHODS = {"md5": "md5", "sha256": "sha256", "sha512": "sha512"}
DEFAULT_HASH_METHOD = "sha256"


class GlinetRpcError(InfraFoundryError):
    """A request to the router's web API failed."""


class GlinetAuthError(GlinetRpcError):
    """The login was refused. It is never retried: the device locks out."""


class GlinetTlsPinError(GlinetRpcError):
    """The router's certificate does not match the configured fingerprint."""


class GlinetApiDriftError(GlinetRpcError):
    """The router's reply does not have the shape this client expects."""


class GlinetUnreachableError(GlinetRpcError):
    """The router could not be reached (refused, timed out, or the connection dropped)."""


def make_tls_context() -> ssl.SSLContext:
    """Return the client context: TLS 1.2+, no chain or host-name check (the pin replaces it)."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # nosec B501  # replaced by the fingerprint pin
    return context


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """An HTTPS connection that checks the peer certificate's SHA-256 pin on connect."""

    def __init__(self, host: str, port: int, *, fingerprint: str | None, timeout: float) -> None:
        """Create the connection; nothing is sent until :meth:`connect` succeeds.

        Args:
            host: Router address.
            port: Web port.
            fingerprint: 64 lowercase hex characters, or ``None`` for the unverified opt-out.
            timeout: Socket timeout in seconds.
        """
        super().__init__(host, port, timeout=timeout, context=make_tls_context())
        self._fingerprint = fingerprint

    def connect(self) -> None:
        """Connect, then compare the certificate with the pin before anything is sent.

        Raises:
            GlinetTlsPinError: If the certificate does not match the pin.
        """
        super().connect()
        if self._fingerprint is None:
            return
        sock = self.sock
        if not isinstance(sock, ssl.SSLSocket):  # pragma: no cover  # HTTPSConnection wraps
            self.close()
            raise GlinetTlsPinError("the router connection is not TLS")
        der = sock.getpeercert(binary_form=True)
        seen = hashlib.sha256(der).hexdigest() if der else ""
        if not hmac.compare_digest(seen, self._fingerprint):
            self.close()
            raise GlinetTlsPinError(
                "the router's certificate does not match tls_fingerprint; if the router "
                "was upgraded or reset, re-pin tls_fingerprint"
            )


ConnectionFactory = Callable[[GlinetWebSettings], http.client.HTTPSConnection]


def _default_factory(settings: GlinetWebSettings) -> http.client.HTTPSConnection:
    if settings.fingerprint is None:
        logger.warning("verify_ssl is false for the router web API: its certificate is not checked")
    return PinnedHTTPSConnection(
        settings.address,
        settings.port,
        fingerprint=settings.fingerprint,
        timeout=settings.connect_timeout,
    )


class GlinetRpcClient:
    """Calls the router's JSON-RPC API over a pinned HTTPS connection."""

    def __init__(
        self, settings: GlinetWebSettings, *, connection_factory: ConnectionFactory | None = None
    ) -> None:
        """Initialize the client.

        Args:
            settings: Web settings for one router.
            connection_factory: Builds a connection; replaced in tests.
        """
        self._settings = settings
        self._factory = connection_factory or _default_factory
        self._next_id = 0

    def __repr__(self) -> str:
        """Show the target only; credentials are never part of the representation."""
        return f"GlinetRpcClient(address={self._settings.address!r}, port={self._settings.port})"

    def _post(self, method: str, params: Any) -> Any:
        self._next_id += 1
        body = json.dumps(
            {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        ).encode()
        connection = self._factory(self._settings)
        try:
            connection.request(
                "POST", RPC_PATH, body=body, headers={"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            raw = response.read()
        except GlinetRpcError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise GlinetUnreachableError(
                f"the router at {self._settings.address} could not be reached: {type(exc).__name__}"
            ) from exc
        finally:
            connection.close()
        try:
            document = json.loads(raw)
        except ValueError as exc:
            raise GlinetApiDriftError(
                f"the router's reply to '{method}' is not JSON (HTTP {response.status})"
            ) from exc
        if not isinstance(document, dict):
            raise GlinetApiDriftError(f"the router's reply to '{method}' is not a JSON object")
        error = document.get("error")
        if error is not None:
            code = error.get("code") if isinstance(error, dict) else None
            raise GlinetRpcError(f"the router rejected '{method}' (error code {code})")
        if "result" not in document:
            raise GlinetApiDriftError(f"the router's reply to '{method}' has no 'result'")
        return document["result"]

    def probe_tls(self) -> None:
        """Complete one TLS handshake (and the pin check) without sending a request.

        Raises:
            GlinetUnreachableError: If the router does not answer.
            GlinetTlsPinError: If the certificate does not match the pin.
        """
        connection = self._factory(self._settings)
        try:
            connection.connect()
        except GlinetRpcError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise GlinetUnreachableError(
                f"the router at {self._settings.address} could not be reached: {type(exc).__name__}"
            ) from exc
        finally:
            connection.close()

    def _login(self) -> str:
        settings = self._settings
        challenge = self._post("challenge", {"username": settings.username})
        if not isinstance(challenge, dict):
            raise GlinetApiDriftError("the router's 'challenge' reply is not an object")
        alg, salt, nonce = (challenge.get(k) for k in ("alg", "salt", "nonce"))
        if not (isinstance(alg, int | str) and isinstance(salt, str) and isinstance(nonce, str)):
            raise GlinetApiDriftError("the router's 'challenge' reply lacks alg, salt or nonce")
        method = HASH_METHODS.get(str(challenge.get("hash-method", DEFAULT_HASH_METHOD)))
        if method is None:
            raise GlinetApiDriftError("the router's 'challenge' names an unsupported hash-method")
        try:
            cipher = crypt(settings.password, f"${alg}${salt}$")
        except UnsupportedCryptError as exc:
            # Raised before 'login' is sent, so no login attempt is spent.
            raise GlinetApiDriftError(str(exc)) from exc
        digest = hashlib.new(
            method, f"{settings.username}:{cipher}:{nonce}".encode(), usedforsecurity=False
        ).hexdigest()
        try:
            result = self._post("login", {"username": settings.username, "hash": digest})
        except (GlinetUnreachableError, GlinetTlsPinError, GlinetApiDriftError):
            raise
        except GlinetRpcError as exc:
            raise GlinetAuthError(
                "the router refused the login; not retrying, because the device locks "
                "out after repeated failed logins. Check web_username and web_password"
            ) from exc
        sid = result.get("sid") if isinstance(result, dict) else None
        if not isinstance(sid, str) or not sid:
            raise GlinetApiDriftError("the router's 'login' reply has no session id")
        return sid

    @contextmanager
    def session(self) -> Iterator[str]:
        """Log in once, yield the session id, and log out afterwards.

        A failed login raises :class:`GlinetAuthError` and is never retried.
        """
        sid = self._login()
        try:
            yield sid
        finally:
            with suppress(GlinetRpcError):
                self._post("logout", {"sid": sid})

    def call(self, sid: str, module: str, method: str, params: dict[str, Any] | None = None) -> Any:
        """Call ``module.method`` in the session ``sid`` and return its ``result``.

        Args:
            sid: Session id from :meth:`session`.
            module: API module (for example ``upgrade``).
            method: Method name.
            params: Method parameters.
        """
        return self._post("call", [sid, module, method, params or {}])


__all__ = [
    "GlinetApiDriftError",
    "GlinetAuthError",
    "GlinetRpcClient",
    "GlinetRpcError",
    "GlinetTlsPinError",
    "GlinetUnreachableError",
    "PinnedHTTPSConnection",
    "make_tls_context",
]
