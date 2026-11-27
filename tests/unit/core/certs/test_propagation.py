"""Waiting for DNS-over-HTTPS resolvers to see the TXT records."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.certs.models import DnsError
from infrafoundry.core.certs.propagation import doh_resolver, wait_for_txt

pytestmark = pytest.mark.unit


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def wait(resolvers: list[Any], expected: set[str], timeout: float, interval: float) -> Clock:
    clock = Clock()
    wait_for_txt(
        "_acme-challenge.example.com",
        expected,
        resolvers,
        timeout=timeout,
        interval=interval,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )
    return clock


def test_returns_at_once_when_every_resolver_sees_every_value() -> None:
    clock = wait([lambda n: {"a", "b", "c"}] * 2, {"a", "b"}, 10, 1)
    assert clock.now == 0


def test_polls_until_the_record_appears_with_no_fixed_sleep() -> None:
    polls = {"n": 0}

    def resolver(name: str) -> set[str]:
        polls["n"] += 1
        return {"v"} if polls["n"] >= 4 else set()

    clock = wait([resolver], {"v"}, 60, 5)
    assert polls["n"] == 4
    assert clock.now == 15


def test_a_partial_view_keeps_waiting_and_times_out() -> None:
    with pytest.raises(DnsError, match="1 of 2 resolver"):
        wait([lambda n: {"v"}, lambda n: set()], {"v"}, 12, 5)


def test_a_failing_resolver_counts_as_not_visible() -> None:
    def broken(name: str) -> set[str]:
        raise OSError("down")

    with pytest.raises(DnsError):
        wait([broken], {"v"}, 2, 1)


class Session:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status, self.body = status, body
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "url": url, **kwargs})
        outer = self

        class Reply:
            status_code = outer.status

            def json(self) -> dict[str, Any]:
                return outer.body

        return Reply()


def test_doh_resolver_reads_quoted_txt_answers_only() -> None:
    body = {"Answer": [{"type": 16, "data": '"abc"'}, {"type": 1, "data": "192.0.2.1"}]}
    session = Session(200, body)
    assert doh_resolver("https://doh.example.test/q", session)("n.example.com") == {"abc"}
    assert session.calls[0]["params"] == {"name": "n.example.com", "type": "TXT"}
    assert session.calls[0]["headers"] == {"Accept": "application/dns-json"}


def test_doh_resolver_raises_on_http_errors() -> None:
    with pytest.raises(OSError, match="HTTP 502"):
        doh_resolver("https://doh.example.test/q", Session(502, {}))("n")


def test_doh_resolver_handles_no_answer() -> None:
    assert doh_resolver("https://doh.example.test/q", Session(200, {"Status": 3}))("n") == set()
