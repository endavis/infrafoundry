"""Tests for offline bucket and IAM validation."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.oci.validator import OCIValidator
from tests.helpers.env import make_env_config

OCID = "ocid1.compartment.oc1..aaaaaaaexample"


def _res(name: str, type_: str, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type=type_, provider="oci", config=config)


def _run(resources: list[ResourceConfig], refs: Any = None) -> ValidationReport:
    env = make_env_config(provider_settings={"oci": {"compartment_ocid": OCID}})
    report = ValidationReport()
    OCIValidator(env, report).validate_offline(resources, refs)
    return report


def _names(report: ValidationReport, level: ValidationLevel) -> list[str]:
    return [r.check_name for r in report.results if r.level == level and not r.passed]


RULE = {"name": "r", "action": "DELETE", "time_amount": 1, "time_unit": "DAYS"}


def test_valid_config_has_no_errors() -> None:
    """A full valid configuration reports nothing."""
    report = _run(
        [
            _res("c", "compartment", description="d"),
            _res("b", "bucket", compartment="c", storage_tier="Archive", lifecycle=[RULE]),
            _res("u", "iam_user"),
            _res("g", "iam_group", members=["u"]),
            _res("p", "iam_policy", statements=["Allow x"], compartment=OCID),
            _res("key", "customer_secret_key", user="u"),
        ]
    )
    assert _names(report, ValidationLevel.ERROR) == []
    assert _names(report, ValidationLevel.WARNING) == []


def test_bucket_enums() -> None:
    """Bad bucket enums are errors."""
    report = _run([_res("b", "bucket", storage_tier="x", versioning="y", access_type="z")])
    assert _names(report, ValidationLevel.ERROR) == [
        "oci_bucket_b_storage_tier",
        "oci_bucket_b_versioning",
        "oci_bucket_b_access_type",
    ]


def test_bucket_unknown_compartment() -> None:
    """A bucket compartment is checked like a vcn's."""
    report = _run([_res("b", "bucket", compartment="ghost")])
    assert "oci_compartment_ref_bucket_b" in _names(report, ValidationLevel.ERROR)


def test_lifecycle_rules() -> None:
    """Bad lifecycle fields and duplicate names are errors."""
    bad = {"action": "NOPE", "time_amount": 0, "time_unit": "HOURS"}
    report = _run([_res("b", "bucket", lifecycle=[RULE, dict(RULE), bad])])
    errors = _names(report, ValidationLevel.ERROR)
    assert "oci_bucket_b_lifecycle_1_name" in errors
    for suffix in ("name", "action", "time_amount", "time_unit"):
        assert f"oci_bucket_b_lifecycle_2_{suffix}" in errors


def test_lifecycle_not_a_list() -> None:
    """A non-list lifecycle is an error."""
    report = _run([_res("b", "bucket", lifecycle="x")])
    assert _names(report, ValidationLevel.ERROR) == ["oci_bucket_b_lifecycle"]


def test_references() -> None:
    """Unknown members, key users and policy compartments are errors."""
    report = _run(
        [
            _res("g", "iam_group", members=["ghost"]),
            _res("p", "iam_policy", statements=[], compartment="ghost"),
            _res("k", "customer_secret_key"),
        ]
    )
    errors = _names(report, ValidationLevel.ERROR)
    assert "oci_iam_group_g_member_ghost" in errors
    assert "oci_iam_policy_p_statements" in errors
    assert "oci_iam_policy_p_compartment" in errors
    assert "oci_customer_secret_key_k_user" in errors


def test_reference_resources_resolve_names() -> None:
    """Names defined outside a filtered subset still resolve."""
    refs = [_res("u", "iam_user")]
    report = _run([_res("k", "customer_secret_key", user="u")], refs)
    assert _names(report, ValidationLevel.ERROR) == []


def test_warnings() -> None:
    """An ignored compartment and an unreferenceable key name warn."""
    report = _run(
        [
            _res("u", "iam_user", compartment=OCID),
            _res("Bad", "customer_secret_key", user="u"),
        ]
    )
    assert _names(report, ValidationLevel.WARNING) == [
        "oci_iam_user_u_compartment",
        "oci_customer_secret_key_Bad_name",
    ]
