"""Wait until resolvers see the DNS-01 TXT records. No fixed sleep.

The primary check asks the zone's authoritative nameservers directly (recursion off), so a
query made too early cannot poison a public resolver's negative cache. DNS-over-HTTPS resolvers
are an optional later stage.
"""

from __future__ import annotations

import secrets
import socket
import time
from collections.abc import Callable, Collection, Sequence
from typing import Any

from infrafoundry.core.certs.dns_cloudflare import HttpSession
from infrafoundry.core.certs.dns_wire import (
    DNS_PORT,
    Exchange,
    query_txt,
    tcp_exchange,
    udp_exchange,
)
from infrafoundry.core.certs.models import DnsError

Resolver = Callable[[str], set[str]]
"""``name -> the TXT values the resolver sees``; may raise ``OSError``."""

TXT_TYPE = 16
HTTP_TIMEOUT = 10
QUERY_TIMEOUT = 5.0
RCODE_NOERROR = 0
RCODE_NXDOMAIN = 3

NameserverQuery = Callable[[str, str], set[str]]
"""``(nameserver host, name) -> the TXT values it serves``; raises ``OSError`` if not visible."""

GetAddrInfo = Callable[..., list[tuple[Any, ...]]]


def query_nameserver(
    host: str,
    name: str,
    *,
    getaddrinfo: GetAddrInfo = socket.getaddrinfo,
    udp: Exchange = udp_exchange,
    tcp: Exchange = tcp_exchange,
    timeout: float = QUERY_TIMEOUT,
) -> set[str]:
    """Return the TXT values one authoritative nameserver serves for ``name``.

    Every address of the host (IPv4 and IPv6) is queried and the values are united, so one
    unreachable address family never hides a value another one serves.

    Raises:
        OSError: If no address gave a valid authoritative answer.
    """
    infos = getaddrinfo(host, DNS_PORT, type=socket.SOCK_DGRAM)
    addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
    values: set[str] = set()
    answered = False
    for address in addresses:
        try:
            response = query_txt(
                address, name, secrets.randbelow(1 << 16), timeout, udp=udp, tcp=tcp
            )
        except (OSError, ValueError):
            continue
        if not response.authoritative:
            continue
        if response.rcode not in (RCODE_NOERROR, RCODE_NXDOMAIN):
            continue
        answered = True
        values |= response.values
    if not answered:
        raise OSError(f"no valid authoritative answer from {host}")
    return values


def authoritative_resolver(
    name_servers: Callable[[], list[str]], query: NameserverQuery
) -> Resolver:
    """Build a resolver that needs every authoritative nameserver to serve a value.

    The nameserver list is fetched on the first poll and kept for the run.

    Raises:
        DnsError: (from the returned resolver) If the list is empty or cannot be fetched.
    """
    cached: list[str] | None = None

    def resolve(name: str) -> set[str]:
        nonlocal cached
        if cached is None:
            fetched = name_servers()
            if not fetched:
                raise DnsError("the zone has no authoritative nameservers to query")
            cached = fetched
        common: set[str] | None = None
        for host in cached:
            try:
                seen = query(host, name)
            except OSError:
                seen = set()
            common = seen if common is None else common & seen
        return common or set()

    return resolve


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
