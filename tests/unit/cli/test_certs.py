"""``foundry certs status`` and ``issue`` with fakes at every seam (no network)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import pytest
from click.testing import CliRunner, Result

from infrafoundry.cli.commands.certs import _common, certs
from infrafoundry.core.certs.install import CertificateTarget
from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import LockAcquisitionError
from infrafoundry.core.state.models import DeploymentStatus, ResourceState
from tests.unit.core.certs.fakes import (
    KEY_ARMOUR,
    NOW,
    TOKEN,
    ZONE,
    FakeAcme,
    MemoryWriter,
    certificate_resource,
    host_resource,
)

pytestmark = pytest.mark.unit

SETTINGS: dict[str, Any] = {
    "agree_tos": True,
    "cloudflare": {
        "api_token": "secret://env_secrets/acme/cloudflare_api_token",
        "zone_id": "secret://env_secrets/acme/cloudflare_zone_id",
    },
    "propagation": {"timeout": 10, "interval": 1},
}
SECRETS = {"acme": {"cloudflare_api_token": TOKEN, "cloudflare_zone_id": ZONE}}


class Reply:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status_code = status
        self._body = body
        self.content = b"x"

    def json(self) -> dict[str, Any]:
        return self._body


class FakeSession:
    """Serves both the Cloudflare API and the DoH resolvers from one record table."""

    def __init__(self) -> None:
        self.records: dict[str, dict[str, str]] = {}
        self.requests: list[tuple[str, str]] = []
        self.tokens: set[str] = set()
        self.nameserver_queries: list[tuple[str, str]] = []

    def nameserver_query(self, host: str, name: str) -> set[str]:
        self.nameserver_queries.append((host, name))
        return {r["content"] for r in self.records.values() if r["name"] == name}

    def request(self, method: str, url: str, **kwargs: Any) -> Reply:
        self.requests.append((method, url))
        if urlsplit(url).hostname == "api.cloudflare.com":
            self.tokens.add(kwargs["headers"]["Authorization"])
            return self._cloudflare(method, url, kwargs)
        name = kwargs["params"]["name"]
        answers = [
            {"type": 16, "data": f'"{r["content"]}"'}
            for r in self.records.values()
            if r["name"] == name
        ]
        return Reply(200, {"Answer": answers})

    def _cloudflare(self, method: str, url: str, kwargs: dict[str, Any]) -> Reply:
        if method == "GET" and urlsplit(url).path.endswith(f"/zones/{ZONE}"):
            return Reply(
                200,
                {
                    "success": True,
                    "result": {"name_servers": ["ns1.example.com", "ns2.example.com"]},
                },
            )
        if method == "POST":
            record_id = f"rec-{len(self.records) + 1}"
            self.records[record_id] = dict(kwargs["json"])
            return Reply(200, {"success": True, "result": {"id": record_id}})
        if method == "DELETE":
            self.records.pop(url.rsplit("/", 1)[1], None)
            return Reply(200, {"success": True})
        listing = [{"id": i, **r} for i, r in self.records.items()]
        return Reply(200, {"success": True, "result": listing})


class FakeHost:
    def __init__(self) -> None:
        self.installed: list[tuple[CertificateTarget, str, str, str]] = []
        self.error: Exception | None = None

    def install_certificate(
        self, target: CertificateTarget, cert_pem: str, chain_pem: str, key_pem: str
    ) -> None:
        if self.error:
            raise self.error
        self.installed.append((target, cert_pem, chain_pem, key_pem))


class Harness:
    def __init__(
        self,
        resources: list[Any] | None = None,
        settings: dict[str, Any] | None = SETTINGS,
        secrets: dict[str, Any] | None = None,
    ) -> None:
        self.session = FakeSession()
        self.acme = FakeAcme()
        self.writer = MemoryWriter()
        self.host = FakeHost()
        self.events: list[str] = []
        self.lock_error: Exception | None = None
        self.resources = (
            [host_resource(), certificate_resource()] if resources is None else resources
        )
        self.env_config = EnvironmentConfig(
            name="dev",
            provider_settings={"acme": settings} if settings is not None else {},
            secrets=SECRETS if secrets is None else secrets,
        )
        self.orchestrator = MagicMock()
        manager = self.orchestrator.config_manager
        manager.base_dir = Path("/cfg/envs")
        manager.get_all_resources_all_providers.return_value = self.resources
        manager.load_environment.return_value = self.env_config
        self.orchestrator.providers = {"host": self.host}

        @contextmanager
        def lock(env_name: str, *, timeout: int = 0, ttl: int = 600) -> Iterator[None]:
            if self.lock_error:
                raise self.lock_error
            self.events.append(f"lock:{timeout}:{ttl}")
            yield
            self.events.append("unlock")

        self.orchestrator.environment_lock.side_effect = lock

    def run(self, *args: str) -> Result:
        deps = _common.CertsDeps(
            acme_client=lambda s: self.acme,
            session=lambda: self.session,
            nameserver_query=self.session.nameserver_query,
            writer=lambda: self.writer,  # type: ignore[arg-type,return-value]
            verify=lambda target, sha: self.events.append("verify"),
            sleep=lambda s: None,
            monotonic=_ticker(),
            now=lambda: NOW,
        )
        with (
            patch.object(_common, "DEPS", deps),
            patch("infrafoundry.cli.main._get_orchestrator", return_value=self.orchestrator),
            patch("infrafoundry.cli.main._load_env_credentials"),
        ):
            return CliRunner().invoke(certs, [*args])


def _ticker() -> Any:
    state = {"now": 0.0}

    def tick() -> float:
        state["now"] += 0.01
        return state["now"]

    return tick


def test_issue_issues_installs_records_state_and_reminds_to_commit() -> None:
    h = Harness()
    result = h.run("issue", "--env", "dev")
    assert result.exit_code == 0, result.output
    assert "issued     proxy-cert: issued and installed; valid until" in result.output
    assert "Commit the config repo" in result.output
    assert h.events == ["lock:0:900", "verify", "unlock"]
    assert len(h.host.installed) == 1
    manager = h.orchestrator.state_manager
    row = manager.track_resource.call_args
    assert row.args[5] == ResourceState.ACTIVE
    assert row.args[3:5] == ("certificate", "proxy-cert")
    assert KEY_ARMOUR not in repr(row)
    manager.update_deployment_status.assert_called_once()
    assert manager.update_deployment_status.call_args.args[1] == DeploymentStatus.COMPLETED


def test_the_dns_records_are_cleaned_up_and_the_token_only_goes_in_the_header() -> None:
    h = Harness()
    h.run("issue", "--env", "dev")
    assert h.session.records == {}
    assert h.session.tokens == {f"Bearer {TOKEN}"}
    assert not any(TOKEN in url for _, url in h.session.requests)


def test_by_default_the_authoritative_nameservers_are_asked_and_no_doh_request_is_made() -> None:
    h = Harness()
    result = h.run("issue", "--env", "dev")
    assert result.exit_code == 0
    assert h.session.nameserver_queries
    assert {host for host, _ in h.session.nameserver_queries} == {
        "ns1.example.com",
        "ns2.example.com",
    }
    assert all(urlsplit(url).hostname == "api.cloudflare.com" for _, url in h.session.requests)


def test_a_configured_doh_resolver_is_asked_only_after_the_record_exists() -> None:
    h = Harness(settings={**SETTINGS, "doh": ["https://doh.example.com/dns-query"]})
    result = h.run("issue", "--env", "dev")
    assert result.exit_code == 0
    methods = [(m, urlsplit(u).hostname) for m, u in h.session.requests]
    first_doh = methods.index(("GET", "doh.example.com"))
    assert ("POST", "api.cloudflare.com") in methods[:first_doh]


def test_no_secret_reaches_the_output_even_when_the_install_fails() -> None:
    h = Harness()
    h.host.error = CertificateInstallError("the reload on 'proxy-01' failed")
    result = h.run("issue", "--env", "dev")
    assert result.exit_code == 1
    for secret in (TOKEN, ZONE, KEY_ARMOUR, "PRIVATE"):
        assert secret not in result.output
    assert "failed     proxy-cert" in result.output


def test_unknown_certificate_name_is_a_usage_error() -> None:
    result = Harness().run("issue", "--env", "dev", "nope")
    assert result.exit_code != 0
    assert "no certificate named: nope" in result.output


def test_missing_settings_are_a_usage_error_naming_keys_only() -> None:
    result = Harness(settings=None).run("issue", "--env", "dev")
    assert result.exit_code == 2
    assert "provider_settings.acme is missing" in result.output


def test_plain_text_token_is_refused_without_echoing_it() -> None:
    bad = {**SETTINGS, "cloudflare": {"api_token": TOKEN, "zone_id": ZONE}}
    result = Harness(settings=bad).run("issue", "--env", "dev")
    assert result.exit_code == 2
    assert TOKEN not in result.output


def test_a_held_lock_exits_75() -> None:
    h = Harness()
    h.lock_error = LockAcquisitionError("dev", "someone@host:1", "t0", "t1")
    result = h.run("issue", "--env", "dev")
    assert result.exit_code == 75
    assert h.host.installed == []


def test_no_certificate_resources_takes_no_lock() -> None:
    h = Harness(resources=[host_resource()])
    result = h.run("issue", "--env", "dev")
    assert result.exit_code == 0
    assert "nothing to do" in result.output
    assert h.events == []


def test_a_second_run_skips_the_current_certificate() -> None:
    h = Harness()
    h.run("issue", "--env", "dev")
    entry = h.writer.history[-1][1]
    h.resources[1] = certificate_resource(stored=entry)
    h.orchestrator.config_manager.get_all_resources_all_providers.return_value = h.resources
    again = h.run("issue", "--env", "dev")
    assert again.exit_code == 0
    assert "skipped    proxy-cert: up to date" in again.output
    assert "Commit the config repo" not in again.output


def test_status_reads_the_store_only() -> None:
    h = Harness()
    h.run("issue", "--env", "dev")
    entry = h.writer.history[-1][1]
    h.resources[1] = certificate_resource(stored=entry)
    h.orchestrator.config_manager.get_all_resources_all_providers.return_value = h.resources
    before = len(h.session.requests)
    result = h.run("status", "--env", "dev")
    assert result.exit_code == 0
    assert "proxy-cert" in result.output
    assert "valid" in result.output
    assert "installed=yes" in result.output
    assert len(h.session.requests) == before
    assert KEY_ARMOUR not in result.output


def test_status_before_the_first_issue() -> None:
    result = Harness().run("status", "--env", "dev")
    assert result.exit_code == 0
    assert "not issued" in result.output


def test_status_without_certificates() -> None:
    result = Harness(resources=[host_resource()]).run("status", "--env", "dev")
    assert result.exit_code == 0
    assert "No certificate resources" in result.output
