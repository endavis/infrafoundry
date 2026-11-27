"""Authoritative propagation: per-nameserver queries and the all-must-agree resolver."""

from __future__ import annotations

import socket
from typing import Any

import pytest

from infrafoundry.core.certs.dns_wire import FLAG_AA, FLAG_QR
from infrafoundry.core.certs.models import DnsError
from infrafoundry.core.certs.propagation import (
    authoritative_resolver,
    query_nameserver,
    wait_for_txt,
)

from .test_dns_wire import NAME, POINTER, response, txt_rr

pytestmark = pytest.mark.unit

V4 = "192.0.2.53"
V6 = "2001:db8::53"


def addrinfo(*addresses: str) -> Any:
    def getaddrinfo(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_DGRAM, 17, "", (a, port)) for a in addresses]

    return getaddrinfo


def serving(by_address: dict[str, Any]) -> Any:
    """A UDP exchange answering per address; an exception value is raised."""

    def udp(address: str, query: bytes, timeout: float) -> bytes:
        item = by_address[address]
        if isinstance(item, BaseException):
            raise item
        qid = int.from_bytes(query[:2], "big")
        return bytes(item(qid)) if callable(item) else bytes(item)

    return udp


def answer(*values: str, flags: int = FLAG_QR | FLAG_AA, rcode: int = 0) -> Any:
    def build(qid: int) -> bytes:
        return response(*[txt_rr(POINTER, v) for v in values], qid=qid, flags=flags, rcode=rcode)

    return build


def no_tcp(address: str, query: bytes, timeout: float) -> bytes:
    raise AssertionError("tcp not expected")


def ask(by_address: dict[str, Any]) -> set[str]:
    return query_nameserver(
        "ns1.example.com",
        NAME,
        getaddrinfo=addrinfo(*by_address),
        udp=serving(by_address),
        tcp=no_tcp,
    )


def test_a_value_on_the_v6_address_counts_when_the_v4_one_times_out() -> None:
    assert ask({V4: TimeoutError("t"), V6: answer("tok")}) == {"tok"}


def test_nxdomain_with_aa_is_an_empty_set() -> None:
    assert ask({V4: answer(rcode=3)}) == set()


@pytest.mark.parametrize(
    "item",
    [
        answer("tok", flags=FLAG_QR),
        answer(rcode=2),
        answer(rcode=5),
        TimeoutError("t"),
    ],
)
def test_an_invalid_answer_is_not_visible(item: Any) -> None:
    with pytest.raises(OSError):
        ask({V4: item})


def test_every_address_failing_is_not_visible() -> None:
    with pytest.raises(OSError):
        ask({V4: OSError("x"), V6: OSError("y")})


def test_a_resolution_failure_propagates_as_oserror() -> None:
    def broken(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        raise socket.gaierror("no such host")

    with pytest.raises(OSError):
        query_nameserver("ns1.example.com", NAME, getaddrinfo=broken, udp=no_tcp, tcp=no_tcp)


def test_the_qid_check_rejects_a_stale_answer() -> None:
    udp = serving({V4: lambda qid: response(txt_rr(POINTER, "tok"), qid=(qid + 1) & 0xFFFF)})
    with pytest.raises(OSError):
        query_nameserver("ns1", NAME, getaddrinfo=addrinfo(V4), udp=udp, tcp=no_tcp)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_the_resolver_returns_only_values_every_nameserver_sees() -> None:
    views = {"ns1": {"a", "b"}, "ns2": {"b", "c"}}
    resolve = authoritative_resolver(lambda: ["ns1", "ns2"], lambda h, n: views[h])
    assert resolve(NAME) == {"b"}


def test_a_nameserver_that_lacks_the_value_times_out() -> None:
    views = {"ns1": {"tok"}, "ns2": set()}
    resolve = authoritative_resolver(lambda: ["ns1", "ns2"], lambda h, n: views[h])
    clock = Clock()
    with pytest.raises(DnsError):
        wait_for_txt(
            NAME,
            {"tok"},
            [resolve],
            timeout=10,
            interval=2,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )


def test_an_unreachable_nameserver_counts_as_not_visible() -> None:
    def query(host: str, name: str) -> set[str]:
        if host == "ns2":
            raise OSError("down")
        return {"tok"}

    resolve = authoritative_resolver(lambda: ["ns1", "ns2"], query)
    assert resolve(NAME) == set()


def test_the_nameserver_list_is_fetched_once() -> None:
    calls: list[int] = []

    def servers() -> list[str]:
        calls.append(1)
        return ["ns1"]

    resolve = authoritative_resolver(servers, lambda h, n: {"tok"})
    resolve(NAME)
    resolve(NAME)
    assert len(calls) == 1


def test_a_lookup_failure_propagates_at_once() -> None:
    def servers() -> list[str]:
        raise DnsError("refused")

    resolve = authoritative_resolver(servers, lambda h, n: {"tok"})
    clock = Clock()
    with pytest.raises(DnsError, match="refused"):
        wait_for_txt(
            NAME,
            {"tok"},
            [resolve],
            timeout=10,
            interval=2,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
    assert clock.now == 0.0


def test_an_empty_nameserver_list_raises() -> None:
    resolve = authoritative_resolver(lambda: [], lambda h, n: set())
    with pytest.raises(DnsError):
        resolve(NAME)
