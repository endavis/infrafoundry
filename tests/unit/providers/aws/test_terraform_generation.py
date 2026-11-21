"""Tests for AWS Terraform generation (string checks on the HCL)."""

from typing import Any

import pytest

from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.providers.aws import AWSProvider

from .conftest import (
    AMI,
    INSTANCE,
    RULE,
    SG,
    VOLUME,
    ZONE,
    instance,
    make_env,
    res,
    rule,
    sg,
    volume,
)


def _generate(provider: AWSProvider, *resources: Any) -> dict[str, str]:
    provider.generate_terraform(list(resources))
    return {p.name: p.read_text() for p in provider.terraform_dir.glob("*") if p.is_file()}


class TestProviderAndVariables:
    def test_provider_block_has_no_credentials(self, provider: AWSProvider) -> None:
        tf = _generate(provider, sg())["provider.tf"]
        assert 'source  = "hashicorp/aws"' in tf
        assert "var.aws_region" in tf
        assert "var.aws_profile" in tf
        assert "access_key" not in tf
        assert "secret_key" not in tf
        assert 'source  = "hashicorp/cloudinit"' in tf

    def test_variables_default_to_null(self, provider: AWSProvider) -> None:
        tf = _generate(provider, sg())["variables.tf"]
        assert 'variable "aws_region"' in tf
        assert 'variable "aws_profile"' in tf
        assert tf.count("default     = null") == 2


class TestSecurityGroup:
    def test_ipv4_and_ipv6_rules_and_escaped_description(self, provider: AWSProvider) -> None:
        tf = _generate(
            provider,
            sg(
                "web-sg",
                description="Web ${x}",
                ingress=[
                    rule("ssh", description="ssh ${y}"),
                    rule(
                        "https6",
                        from_port=443,
                        to_port=443,
                        cidr_ipv4=None,
                        cidr_ipv6="2001:db8::/32",
                    ),
                ],
            ),
        )["security_groups.tf"]
        assert 'resource "aws_security_group" "web_sg"' in tf
        assert 'description = "Web $${x}"' in tf
        assert 'resource "aws_vpc_security_group_ingress_rule" "web_sg_in_ssh"' in tf
        assert 'cidr_ipv4         = "192.0.2.0/24"' in tf
        assert 'description       = "ssh $${y}"' in tf
        assert 'cidr_ipv6         = "2001:db8::/32"' in tf
        assert "security_group_id = aws_security_group.web_sg.id" in tf

    def test_default_egress_allow_all(self, provider: AWSProvider) -> None:
        tf = _generate(provider, sg())["security_groups.tf"]
        assert 'resource "aws_vpc_security_group_egress_rule" "web_out_allow_all_ipv4"' in tf
        assert 'cidr_ipv4         = "0.0.0.0/0"' in tf
        assert 'resource "aws_vpc_security_group_egress_rule" "web_out_allow_all_ipv6"' in tf
        assert 'cidr_ipv6         = "::/0"' in tf

    def test_empty_egress_renders_none(self, provider: AWSProvider) -> None:
        tf = _generate(provider, sg(egress=[]))["security_groups.tf"]
        assert "egress_rule" not in tf

    def test_explicit_egress_replaces_default(self, provider: AWSProvider) -> None:
        tf = _generate(
            provider, sg(egress=[rule("dns", ip_protocol="udp", from_port=53, to_port=53)])
        )["security_groups.tf"]
        assert '"web_out_dns"' in tf
        assert "allow_all" not in tf

    def test_extra_tags(self, provider: AWSProvider) -> None:
        tf = _generate(provider, sg(tags={"Role": "edge"}))["security_groups.tf"]
        assert 'Name = "web"' in tf
        assert '"Role" = "edge"' in tf


class TestInstance:
    def test_literal_ami_and_defaults(self, provider: AWSProvider) -> None:
        tf = _generate(provider, instance(key_name="deploy", tags={"Role": "app"}))["instances.tf"]
        assert f'ami           = "{AMI}"' in tf
        assert "data.aws_ssm_parameter" not in tf
        assert 'http_tokens   = "required"' in tf
        assert 'volume_type = "gp3"' in tf
        assert "encrypted   = true" in tf
        assert 'Name = "app"' in tf
        assert '"Role" = "app"' in tf
        assert 'key_name      = "deploy"' in tf
        assert "ignore_changes" not in tf

    def test_ssm_ami_ignores_changes(self, provider: AWSProvider) -> None:
        tf = _generate(provider, instance(ami=None, ami_ssm_parameter="/ami/param"))["instances.tf"]
        assert 'data "aws_ssm_parameter" "app_ami"' in tf
        assert "nonsensitive(data.aws_ssm_parameter.app_ami.value)" in tf
        assert "ignore_changes = [ami]" in tf

    def test_replace_on_ami_change_drops_ignore(self, provider: AWSProvider) -> None:
        tf = _generate(
            provider,
            instance(ami=None, ami_ssm_parameter="/ami/param", replace_on_ami_change=True),
        )["instances.tf"]
        assert "aws_ssm_parameter" in tf
        assert "ignore_changes" not in tf

    def test_overrides(self, provider: AWSProvider) -> None:
        tf = _generate(
            provider,
            instance(imdsv2_required=False, root_volume_size=40, kms_key_id="alias/example"),
        )["instances.tf"]
        assert 'http_tokens   = "optional"' in tf
        assert "volume_size = 40" in tf
        assert 'kms_key_id  = "alias/example"' in tf

    def test_ipv6_only(self, provider: AWSProvider) -> None:
        tf = _generate(provider, instance(ipv6_only=True))["instances.tf"]
        assert "ipv6_address_count          = 1" in tf
        assert "associate_public_ip_address = false" in tf
        assert 'http_protocol_ipv6 = "enabled"' in tf
        assert 'hostname_type = "resource-name"' in tf
        assert "enable_resource_name_dns_aaaa_record = true" in tf

    def test_aaaa_record_only_when_ipv6_only(self, provider: AWSProvider) -> None:
        tf = _generate(provider, instance())["instances.tf"]
        assert "enable_resource_name_dns_aaaa_record" not in tf
        assert "enable_resource_name_dns_a_record" not in tf

    def test_dual_stack_ipv6_count_alone(self, provider: AWSProvider) -> None:
        tf = _generate(provider, instance(ipv6_address_count=2))["instances.tf"]
        assert "ipv6_address_count          = 2" in tf
        assert "http_protocol_ipv6" not in tf

    def test_security_groups_by_name_and_raw_id(self, provider: AWSProvider) -> None:
        tf = _generate(provider, sg("web-sg"), instance(security_groups=["web-sg", SG]))[
            "instances.tf"
        ]
        assert "aws_security_group.web_sg.id," in tf
        assert f'"{SG}",' in tf

    def test_cloud_init_snippet_user_data(self, provider: AWSProvider) -> None:
        snippets = provider.config_dir / "test" / "files" / "cloud-init-snippets"
        snippets.mkdir(parents=True)
        (snippets / "base.yaml").write_text("packages:\n  - htop\n")
        tf = _generate(provider, instance(cloud_init_snippets=["base"]))["instances.tf"]
        assert "#cloud-config" in tf
        assert "yamlencode(" in tf
        assert "htop" in tf

    def test_raw_user_data_is_escaped(self, provider: AWSProvider) -> None:
        tf = _generate(provider, instance(user_data="#!/bin/sh\necho ${HOME}"))["instances.tf"]
        assert 'user_data = "#!/bin/sh\\necho $${HOME}"' in tf

    def test_tailscale_module_and_secret_variable(
        self, provider: AWSProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        files = _generate(
            provider,
            instance(
                tailscale={"hostname": "app", "auth": {"auth_key_secret": "tailscale.auth_key"}}
            ),
        )
        assert 'module "tailscale_app"' in files["instances.tf"]
        assert "user_data_base64 = module.tailscale_app.rendered" in files["instances.tf"]
        assert 'variable "tailscale_auth_key"' in files["variables.tf"]
        assert "sensitive   = true" in files["variables.tf"]


class TestEbsVolume:
    def test_protected_by_default(self, provider: AWSProvider) -> None:
        tf = _generate(provider, instance(), volume())["ebs_volumes.tf"]
        assert 'resource "aws_ebs_volume" "data"' in tf
        assert "prevent_destroy = true" in tf
        assert 'resource "aws_volume_attachment" "data_attachment"' in tf
        assert "instance_id = aws_instance.app.id" in tf
        assert "stop_instance_before_detaching = true" in tf
        assert f'availability_zone = "{ZONE}"' in tf
        assert "encrypted         = true" in tf

    def test_unprotected(self, provider: AWSProvider) -> None:
        tf = _generate(provider, instance(), volume(prevent_destroy=False))["ebs_volumes.tf"]
        assert "prevent_destroy" not in tf

    def test_raw_instance_id_and_options(self, provider: AWSProvider) -> None:
        tf = _generate(
            provider,
            volume(instance=None, instance_id=INSTANCE, iops=4000, throughput=250, type="gp3"),
        )["ebs_volumes.tf"]
        assert f'instance_id = "{INSTANCE}"' in tf
        assert "iops              = 4000" in tf
        assert "throughput        = 250" in tf


class TestImportBlocks:
    def test_one_import_for_each_primary_type(self, provider: AWSProvider) -> None:
        files = _generate(
            provider,
            sg(import_id=SG),
            instance(import_id=INSTANCE),
            volume(import_id=VOLUME),
        )
        for name, address, ident in (
            ("security_groups.tf", "aws_security_group.web", SG),
            ("instances.tf", "aws_instance.app", INSTANCE),
            ("ebs_volumes.tf", "aws_ebs_volume.data", VOLUME),
        ):
            assert files[name].count("import {") == 1
            assert f'to = {address}\n  id = "{ident}"' in files[name]

    def test_no_import_for_companions_from_parent_id(self, provider: AWSProvider) -> None:
        files = _generate(
            provider, sg(import_id=SG, ingress=[rule()]), instance(), volume(import_id=VOLUME)
        )
        assert "to = aws_vpc_security_group_ingress_rule" not in files["security_groups.tf"]
        assert "to = aws_volume_attachment" not in files["ebs_volumes.tf"]

    def test_rule_and_attachment_import_ids(self, provider: AWSProvider) -> None:
        attachment = f"/dev/sdf:{VOLUME}:{INSTANCE}"
        files = _generate(
            provider,
            sg(ingress=[rule(import_id=RULE)]),
            instance(),
            volume(attachment_import_id=attachment),
        )
        assert (
            f'to = aws_vpc_security_group_ingress_rule.web_in_ssh\n  id = "{RULE}"'
            in files["security_groups.tf"]
        )
        assert (
            f'to = aws_volume_attachment.data_attachment\n  id = "{attachment}"'
            in files["ebs_volumes.tf"]
        )


class TestOutputs:
    def test_outputs(self, provider: AWSProvider) -> None:
        tf = _generate(provider, sg(), instance(), volume())["outputs.tf"]
        for name in (
            "security_group_ids",
            "instance_ids",
            "instance_private_ips",
            "instance_public_ips",
            "instance_ipv6_addresses",
            "ebs_volume_ids",
        ):
            assert f'output "{name}"' in tf


def test_only_present_types_are_rendered(provider: AWSProvider) -> None:
    files = _generate(provider, sg())
    assert "instances.tf" not in files
    assert "ebs_volumes.tf" not in files


def test_invalid_config_raises_naming_the_check(provider: AWSProvider) -> None:
    with pytest.raises(SchemaValidationError, match="aws_instance_app_ami"):
        provider.generate_terraform([instance(ami=None)])


def test_credentials_in_settings_raise(
    provider: AWSProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        provider, "_load_environment_config", lambda: make_env({"secret_key": "sentinel"})
    )
    with pytest.raises(SchemaValidationError, match="aws_settings_secret_key") as exc:
        provider.generate_terraform([res("web", "security_group", vpc_id="vpc-0123456789abcdef0")])
    assert "sentinel" not in str(exc.value)


class TestPackageSecretVariable:
    def test_package_ref_declares_package_scoped_variable(self, provider: AWSProvider) -> None:
        resource = instance(terraform_secrets=["package.admin_token"])
        resource.package_path = "aws/example-app"
        resource.package_secrets = {"admin_token": "not-a-real-secret"}
        files = _generate(provider, resource)
        assert 'variable "package_aws_example_app_admin_token"' in files["variables.tf"]
        assert all("not-a-real-secret" not in content for content in files.values())
