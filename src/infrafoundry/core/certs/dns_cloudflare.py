"""DNS-01 records on Cloudflare.

The HTTP session is injected (``requests.Session`` or a fake). The API token is scrubbed from
every error message.
"""

from __future__ import annotations

from typing import Any, Protocol

from infrafoundry.core.certs.models import RECORD_COMMENT, DnsError

API_BASE = "https://api.cloudflare.com/client/v4"
RECORD_TTL = 60
HTTP_TIMEOUT = 20


class DnsProvider(Protocol):
    """What the issuer needs from a DNS host."""

    def add_txt(self, name: str, value: str, comment: str) -> str:
        """Create a TXT record and return its id."""
        ...

    def delete(self, record_id: str) -> None:
        """Delete a record; a record that is already gone is not an error."""
        ...

    def purge_stale(self) -> int:
        """Delete every TXT record InfraFoundry left behind; return how many."""
        ...


class HttpSession(Protocol):
    """The part of ``requests.Session`` that is used."""

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        """Send a request."""
        ...


class CloudflareDns:
    """:class:`DnsProvider` on the Cloudflare API for one zone."""

    def __init__(self, token: str, zone_id: str, session: HttpSession) -> None:
        """Initialize the client. The token is only ever sent in an ``Authorization`` header."""
        self._token = token
        self._zone = zone_id
        self._session = session

    def _scrub(self, text: str) -> str:
        scrubbed = text.replace(self._token, "***") if self._token else text
        return scrubbed.replace(self._zone, "<zone>") if self._zone else scrubbed

    def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{API_BASE}/zones/{self._zone}/dns_records{path}"
        try:
            response = self._session.request(
                method,
                url,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=HTTP_TIMEOUT,
                **kwargs,
            )
            status = int(response.status_code)
            body = response.json() if response.content else {}
        except (OSError, ValueError) as exc:
            raise DnsError(
                self._scrub(f"Cloudflare {method} failed: {exc.__class__.__name__}")
            ) from None
        if status == 404 and method == "DELETE":
            return {"success": True}
        if not isinstance(body, dict) or status >= 400 or body.get("success") is not True:
            errors = body.get("errors") if isinstance(body, dict) else None
            detail = ""
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                detail = f": {errors[0].get('message', '')}"
            raise DnsError(self._scrub(f"Cloudflare {method} failed (HTTP {status}){detail}"))
        return body

    def verify_access(self) -> None:
        """Check that the token can read this zone's DNS records (a read-only call).

        Raises:
            DnsError: If Cloudflare refuses the token or the zone. The message never carries
                the token or the zone id.
        """
        self._call("GET", "", params={"type": "TXT", "per_page": 1})

    def add_txt(self, name: str, value: str, comment: str) -> str:
        """Create a TXT record carrying ``comment`` and return its id."""
        body = self._call(
            "POST",
            "",
            json={
                "type": "TXT",
                "name": name,
                "content": value,
                "ttl": RECORD_TTL,
                "comment": comment,
            },
        )
        record_id = (body.get("result") or {}).get("id")
        if not isinstance(record_id, str) or not record_id:
            raise DnsError("Cloudflare returned no record id")
        return record_id

    def delete(self, record_id: str) -> None:
        """Delete a record by id."""
        self._call("DELETE", f"/{record_id}")

    def purge_stale(self) -> int:
        """Delete every TXT record whose comment starts with ``infrafoundry-acme``."""
        body = self._call(
            "GET",
            "",
            params={"type": "TXT", "comment.startswith": RECORD_COMMENT, "per_page": 100},
        )
        removed = 0
        for record in body.get("result") or []:
            comment = str(record.get("comment") or "")
            record_id = record.get("id")
            if comment.startswith(RECORD_COMMENT) and isinstance(record_id, str):
                self.delete(record_id)
                removed += 1
        return removed
