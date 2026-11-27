"""``CertificateService``: status, the issue order, retries and failure isolation."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.certs.install import CertificateTarget
from infrafoundry.core.certs.issuer import CertificateIssuer
from infrafoundry.core.certs.models import AccountRecord, CertificateInstallError
from infrafoundry.core.certs.service import CertificateService, _entry_from
from infrafoundry.core.provider import ResourceConfig

from .fakes import (
    KEY_ARMOUR,
    NOW,
    FakeAcme,
    FakeCloudflare,
    MemoryWriter,
    certificate_resource,
    host_resource,
    settings,
)

pytestmark = pytest.mark.unit

ENVS = Path("/cfg/envs")
DIRECTORY = settings().directory
NAMES = ("*.example.com", "example.com")


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeHost:
    """A provider with the install hook; records what it was given."""

    def __init__(self) -> None:
        self.installed: list[tuple[CertificateTarget, str, str, str]] = []
        self.error: Exception | None = None
        self.events: list[str] = []

    def install_certificate(
        self, target: CertificateTarget, cert_pem: str, chain_pem: str, key_pem: str
    ) -> None:
        self.events.append("install")
        if self.error:
            raise self.error
        self.installed.append((target, cert_pem, chain_pem, key_pem))


class Rig:
    def __init__(self, days: int = 90) -> None:
        self.acme = FakeAcme(days=days)
        self.dns = FakeCloudflare()
        self.writer = MemoryWriter()
        self.host = FakeHost()
        self.verified: list[tuple[CertificateTarget, str]] = []
        self.states: list[tuple[ResourceConfig, dict[str, Any]]] = []
        self.verify_error: Exception | None = None
        clock = Clock()
        self.issuer = CertificateIssuer(
            self.acme,
            self.dns,
            [self.dns.resolver()],
            settings(),
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            now=lambda: NOW,
        )

    def service(self, providers: dict[str, Any] | None = None) -> CertificateService:
        return CertificateService(
            env="prod",
            envs_dir=ENVS,
            writer=self.writer,  # type: ignore[arg-type]
            providers={"host": self.host} if providers is None else providers,
            verify=self._verify,
            record_state=lambda r, c: self.states.append((r, c)),
            now=lambda: NOW,
        )

    def _verify(self, target: CertificateTarget, sha: str) -> None:
        self.host.events.append("verify")
        if self.verify_error:
            raise self.verify_error
        self.verified.append((target, sha))

    def issue(
        self,
        resources: list[ResourceConfig],
        account: AccountRecord | None = None,
        providers: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.service(providers).issue(
            resources,
            self.issuer,
            account,
            directory=DIRECTORY,
            directory_id="staging",
            **kwargs,
        )


def stored_entry(
    rig: Rig, *, days: int = 90, installed: bool = True, **over: Any
) -> dict[str, Any]:
    """An entry as ``issue`` stores it, for a certificate issued ``days`` ago-adjusted."""
    issued = _issue_directly(rig, days)
    entry = _entry_from(issued)
    entry["installed_sha256"] = entry["sha256"] if installed else ""
    entry.update(over)
    return entry


def _issue_directly(rig: Rig, days: int) -> Any:
    from infrafoundry.core.certs.models import CertificateSpec

    dns = FakeCloudflare()
    clock = Clock()
    issuer = CertificateIssuer(
        FakeAcme(rig.acme.ca, days=days),
        dns,
        [dns.resolver()],
        settings(),
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        now=lambda: NOW,
    )
    return issuer.issue(CertificateSpec("proxy-cert", NAMES, "ec-p256", None, {}))


def resources(*certs: ResourceConfig) -> list[ResourceConfig]:
    return [host_resource(), *certs]


def test_issue_runs_in_order_and_installs_the_stored_key() -> None:
    rig = Rig()
    outcomes = rig.issue(resources(certificate_resource()))
    assert [(o.name, o.action) for o in outcomes] == [("proxy-cert", "issued")]
    assert rig.host.events == ["install", "verify"]
    target, cert, chain, key = rig.host.installed[0]
    assert target.endpoint is not None
    assert KEY_ARMOUR in key
    assert cert.count("BEGIN CERTIFICATE") == 1
    assert chain.count("BEGIN CERTIFICATE") == 1


def test_the_entry_is_written_before_the_install_and_marked_installed_after() -> None:
    rig = Rig()
    rig.issue(resources(certificate_resource()))
    keys = ("variables", "acme_certificates", "proxy-cert")
    writes = [v for k, v in rig.writer.history if k == keys]
    assert writes[0]["installed_sha256"] == ""
    assert writes[1]["installed_sha256"] == writes[1]["sha256"]
    assert set(writes[0]) >= {
        "cert_pem", "chain_pem", "key_pem", "not_after", "not_before", "serial", "sha256",
        "names", "key_type", "directory", "issued_at", "installed_sha256",
    }  # fmt: skip
    assert rig.writer.paths[-1] == ENVS / "prod" / "proxy" / "secrets.yaml"
    assert rig.verified[0][1] == writes[1]["sha256"]


def test_the_account_key_is_stored_in_the_env_secrets_once() -> None:
    rig = Rig()
    rig.issue(resources(certificate_resource()))
    account = rig.writer.values[("acme", "accounts", "staging")]
    assert KEY_ARMOUR in account["key_pem"]
    assert account["uri"] == rig.acme.account_uri
    assert (ENVS / "prod" / "secrets.yaml", "acme: {}\n") in rig.writer.created


def test_a_stored_account_is_reused_and_not_rewritten() -> None:
    rig = Rig()
    rig.issue(resources(certificate_resource()), account=AccountRecord("KEY", rig.acme.account_uri))
    assert ("acme", "accounts", "staging") not in rig.writer.values
    assert rig.acme.accounts[0][:2] == ("KEY", rig.acme.account_uri)


def test_a_current_installed_certificate_is_skipped_without_contacting_the_ca() -> None:
    rig = Rig()
    cert = certificate_resource(stored=stored_entry(rig))
    outcomes = rig.issue(resources(cert))
    assert [o.action for o in outcomes] == ["skipped"]
    assert rig.acme.calls == []
    assert rig.host.events == []
    assert rig.states == []


def test_a_due_certificate_is_issued_again() -> None:
    rig = Rig()
    cert = certificate_resource(stored=stored_entry(rig, days=10))
    assert [o.action for o in rig.issue(resources(cert))] == ["issued"]


def test_force_issues_a_current_certificate_again() -> None:
    rig = Rig()
    cert = certificate_resource(stored=stored_entry(rig))
    assert [o.action for o in rig.issue(resources(cert), force=True)] == ["issued"]


@pytest.mark.parametrize(
    "change",
    [{"directory": "https://other.example.test/dir"}, {"key_type": "rsa-2048"}, {"key_pem": ""}],
)
def test_a_changed_directory_key_type_or_missing_key_reissues(change: dict[str, Any]) -> None:
    rig = Rig()
    cert = certificate_resource(stored=stored_entry(rig, **change))
    assert [o.action for o in rig.issue(resources(cert))] == ["issued"]


def test_changed_names_reissue() -> None:
    rig = Rig()
    cert = certificate_resource(names=["example.com"], stored=stored_entry(rig))
    assert [o.action for o in rig.issue(resources(cert))] == ["issued"]


def test_a_stored_but_not_installed_certificate_gets_an_install_only_retry() -> None:
    rig = Rig()
    entry = stored_entry(rig, installed=False)
    cert = certificate_resource(stored=entry)
    outcomes = rig.issue(resources(cert))
    assert [o.action for o in outcomes] == ["installed"]
    assert rig.acme.calls == []
    assert rig.host.installed[0][3] == entry["key_pem"]
    last = rig.writer.history[-1][1]
    assert last["installed_sha256"] == entry["sha256"]


def test_an_install_failure_is_reported_and_the_certificate_stays_stored_for_a_retry() -> None:
    rig = Rig()
    rig.host.error = CertificateInstallError("the reload on 'proxy-01' failed")
    outcomes = rig.issue(resources(certificate_resource()))
    assert outcomes[0].action == "failed"
    assert "issued and stored" in outcomes[0].message
    assert "run 'foundry certs issue' again" in outcomes[0].message
    stored = rig.writer.history[-1][1]
    assert stored["installed_sha256"] == ""
    assert rig.states == []


def test_a_verification_failure_leaves_installed_sha256_empty() -> None:
    rig = Rig()
    rig.verify_error = CertificateInstallError("it serves a different certificate")
    outcomes = rig.issue(resources(certificate_resource()))
    assert outcomes[0].action == "failed"
    assert rig.writer.history[-1][1]["installed_sha256"] == ""


def test_one_failure_does_not_stop_the_next_certificate() -> None:
    rig = Rig()
    rig.acme.fail_on = None
    first = certificate_resource("a-cert", names=["a.example.com"])
    first.config["target"]["resource"] = "missing-host"
    second = certificate_resource("b-cert", names=["b.example.com"])
    outcomes = rig.issue(resources(first, second))
    assert [(o.name, o.action) for o in outcomes] == [("a-cert", "failed"), ("b-cert", "issued")]
    assert "not declared" in outcomes[0].message


def test_an_acme_failure_is_reported_per_certificate() -> None:
    rig = Rig()
    rig.acme.fail_on = "new_order"
    outcomes = rig.issue(resources(certificate_resource()))
    assert outcomes[0].action == "failed"
    assert rig.host.events == []


def test_a_target_provider_without_the_hook_is_a_clear_failure() -> None:
    rig = Rig()
    outcomes = rig.issue(resources(certificate_resource()), providers={"host": object()})
    assert outcomes[0].action == "failed"
    assert "cannot install certificates" in outcomes[0].message


def test_a_secrets_write_failure_is_reported_and_nothing_is_installed() -> None:
    rig = Rig()
    rig.writer.fail = True
    outcomes = rig.issue(resources(certificate_resource()))
    assert outcomes[0].action == "failed"
    assert rig.host.events == []


def test_unknown_names_are_a_usage_error() -> None:
    from infrafoundry.core.certs.models import CertificateError

    with pytest.raises(CertificateError, match="no certificate named: nope"):
        Rig().issue(resources(certificate_resource()), only=["nope"])


def test_only_the_named_certificates_are_processed() -> None:
    rig = Rig()
    a = certificate_resource("a-cert", names=["a.example.com"])
    b = certificate_resource("b-cert", names=["b.example.com"])
    outcomes = rig.issue(resources(a, b), only=["b-cert"])
    assert [o.name for o in outcomes] == ["b-cert"]


def test_the_state_row_carries_no_key_material() -> None:
    rig = Rig()
    rig.issue(resources(certificate_resource()))
    resource, config = rig.states[0]
    assert resource.name == "proxy-cert"
    assert set(config) == {"names", "not_after", "sha256", "target"}
    assert KEY_ARMOUR not in repr(config)
    assert "key" not in " ".join(config["target"])


def test_nothing_secret_reaches_outcomes_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig()
    rig.host.error = CertificateInstallError("the reload failed")
    with caplog.at_level("DEBUG"):
        outcomes = rig.issue(resources(certificate_resource()))
    text = " ".join(o.message for o in outcomes) + caplog.text
    assert KEY_ARMOUR not in text
    assert "PRIVATE" not in text


def test_status_reports_each_state() -> None:
    rig = Rig()
    cases = {
        "none": certificate_resource("none"),
        "valid": certificate_resource("valid", stored=stored_entry(rig)),
        "due": certificate_resource("due", stored=stored_entry(rig, days=10)),
        "uninstalled": certificate_resource(
            "uninstalled", stored=stored_entry(rig, installed=False)
        ),
        "broken": certificate_resource("broken", stored={"cert_pem": "garbage"}),
    }
    by_name = {s.name: s for s in rig.service().status(list(cases.values()))}
    assert by_name["none"].state == "not issued"
    assert by_name["valid"].state == "valid"
    assert by_name["valid"].installed is True
    assert by_name["valid"].days_left == 90
    assert by_name["due"].state == "due"
    assert by_name["uninstalled"].state == "not installed"
    assert by_name["broken"].state == "invalid"


def test_status_reports_expired_certificates() -> None:
    rig = Rig()
    late = CertificateService(
        env="prod",
        envs_dir=ENVS,
        writer=rig.writer,  # type: ignore[arg-type]
        providers={},
        now=lambda: NOW + dt.timedelta(days=200),
    )
    [item] = late.status([certificate_resource(stored=stored_entry(rig))])
    assert item.state == "expired"


def test_status_honours_a_per_certificate_window() -> None:
    rig = Rig()
    cert = certificate_resource(stored=stored_entry(rig, days=40), renew_before_days=45)
    assert rig.service().status([cert])[0].state == "due"
