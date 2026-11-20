"""Tests for OCI compartment validation."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.oci.validator import OCIValidator
from infrafoundry.providers.oci.validators import CompartmentValidator
from infrafoundry.providers.oci.validators.context import OCIApiContext
from tests.helpers.env import make_env_config

OCID = "ocid1.compartment.oc1..aaaaaaaexample"


def _settings(**extra: str) -> Any:
    settings = {
        "tenancy_ocid": "ocid1.tenancy.oc1..example",
        "user_ocid": "ocid1.user.oc1..example",
        "fingerprint": "aa:bb",
        "private_key_path": "/tmp/k.pem",
        "region": "us-phoenix-1",
    }
    settings.update(extra)
    return make_env_config(provider_settings={"oci": settings})


def _res(name: str, type_: str, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type=type_, provider="oci", config=config)


def _comp(name: str, **config: Any) -> ResourceConfig:
    config.setdefault("description", "d")
    return _res(name, "compartment", **config)


def _errors(report: ValidationReport) -> list[str]:
    return [
        r.check_name for r in report.results if r.level == ValidationLevel.ERROR and not r.passed
    ]


def _validate(resources: list[ResourceConfig], refs: Any = None, **settings: str) -> list[str]:
    report = ValidationReport()
    OCIValidator(_settings(**settings), report).validate_offline(resources, refs)
    return _errors(report)


class TestOffline:
    """Offline compartment checks."""

    def test_known_name_ocid_and_fallback_ok(self) -> None:
        """Name, OCID and the compartment_ocid fallback all pass."""
        resources = [
            _comp("c"),
            _res("v1", "vcn", compartment="c"),
            _res("v2", "vcn", compartment=OCID),
            _res("v3", "vcn"),
        ]
        assert _validate(resources, compartment_ocid=OCID) == []

    def test_unknown_reference(self) -> None:
        """An undefined compartment name is an error."""
        errors = _validate([_res("v", "vcn", compartment="ghost")], compartment_ocid=OCID)
        assert errors == ["oci_compartment_ref_vcn_v"]

    def test_missing_compartment_without_fallback(self) -> None:
        """A resource with no compartment and no compartment_ocid is an error."""
        assert "oci_compartment_ref_subnet_s" in _validate([_res("s", "subnet", vcn="v")])

    def test_missing_description(self) -> None:
        """A compartment needs a description."""
        resource = _res("c", "compartment")
        assert _validate([resource]) == ["oci_compartment_c_description"]

    def test_unknown_parent(self) -> None:
        """An undefined parent is an error."""
        assert _validate([_comp("c", parent="ghost")]) == ["oci_compartment_c_parent"]

    def test_parent_ocid_ok(self) -> None:
        """An OCID parent is accepted."""
        assert _validate([_comp("c", parent=OCID)]) == []

    def test_cycle(self) -> None:
        """A parent cycle is reported for each member."""
        errors = _validate([_comp("a", parent="b"), _comp("b", parent="a")])
        assert sorted(errors) == ["oci_compartment_a_cycle", "oci_compartment_b_cycle"]

    def test_resolution_through_reference_resources(self) -> None:
        """A compartment outside the filtered subset resolves via reference_resources."""
        assert _validate([_res("v", "vcn", compartment="c")], [_comp("c")]) == []


def _api_validator(**settings: str) -> tuple[OCIValidator, MagicMock, ValidationReport]:
    report = ValidationReport()
    validator = OCIValidator(_settings(**settings), report)
    client = MagicMock()
    client.identity_url.return_value = "https://identity.example"
    client.iaas_url.return_value = "https://iaas.example"
    validator._create_client = MagicMock(return_value=client)  # type: ignore[method-assign]
    return validator, client, report


class TestApi:
    """API-backed compartment checks."""

    def test_only_region_subscriptions_without_compartment_ocid(self) -> None:
        """With compartments and no compartment_ocid only regionSubscriptions is fetched."""
        validator, client, report = _api_validator()
        client.list_resources.return_value = [{"regionName": "us-phoenix-1", "isHomeRegion": True}]
        validator._validate_api_references([_comp("c")])
        assert client.list_resources.call_count == 1
        assert "regionSubscriptions" in client.list_resources.call_args[0][1]
        assert _errors(report) == []

    def test_home_region_mismatch_reported(self) -> None:
        """A non-home region is an error."""
        validator, client, report = _api_validator()
        client.list_resources.return_value = [
            {"regionName": "eu-frankfurt-1", "isHomeRegion": True}
        ]
        validator._validate_api_references([_comp("c")])
        assert _errors(report) == ["oci_compartment_home_region"]

    def test_with_compartment_ocid_fetches_everything(self) -> None:
        """With compartment_ocid and compartments, five endpoints are fetched."""
        validator, client, _report = _api_validator(compartment_ocid=OCID)
        client.list_resources.return_value = []
        validator._validate_api_references([_comp("c")])
        assert client.list_resources.call_count == 5

    def test_no_compartments_unchanged(self) -> None:
        """Without compartment resources the original four calls are made."""
        validator, client, _report = _api_validator(compartment_ocid=OCID)
        client.list_resources.return_value = []
        validator._validate_api_references([_res("v", "vcn", cidr_block="192.0.2.0/24")])
        assert client.list_resources.call_count == 4

    def test_skipped_without_compartment_ocid_or_compartments(self) -> None:
        """Nothing is fetched when there is nothing to check."""
        validator, client, _report = _api_validator()
        validator._validate_api_references([_res("v", "vcn")])
        client.list_resources.assert_not_called()


class TestHomeRegion:
    """CompartmentValidator.check_home_region."""

    def _run(self, subs: list[dict[str, Any]] | None, resources: list[ResourceConfig]) -> Any:
        report = ValidationReport()
        context = OCIApiContext(
            resources=resources,
            compartment_ocid="",
            region="us-phoenix-1",
            region_subscriptions=subs,
        )
        CompartmentValidator(report).check_home_region(context)
        return report

    def test_match(self) -> None:
        """The home region passes."""
        report = self._run([{"regionName": "us-phoenix-1", "isHomeRegion": True}], [_comp("c")])
        assert [r.passed for r in report.results] == [True]

    def test_mismatch(self) -> None:
        """A different home region fails."""
        report = self._run([{"regionName": "eu-frankfurt-1", "isHomeRegion": True}], [_comp("c")])
        assert _errors(report) == ["oci_compartment_home_region"]

    def test_no_data(self) -> None:
        """No subscription data adds nothing."""
        assert self._run(None, [_comp("c")]).results == []

    def test_no_compartments(self) -> None:
        """Without compartment resources nothing is checked."""
        subs = [{"regionName": "eu-frankfurt-1", "isHomeRegion": True}]
        assert self._run(subs, [_res("v", "vcn")]).results == []

    def test_existence_check_skipped_without_ocid(self) -> None:
        """validate() skips the existence check when compartment_ocid is empty."""
        report = ValidationReport()
        context = OCIApiContext(resources=[], compartment_ocid="", compartments=[])
        CompartmentValidator(report).validate(context)
        assert report.results == []
