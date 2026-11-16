"""Tests for the AWS resource-config and settings validators."""

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.aws.validators import (
    EbsVolumeValidator,
    InstanceValidator,
    SecurityGroupValidator,
    SettingsValidator,
)
from infrafoundry.providers.aws.validators._common import parse_cidr
from infrafoundry.providers.aws.validators.context import AWSConfigContext, AWSSettingsContext

from .conftest import SG, instance, rule, sg, volume


def _errors(report: ValidationReport) -> set[str]:
    return {
        r.check_name for r in report.results if not r.passed and r.level == ValidationLevel.ERROR
    }


def _run(validator: Any, resources: list[ResourceConfig]) -> ValidationReport:
    report = ValidationReport()
    validator(report).validate(AWSConfigContext.from_resources(resources))
    return report


class TestParseCidr:
    @pytest.mark.parametrize(
        ("value", "version"),
        [("192.0.2.0/24", 4), ("2001:db8::/32", 6), ("0.0.0.0/0", 4), ("::/0", 6)],
    )
    def test_valid(self, value: str, version: int) -> None:
        assert parse_cidr(value, version) is None

    @pytest.mark.parametrize(
        ("value", "version"),
        [
            ("not-a-cidr", 4),
            ("192.0.2.1/24", 4),
            ("2001:db8::/32", 4),
            ("192.0.2.0/24", 6),
            (24, 4),
        ],
    )
    def test_invalid(self, value: Any, version: int) -> None:
        assert parse_cidr(value, version)


class TestSecurityGroup:
    def test_valid(self) -> None:
        assert not _errors(_run(SecurityGroupValidator, [sg(ingress=[rule()])]))

    def test_vpc_required(self) -> None:
        group = ResourceConfig(name="web", type="security_group", provider="aws", config={})
        assert "aws_sg_web_vpc_id" in _errors(_run(SecurityGroupValidator, [group]))

    @pytest.mark.parametrize(
        "bad",
        [
            {"cidr_ipv4": "not-a-cidr"},
            {"cidr_ipv4": "192.0.2.1/24"},
            {"cidr_ipv4": "2001:db8::/32"},
            {"cidr_ipv4": None, "cidr_ipv6": "192.0.2.0/24"},
            {"cidr_ipv6": "2001:db8::/32"},
            {"cidr_ipv4": None},
        ],
    )
    def test_bad_cidr(self, bad: dict[str, Any]) -> None:
        errors = _errors(_run(SecurityGroupValidator, [sg(ingress=[rule(**bad)])]))
        assert "aws_sg_web_ingress_ssh_cidr" in errors

    @pytest.mark.parametrize(
        ("change", "suffix"),
        [
            ({"ip_protocol": "gre"}, "protocol"),
            ({"ip_protocol": 300}, "protocol"),
            ({"from_port": 70000}, "ports"),
            ({"from_port": 100, "to_port": 22}, "ports"),
            ({"from_port": None}, "ports"),
            ({"from_port": -1, "to_port": -1}, "ports"),
        ],
    )
    def test_bad_protocol_or_ports(self, change: dict[str, Any], suffix: str) -> None:
        errors = _errors(_run(SecurityGroupValidator, [sg(ingress=[rule(**change)])]))
        assert f"aws_sg_web_ingress_ssh_{suffix}" in errors

    def test_icmp_allows_minus_one_and_all_protocol_needs_no_ports(self) -> None:
        rules = [
            rule("ping", ip_protocol="icmp", from_port=-1, to_port=-1),
            rule("all", ip_protocol="-1", from_port=None, to_port=None),
        ]
        assert not _errors(_run(SecurityGroupValidator, [sg(egress=rules)]))

    def test_duplicate_and_bad_names(self) -> None:
        errors = _errors(
            _run(SecurityGroupValidator, [sg(ingress=[rule("a"), rule("a"), rule("b c")])])
        )
        assert "aws_sg_web_ingress_a" in errors
        assert "aws_sg_web_ingress_b c" in errors

    def test_rule_must_be_mapping(self) -> None:
        assert _errors(_run(SecurityGroupValidator, [sg(ingress=["x"])]))
        assert _errors(_run(SecurityGroupValidator, [sg(egress="x")]))


class TestInstance:
    def test_valid(self) -> None:
        assert not _errors(_run(InstanceValidator, [sg(), instance(security_groups=["web", SG])]))

    def test_neither_or_both_amis(self) -> None:
        assert "aws_instance_app_ami" in _errors(_run(InstanceValidator, [instance(ami=None)]))
        both = instance(ami_ssm_parameter="/p")
        assert "aws_instance_app_ami" in _errors(_run(InstanceValidator, [both]))

    def test_required_fields(self) -> None:
        errors = _errors(_run(InstanceValidator, [instance(instance_type=None, subnet_id=None)]))
        assert {"aws_instance_app_instance_type", "aws_instance_app_subnet_id"} <= errors

    def test_unknown_security_group(self) -> None:
        errors = _errors(_run(InstanceValidator, [instance(security_groups=["missing"])]))
        assert "aws_instance_app_security_groups" in errors

    def test_ipv6_only_conflicts_with_public_ip(self) -> None:
        bad = instance(ipv6_only=True, associate_public_ip_address=True)
        assert "aws_instance_app_ipv6_only" in _errors(_run(InstanceValidator, [bad]))

    @pytest.mark.parametrize("count", [0, "1", True])
    def test_ipv6_address_count(self, count: Any) -> None:
        bad = instance(ipv6_only=True, ipv6_address_count=count)
        assert "aws_instance_app_ipv6_address_count" in _errors(_run(InstanceValidator, [bad]))

    def test_security_groups_must_be_list(self) -> None:
        bad = instance(security_groups="web")
        assert "aws_instance_app_security_groups" in _errors(_run(InstanceValidator, [bad]))


class TestEbsVolume:
    def test_valid(self) -> None:
        assert not _errors(_run(EbsVolumeValidator, [instance(), volume()]))

    def test_missing_zone_and_size(self) -> None:
        errors = _errors(
            _run(EbsVolumeValidator, [instance(), volume(availability_zone=None, size=None)])
        )
        assert {"aws_ebs_volume_data_availability_zone", "aws_ebs_volume_data_size"} <= errors

    def test_unknown_instance(self) -> None:
        assert "aws_ebs_volume_data_instance" in _errors(_run(EbsVolumeValidator, [volume()]))

    def test_instance_or_instance_id_exactly_one(self) -> None:
        both = volume(instance_id="i-0123456789abcdef0")
        neither = volume(instance=None)
        assert "aws_ebs_volume_data_instance" in _errors(
            _run(EbsVolumeValidator, [instance(), both])
        )
        assert "aws_ebs_volume_data_instance" in _errors(_run(EbsVolumeValidator, [neither]))

    def test_zone_mismatch_only_when_instance_zone_set(self) -> None:
        mismatch = _run(EbsVolumeValidator, [instance(availability_zone="us-east-1b"), volume()])
        assert "aws_ebs_volume_data_availability_zone" in _errors(mismatch)
        assert not _errors(_run(EbsVolumeValidator, [instance(), volume()]))
        same = _run(EbsVolumeValidator, [instance(availability_zone="us-east-1a"), volume()])
        assert not _errors(same)

    @pytest.mark.parametrize("device", ["/dev/sda1", "sdf", "/dev/sdq"])
    def test_bad_device_name(self, device: str) -> None:
        errors = _errors(_run(EbsVolumeValidator, [instance(), volume(device_name=device)]))
        assert "aws_ebs_volume_data_device_name" in errors

    def test_bad_type(self) -> None:
        errors = _errors(_run(EbsVolumeValidator, [instance(), volume(type="magnetic")]))
        assert "aws_ebs_volume_data_type" in errors


class TestSettings:
    def _run(self, settings: dict[str, Any], env_region: bool = False) -> ValidationReport:
        report = ValidationReport()
        SettingsValidator(report).validate(
            AWSSettingsContext(provider_settings=settings, env_region=env_region)
        )
        return report

    @pytest.mark.parametrize("key", ["access_key", "secret_key", "token", "session_token"])
    def test_credential_keys_rejected(self, key: str) -> None:
        assert f"aws_settings_{key}" in _errors(self._run({"region": "us-east-1", key: "x"}))

    def test_missing_region_warns(self) -> None:
        report = self._run({})
        assert not report.has_errors()
        assert any(
            r.check_name == "aws_settings_region" and r.level == ValidationLevel.WARNING
            for r in report.results
        )

    def test_region_from_settings_or_env_is_clean(self) -> None:
        for report in (self._run({"region": "us-east-1"}), self._run({}, env_region=True)):
            assert not [r for r in report.results if not r.passed]
