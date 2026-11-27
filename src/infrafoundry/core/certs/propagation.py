"""Wait until DNS-over-HTTPS resolvers see the DNS-01 TXT records. No fixed sleep."""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Sequence
from typing import Any

from infrafoundry.core.certs.dns_cloudflare import HttpSession
from infrafoundry.core.certs.models import DnsError

Resolver = Callable[[str], set[str]]
"""``name -> the TXT values the resolver sees``; may raise ``OSError``."""

TXT_TYPE = 16
HTTP_TIMEOUT = 10


def doh_resolver(url: str, session: HttpSession) -> Resolver:
    """Build a resolver for a DNS-over-HTTPS JSON endpoint (Cloudflare and Google style)."""

    def resolve(name: str) -> set[str]:
        response: Any = session.request(
            "GET",
            url,
            params={"name": name, "type": "TXT"},
            headers={"Accept": "application/dns-json"},
            timeout=HTTP_TIMEOUT,
        )
        if int(response.status_code) != 200:
            raise OSError(f"resolver answered HTTP {response.status_code}")
        body = response.json()
        values: set[str] = set()
        for answer in body.get("Answer") or []:
            if answer.get("type") == TXT_TYPE:
                values.add(str(answer.get("data", "")).strip().strip('"'))
        return values

    return resolve


def wait_for_txt(
    name: str,
    expected: Collection[str],
    resolvers: Sequence[Resolver],
    *,
    timeout: float,
    interval: float,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """Poll until every resolver sees every expected TXT value, or the timeout passes.

    Args:
        name: The record name.
        expected: The TXT values that must be visible.
        resolvers: Resolvers that must all see them.
        timeout: Seconds to wait.
        interval: Seconds between polls.
        sleep: Sleep function.
        monotonic: Clock.

    Raises:
        DnsError: If the values are not visible in time.
    """
    want = set(expected)
    deadline = monotonic() + timeout
    while True:
        missing = 0
        for resolve in resolvers:
            try:
                if not want <= resolve(name):
                    missing += 1
            except (OSError, ValueError, KeyError):
                missing += 1
        if missing == 0:
            return
        if monotonic() >= deadline:
            raise DnsError(
                f"the TXT record for {name} was not visible to {missing} of "
                f"{len(resolvers)} resolver(s) within {int(timeout)}s"
            )
        sleep(interval)
