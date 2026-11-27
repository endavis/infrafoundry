"""``foundry certs renew``: selection, dry-run, quiet runs, exit codes (no network)."""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.exceptions import LockAcquisitionError
from tests.unit.cli.test_certs import Harness
from tests.unit.core.certs.fakes import KEY_ARMOUR, TOKEN, ZONE, certificate_resource, host_resource

pytestmark = pytest.mark.unit


def with_stored(h: Harness, **kwargs: Any) -> None:
    """Issue once, then declare the certificate with the stored entry."""
    h.run("issue", "--env", "dev")
    entry = {**h.writer.history[-1][1], **kwargs}
    h.resources[1] = certificate_resource(stored=entry)
    h.orchestrator.config_manager.get_all_resources_all_providers.return_value = h.resources
    h.events.clear()
    h.host.installed.clear()
    h.acme.calls.clear()


def test_renew_issues_a_never_issued_certificate_under_the_lock() -> None:
    h = Harness()
    result = h.run("renew", "--env", "dev")
    assert result.exit_code == 0, result.output
    assert "issued     proxy-cert" in result.output
    assert "Commit the config repo" in result.output
    assert h.events == ["lock:0:900", "verify", "unlock"]
    row = h.orchestrator.state_manager.create_deployment.call_args
    assert row.args[1] == "certs renew"


def test_renew_is_silent_and_takes_no_lock_when_nothing_is_due() -> None:
    h = Harness()
    with_stored(h)
    result = h.run("renew", "--env", "dev")
    assert result.exit_code == 0
    assert result.output == ""
    assert h.events == [] and h.acme.calls == []


def test_renew_retries_a_stored_but_not_installed_certificate() -> None:
    h = Harness()
    with_stored(h, installed_sha256="")
    result = h.run("renew", "--env", "dev")
    assert result.exit_code == 0, result.output
    assert "installed  proxy-cert" in result.output
    assert len(h.host.installed) == 1
    assert h.acme.calls == []


def test_dry_run_reports_and_takes_no_lock_or_network() -> None:
    h = Harness()
    result = h.run("renew", "--env", "dev", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would issue" in result.output and "never issued" in result.output
    assert h.events == []
    assert h.acme.calls == [] and h.session.requests == []
    assert h.host.installed == [] and h.writer.history == []
    h.orchestrator.state_manager.track_resource.assert_not_called()
    h.orchestrator.event_manager.emit_event.assert_not_called()


def test_dry_run_for_an_installed_retry_and_for_nothing_due() -> None:
    h = Harness()
    with_stored(h, installed_sha256="")
    assert "would install" in h.run("renew", "--env", "dev", "--dry-run").output
    h2 = Harness()
    with_stored(h2)
    result = h2.run("renew", "--env", "dev", "--dry-run")
    assert result.exit_code == 0 and "Nothing is due." in result.output


def test_dry_run_with_a_bad_declaration_exits_1() -> None:
    h = Harness(resources=[host_resource(), certificate_resource(names=["192.0.2.1"])])
    result = h.run("renew", "--env", "dev", "--dry-run")
    assert result.exit_code == 1
    assert "invalid" in result.output


def test_a_failed_certificate_exits_1_without_leaking_secrets() -> None:
    h = Harness()
    h.host.error = CertificateInstallError("the reload on 'proxy-01' failed")
    result = h.run("renew", "--env", "dev")
    assert result.exit_code == 1
    assert "failed     proxy-cert" in result.output
    for secret in (TOKEN, ZONE, KEY_ARMOUR, "PRIVATE"):
        assert secret not in result.output


def test_a_held_lock_exits_75() -> None:
    h = Harness()
    h.lock_error = LockAcquisitionError("dev", "someone@host:1", "t0", "t1")
    result = h.run("renew", "--env", "dev")
    assert result.exit_code == 75
    assert h.host.installed == []


def test_usage_errors_exit_2() -> None:
    assert Harness().run("renew", "--env", "dev", "nope").exit_code == 2
    assert Harness(settings=None).run("renew", "--env", "dev").exit_code == 2


def test_renew_has_no_force_option() -> None:
    assert Harness().run("renew", "--env", "dev", "--force").exit_code == 2


def test_no_certificate_resources_is_quiet_for_renew() -> None:
    h = Harness(resources=[host_resource()])
    assert h.run("renew", "--env", "dev").output == ""
    assert h.events == []


def test_events_reach_the_event_manager_with_the_environment() -> None:
    h = Harness()
    h.run("renew", "--env", "dev")
    calls = h.orchestrator.event_manager.emit_event.call_args_list
    assert [c.args[0].value for c in calls] == ["certificate_issued", "certificate_installed"]
    assert all(c.args[1] == "dev" for c in calls)
    assert KEY_ARMOUR not in repr(calls)
