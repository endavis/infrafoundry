"""The issuer: cleanup of DNS records on every path, account handling and results."""

from __future__ import annotations

import logging

import pytest

from infrafoundry.core.certs.issuer import CertificateIssuer
from infrafoundry.core.certs.models import AccountRecord, AcmeError, CertificateSpec, DnsError

from .fakes import KEY_ARMOUR, FakeAcme, FakeCloudflare, settings

pytestmark = pytest.mark.unit


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def spec(names: tuple[str, ...] = ("*.example.com", "example.com")) -> CertificateSpec:
    return CertificateSpec("proxy-cert", names, "ec-p256", None, {})


def build(
    acme: FakeAcme | None = None, dns: FakeCloudflare | None = None, visible: bool = True
) -> tuple[CertificateIssuer, FakeAcme, FakeCloudflare]:
    acme = acme or FakeAcme()
    dns = dns or FakeCloudflare()
    clock = Clock()
    issuer = CertificateIssuer(
        acme,
        dns,
        [dns.resolver(visible=visible)],
        settings(propagation_timeout=10, propagation_interval=2),
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )
    return issuer, acme, dns


def test_issue_returns_a_certificate_and_deletes_every_record() -> None:
    issuer, acme, dns = build()
    issued = issuer.issue(spec())
    assert issued.info.names == ("*.example.com", "example.com")
    assert issued.cert_pem.count("BEGIN CERTIFICATE") == 1
    assert issued.chain_pem.count("BEGIN CERTIFICATE") == 1
    assert KEY_ARMOUR in issued.key_pem
    assert KEY_ARMOUR not in repr(issued)
    assert dns.records == {}
    assert sorted(dns.deleted) == sorted(dns.added)
    assert len(dns.added) == 2
    assert len(acme.answered) == 2


def test_records_carry_the_infrafoundry_comment() -> None:
    issuer, _, dns = build()
    seen: list[str] = []
    original = dns.add_txt

    def spy(name: str, value: str, comment: str) -> str:
        seen.append(comment)
        return original(name, value, comment)

    dns.add_txt = spy  # type: ignore[method-assign]
    issuer.issue(spec())
    assert seen == ["infrafoundry-acme proxy-cert"] * 2


def test_stale_records_are_purged_before_ordering() -> None:
    dns = FakeCloudflare()
    dns.records["old"] = ("_acme-challenge.example.com", "stale", "infrafoundry-acme old")
    dns.records["mine"] = ("x.example.com", "keep", "not ours")
    issuer, _, dns = build(dns=dns)
    issuer.issue(spec())
    assert dns.purged == 1
    assert "mine" in dns.records


def test_propagation_timeout_still_deletes_the_records() -> None:
    issuer, acme, dns = build(visible=False)
    with pytest.raises(DnsError, match="not visible"):
        issuer.issue(spec())
    assert dns.records == {}
    assert acme.answered == []


@pytest.mark.parametrize("step", ["new_order", "answer", "finalize"])
def test_an_acme_failure_still_deletes_the_records(step: str) -> None:
    acme = FakeAcme()
    acme.fail_on = step
    issuer, _, dns = build(acme=acme)
    with pytest.raises(AcmeError, match=step):
        issuer.issue(spec())
    assert dns.records == {}


def test_a_record_that_cannot_be_created_removes_the_ones_already_made() -> None:
    dns = FakeCloudflare()
    dns.fail_add_after = 1
    issuer, _, dns = build(dns=dns)
    with pytest.raises(DnsError, match="POST"):
        issuer.issue(spec())
    assert dns.records == {}
    assert len(dns.deleted) == 1


def test_a_cleanup_failure_does_not_fail_the_issue(caplog: pytest.LogCaptureFixture) -> None:
    dns = FakeCloudflare()
    dns.fail_delete = True
    issuer, _, dns = build(dns=dns)
    with caplog.at_level(logging.WARNING):
        issued = issuer.issue(spec(("example.com",)))
    assert issued.info.names == ("example.com",)
    assert "could not delete" in caplog.text


def test_a_cleanup_failure_does_not_mask_the_original_error() -> None:
    dns = FakeCloudflare()
    dns.fail_delete = True
    acme = FakeAcme()
    acme.fail_on = "finalize"
    issuer, _, _ = build(acme=acme, dns=dns)
    with pytest.raises(AcmeError, match="finalize"):
        issuer.issue(spec(("example.com",)))


def test_two_names_on_one_zone_share_a_record_name_with_two_values() -> None:
    issuer, _, dns = build()
    seen: list[tuple[str, str]] = []
    original = dns.add_txt

    def spy(name: str, value: str, comment: str) -> str:
        seen.append((name, value))
        return original(name, value, comment)

    dns.add_txt = spy  # type: ignore[method-assign]
    issuer.issue(spec())
    assert len({n for n, _ in seen}) == 1
    assert len({v for _, v in seen}) == 2


def test_ensure_account_generates_a_key_and_registers_on_the_first_run() -> None:
    issuer, acme, _ = build()
    record = issuer.ensure_account(None)
    assert KEY_ARMOUR in record.key_pem
    assert record.uri == acme.account_uri
    assert acme.accounts[0][1] is None


def test_ensure_account_returns_the_stored_record_when_nothing_changed() -> None:
    issuer, acme, _ = build()
    stored = AccountRecord("KEY-SENTINEL", acme.account_uri)
    assert issuer.ensure_account(stored) is stored
    assert acme.accounts[0][:2] == ("KEY-SENTINEL", acme.account_uri)
    assert "KEY-SENTINEL" not in repr(stored)


def test_ensure_account_returns_a_new_record_when_the_uri_changes() -> None:
    issuer, acme, _ = build()
    record = issuer.ensure_account(AccountRecord("KEY", None))
    assert record.uri == acme.account_uri
