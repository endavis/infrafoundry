"""ONTAP validator: offline findings, the spec file, connectivity and references."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import urlparse

import pytest

from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers._netapp.ontap import OntapConnectionError
from infrafoundry.providers.ontap import validator as ontap_validator
from infrafoundry.providers.ontap.validator import OntapValidator

from .conftest import RAW_SETTINGS, SETTINGS, FakeOntapService, lif, make_env

pytestmark = pytest.mark.unit

SECRETS = {"ontap": {"username": "u", "password": "p"}}


def _names(report: ValidationReport) -> list[str]:
    return [c.check_name for c in report.results if not c.passed]


def _settings(spec_dir: Path | None = None) -> dict[str, Any]:
    return {**RAW_SETTINGS, **({"api_spec_dir": str(spec_dir)} if spec_dir else {})}


@pytest.fixture
def spec_dir(tmp_path: Path) -> Path:
    (tmp_path / "ontap").mkdir()
    (tmp_path / "ontap" / "all.json").write_text('{"paths": {}}')
    return tmp_path


def test_valid_offline_has_no_findings(spec_dir: Path) -> None:
    report = ValidationReport()
    OntapValidator(make_env(_settings(spec_dir), SECRETS), report).validate_offline([lif()])
    assert _names(report) == []


def test_missing_spec_is_a_finding_that_names_the_path(tmp_path: Path) -> None:
    report = ValidationReport()
    env = make_env(_settings(tmp_path), SECRETS)
    OntapValidator(env, report).validate_offline([lif()])
    [check] = [c for c in report.results if c.check_name == "ontap_spec"]
    assert str(tmp_path / "ontap" / "all.json") in check.message
    urls = re.findall(r"https://\S+", check.message)
    assert urls, check.message
    assert urlparse(urls[0].rstrip(".,)")).hostname == "raw.githubusercontent.com"


def test_plaintext_secret_and_missing_env_secret_are_findings(spec_dir: Path) -> None:
    report = ValidationReport()
    env = make_env({**_settings(spec_dir), "password": "plain"}, SECRETS)
    OntapValidator(env, report).validate_offline([lif()])
    assert "ontap_settings" in _names(report)
    report = ValidationReport()
    env = make_env(_settings(spec_dir), {"ontap": {"username": "u"}})
    OntapValidator(env, report).validate_offline([lif()])
    assert "ontap_secret_password" in _names(report)


def test_schema_finding(spec_dir: Path) -> None:
    report = ValidationReport()
    OntapValidator(make_env(_settings(spec_dir), SECRETS), report).validate_offline([lif(vlan=3)])
    assert "ontap_schema_lif1" in _names(report)


def _connect(fake: Any, resources: list[Any] | None = None, *, refs: bool = False) -> Any:
    report = ValidationReport()
    env = make_env(dict(RAW_SETTINGS), SECRETS)
    validator = OntapValidator(env, report, Path("/unused"), service_factory=lambda _s: fake)
    with (
        patch.object(ontap_validator, "load_settings", return_value=SETTINGS),
        patch.object(ontap_validator, "spec_file_for", return_value=Path(__file__)),
    ):
        if refs:
            validator.validate_references(resources or [])
        else:
            validator.validate_connectivity()
    return report


def test_connectivity_reports_the_version() -> None:
    report = _connect(FakeOntapService())
    assert _names(report) == []
    assert "NetApp Release 9.18.1" in report.results[-1].message


def test_connectivity_failure_is_a_finding_without_credentials() -> None:
    class Down(FakeOntapService):
        def cluster_info(self) -> dict[str, Any]:
            raise OntapConnectionError("cannot reach 'cluster1.example.com'")

    report = _connect(Down())
    assert _names(report) == ["ontap_connectivity"]
    assert "pw-example" not in report.results[-1].message


def test_references_pass_for_existing_svm_node_and_port() -> None:
    assert _names(_connect(FakeOntapService(), [lif()], refs=True)) == []


@pytest.mark.parametrize(
    ("config", "needle"),
    [
        ({"svm": "svm9"}, "svm 'svm9'"),
        ({"home_node": "cluster1-09"}, "home node 'cluster1-09'"),
        ({"home_port": "e9z"}, "home port 'e9z' on node 'cluster1-01'"),
    ],
)
def test_references_to_missing_objects_are_findings(config: dict[str, Any], needle: str) -> None:
    report = _connect(FakeOntapService(), [lif(**config)], refs=True)
    [check] = [c for c in report.results if not c.passed and "reference" in c.check_name]
    assert needle in check.message


def test_references_skip_the_cluster_when_the_schema_is_broken() -> None:
    fake = FakeOntapService()
    report = _connect(fake, [lif(vlan=3)], refs=True)
    assert "ontap_schema_lif1" in _names(report) and fake.reads == []
