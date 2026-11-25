"""SHA-256 certificate pinning for HTTPS clients of devices with self-signed certificates.

The pin replaces chain and host-name verification: the peer certificate's SHA-256 digest
is compared with the configured fingerprint in ``connect()``, before any request byte is
written. ``fingerprint=None`` is the unsafe opt-out (no verification at all).
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import re
import ssl
from collections.abc import Callable

FINGERPRINT_HEX_LENGTH = 64
_HEX = re.compile(r"^[0-9a-f]{64}$")


def normalize_fingerprint(value: object) -> str | None:
    """Return a SHA-256 fingerprint as 64 lowercase hex characters, or ``None`` if invalid.

    Args:
        value: The configured pin, with or without ``:`` separators, in any case.
    """
    if not isinstance(value, str):
        return None
    compact = value.replace(":", "").strip().lower()
    return compact if _HEX.match(compact) else None


def make_tls_context() -> ssl.SSLContext:
    """Return the client context: TLS 1.2+, no chain or host-name check (the pin replaces it)."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # nosec B501  # replaced by the fingerprint pin
    return context


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """An HTTPS connection that checks the peer certificate's SHA-256 pin on connect."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        fingerprint: str | None,
        timeout: float,
        on_mismatch: Callable[[], Exception],
    ) -> None:
        """Create the connection; nothing is sent until :meth:`connect` succeeds.

        Args:
            host: Device address.
            port: HTTPS port.
            fingerprint: 64 lowercase hex characters, or ``None`` for the unverified opt-out.
            timeout: Socket timeout in seconds.
            on_mismatch: Builds the error raised when the certificate does not match.
        """
        super().__init__(host, port, timeout=timeout, context=make_tls_context())
        self._fingerprint = fingerprint
        self._on_mismatch = on_mismatch

    def connect(self) -> None:
        """Connect, then compare the certificate with the pin before anything is sent.

        Raises:
            Exception: The ``on_mismatch`` error if the certificate does not match the pin.
        """
        super().connect()
        if self._fingerprint is None:
            return
        sock = self.sock
        if not isinstance(sock, ssl.SSLSocket):  # pragma: no cover  # HTTPSConnection wraps
            self.close()
            raise self._on_mismatch()
        der = sock.getpeercert(binary_form=True)
        seen = hashlib.sha256(der).hexdigest() if der else ""
        if not hmac.compare_digest(seen, self._fingerprint):
            self.close()
            raise self._on_mismatch()


__all__ = [
    "FINGERPRINT_HEX_LENGTH",
    "PinnedHTTPSConnection",
    "make_tls_context",
    "normalize_fingerprint",
]
