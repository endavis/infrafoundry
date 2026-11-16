"""Tests for HostValidator."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.host.validator import HostValidator, SshProbe, ssh_argv

from .conftest import AUTH_REF, host, make_env, tailscale_block


def _validate(
    resources: list[ResourceConfig],
    probe: SshProbe,
    repo: Path | None = None,
    secrets: dict[str, object] | None = None,
) -> ValidationReport:
    report = ValidationReport()
    HostValidator(
        make_env(secrets),
        report,
        ssh_probe=probe,
        repo_root=repo,
    ).validate_references(resources)
    return report


def _recording(calls: list[list[str]]) -> SshProbe:
    def probe(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    return probe


def _names(report: ValidationReport, passed: bool) -> list[str]:
    return [r.check_name for r in report.results if r.passed is passed]


def test_ssh_probe_passes() -> None:
    calls: list[list[str]] = []

    def probe(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    report = _validate([host()], probe)
    assert _names(report, True) == ["host_ssh_vps-01"]
    assert not report.has_errors()
    assert len(calls) == 1


def test_ssh_probe_failure_is_an_error() -> None:
    report = _validate([host()], lambda argv: 255)
    assert report.has_errors()
    assert "exit 255" in report.results[0].message


def test_ssh_probe_timeout_is_an_error() -> None:
    def probe(argv: list[str]) -> int:
        raise subprocess.TimeoutExpired(argv, 30)

    report = _validate([host()], probe)
    assert report.has_errors()
    assert "timed out" in report.results[0].message


def test_missing_ssh_is_a_warning() -> None:
    def probe(argv: list[str]) -> int:
        raise FileNotFoundError

    report = _validate([host()], probe)
    assert report.has_warnings()
    assert not report.has_errors()


def test_ssh_argv_shape() -> None:
    argv = ssh_argv(
        host(address="192.0.2.10", ssh_port=2222, ssh_user="admin", ssh_private_key_file="k")
    )
    assert argv == [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-p", "2222", "-i", "k", "-l", "admin", "--", "192.0.2.10", "true",
    ]  # fmt: skip
    assert ssh_argv(host())[-3:] == ["--", "vps-01.example.com", "true"]


def test_only_host_resources_are_probed() -> None:
    other = ResourceConfig(name="x", type="vm", provider="proxmox", config={})
    calls: list[list[str]] = []
    _validate([host(), other], _recording(calls))
    assert len(calls) == 1


def test_invalid_host_is_reported_and_not_probed() -> None:
    calls: list[list[str]] = []
    report = _validate([host(address="-bad")], _recording(calls))
    assert report.has_errors()
    assert calls == []


def test_missing_ansible_playbook_is_a_warning() -> None:
    report = ValidationReport()
    validator = HostValidator(make_env(), report)
    with patch("shutil.which", return_value=None):
        validator.validate_connectivity()
    assert report.has_warnings()
    assert report.results[0].level == ValidationLevel.WARNING

    report = ValidationReport()
    with patch("shutil.which", return_value="/usr/bin/ansible-playbook"):
        HostValidator(make_env(), report).validate_connectivity()
    assert not report.has_warnings()


def test_bad_secret_reference_is_an_error() -> None:
    resource = host(tailscale=tailscale_block(), terraform_secrets=["nope.missing"])
    report = _validate([resource], lambda argv: 0, secrets={"tailscale": {"x": "y"}})
    assert any("nope.missing" in r.message for r in report.results if not r.passed)
    assert AUTH_REF not in "".join(r.message for r in report.results if not r.passed)


def test_playbook_existence_checked_with_repo_root(repo: Path) -> None:
    resource = host(ansible={"playbooks": ["playbooks/missing.yml"]})
    report = _validate([resource], lambda argv: 0, repo=repo)
    assert any("does not exist" in r.message for r in report.results)


@pytest.mark.parametrize("probe_code", [0, 1])
def test_default_probe_is_replaceable(probe_code: int) -> None:
    report = _validate([host()], lambda argv: probe_code)
    assert report.has_errors() is bool(probe_code)
