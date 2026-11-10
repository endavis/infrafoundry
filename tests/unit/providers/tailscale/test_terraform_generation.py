"""Tests for Tailscale Terraform generation (exact-string checks on the HCL)."""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.providers.tailscale import TailscaleProvider
from infrafoundry.providers.tailscale.hcl import hcl_list, hcl_string

from .conftest import (
    OAUTH_SECRETS,
    OAUTH_URIS,
    SECRET_ID,
    SECRET_VALUE,
    make_env,
    res,
)

POLICY: dict[str, Any] = {
    "tagOwners": {"tag:server": ["autogroup:admin"]},
    "acls": [{"action": "accept", "src": ["*"], "dst": ["*:*"]}],
}


def _generate(provider: TailscaleProvider, *resources: Any) -> dict[str, str]:
    provider.generate_terraform(list(resources))
    return {p.name: p.read_text() for p in provider.terraform_dir.glob("*") if p.is_file()}


@pytest.fixture
def oauth_env(provider: TailscaleProvider, monkeypatch: pytest.MonkeyPatch) -> TailscaleProvider:
    monkeypatch.setattr(
        provider, "_load_environment_config", lambda: make_env(OAUTH_URIS, OAUTH_SECRETS)
    )
    return provider


class TestHclFilters:
    def test_escapes_quotes_backslashes_newlines(self) -> None:
        assert hcl_string('a"b\\c\nd') == '"a\\"b\\\\c\\nd"'

    def test_escapes_interpolation_sequences(self) -> None:
        assert hcl_string("x ${var.a} %{if b}") == '"x $${var.a} %%{if b}"'

    def test_list(self) -> None:
        assert hcl_list(["tag:a", 'b"c']) == '["tag:a", "b\\"c"]'
        assert hcl_list([]) == "[]"


class TestProviderAndVariables:
    def test_provider_tf(self, oauth_env: TailscaleProvider) -> None:
        files = _generate(oauth_env)
        assert 'source  = "tailscale/tailscale"' in files["provider.tf"]
        assert 'version = "~> 0.29.3"' in files["provider.tf"]
        assert "var.tailscale_oauth_client_secret" in files["provider.tf"]

    def test_variables_tf(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(oauth_env)["variables.tf"]
        for name in ("api_key", "oauth_client_id", "oauth_client_secret"):
            block = text.split(f'variable "tailscale_{name}"')[1].split("}")[0]
            assert "sensitive   = true" in block
        assert text.count("default     = null") == 6

    def test_no_secret_in_any_file_and_no_tfvars(self, oauth_env: TailscaleProvider) -> None:
        files = _generate(
            oauth_env,
            res("key", "tailnet_key", tags=["tag:server"]),
            res("acl", "acl", policy=POLICY),
        )
        assert "terraform.tfvars" not in files
        for text in files.values():
            for sentinel in (SECRET_ID, SECRET_VALUE, "secret://"):
                assert sentinel not in text


class TestAcl:
    def test_policy_rendered_as_json_string(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(oauth_env, res("main", "acl", policy=POLICY))["acl.tf"]
        assert 'resource "tailscale_acl" "main"' in text
        assert '\\"tagOwners\\"' in text

    def test_hujson_comment_kept(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(oauth_env, res("main", "acl", hujson="{\n  // keep me\n}\n"))["acl.tf"]
        assert "// keep me" in text

    def test_interpolation_escaped(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(oauth_env, res("main", "acl", hujson="{ // ${x}\n}"))["acl.tf"]
        assert "$${x}" in text
        assert "${x}" not in text.replace("$${x}", "")

    def test_flags_omitted_by_default(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(oauth_env, res("main", "acl", policy=POLICY))["acl.tf"]
        assert "overwrite_existing_content" not in text
        assert "reset_acl_on_destroy" not in text

    def test_flags_rendered_when_set(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(
            oauth_env,
            res(
                "main",
                "acl",
                policy=POLICY,
                overwrite_existing_content=True,
                reset_acl_on_destroy=True,
            ),
        )["acl.tf"]
        assert "overwrite_existing_content = true" in text
        assert "reset_acl_on_destroy = true" in text

    def test_import_id_yields_import_block(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(oauth_env, res("main-acl", "acl", policy=POLICY, import_id="acl"))[
            "acl.tf"
        ]
        assert 'import {\n  to = tailscale_acl.main_acl\n  id = "acl"\n}' in text


class TestTailnetKey:
    def test_fields_and_depends_on_acl(self, oauth_env: TailscaleProvider) -> None:
        files = _generate(
            oauth_env,
            res("main", "acl", policy=POLICY),
            res(
                "node-key",
                "tailnet_key",
                tags=["tag:server"],
                expiry=3600,
                reusable=False,
                preauthorized=True,
                ephemeral=False,
                description="example",
                recreate_if_invalid="always",
            ),
        )
        text = files["tailnet_key.tf"]
        assert 'resource "tailscale_tailnet_key" "node_key"' in text
        assert 'tags                = ["tag:server"]' in text
        assert "expiry              = 3600" in text
        assert "reusable            = false" in text
        assert "preauthorized       = true" in text
        assert 'description         = "example"' in text
        assert 'recreate_if_invalid = "always"' in text
        assert "depends_on          = [tailscale_acl.main]" in text

    def test_no_depends_on_without_acl(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(oauth_env, res("k", "tailnet_key", tags=["tag:server"]))["tailnet_key.tf"]
        assert "depends_on" not in text

    def test_outputs_sensitive(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(oauth_env, res("node-key", "tailnet_key", tags=["tag:server"]))[
            "outputs.tf"
        ]
        block = text.split('output "tailnet_key_node_key"')[1].split("}")[0]
        assert "sensitive   = true" in block
        assert "tailscale_tailnet_key.node_key.key" in block
        assert 'output "tailnet_keys"' in text

    def test_no_key_outputs_without_keys(self, oauth_env: TailscaleProvider) -> None:
        assert "output" not in _generate(oauth_env)["outputs.tf"]


class TestDevices:
    def test_routes_with_device_lookup(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(
            oauth_env,
            res(
                "fw",
                "device_subnet_routes",
                device={"hostname": "fw-test", "wait_for": "120s"},
                routes=["192.0.2.0/24"],
            ),
        )["device_subnet_routes.tf"]
        assert 'data "tailscale_device" "fw_device" {\n  hostname = "fw-test"' in text
        assert 'wait_for = "120s"' in text
        assert "device_id = data.tailscale_device.fw_device.node_id" in text
        assert 'routes    = ["192.0.2.0/24"]' in text

    def test_device_by_name(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(
            oauth_env,
            res("fw", "device_tags", device={"name": "fw-test.example.com"}, tags=["tag:server"]),
        )["device_tags.tf"]
        assert 'name     = "fw-test.example.com"' in text
        assert "wait_for" not in text

    def test_raw_device_id_has_no_data_source(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(
            oauth_env, res("fw", "device_tags", device_id="12345", tags=["tag:server"])
        )["device_tags.tf"]
        assert 'device_id = "12345"' in text
        assert "data " not in text

    def test_depends_on_acl(self, oauth_env: TailscaleProvider) -> None:
        files = _generate(
            oauth_env,
            res("main", "acl", policy=POLICY),
            res("fw", "device_tags", device_id="1", tags=["tag:server"]),
        )
        assert "depends_on = [tailscale_acl.main]" in files["device_tags.tf"]


class TestDns:
    def test_three_resources(self, oauth_env: TailscaleProvider) -> None:
        text = _generate(
            oauth_env,
            res("ns", "dns_nameservers", nameservers=["192.0.2.53", "2001:db8::53"]),
            res("prefs", "dns_preferences", magic_dns=True),
            res("paths", "dns_search_paths", search_paths=["example.com"]),
        )["dns.tf"]
        assert 'nameservers = ["192.0.2.53", "2001:db8::53"]' in text
        assert "magic_dns = true" in text
        assert 'search_paths = ["example.com"]' in text

    def test_no_dns_file_without_dns_resources(self, oauth_env: TailscaleProvider) -> None:
        assert "dns.tf" not in _generate(oauth_env, res("main", "acl", policy=POLICY))


class TestValidationOnGenerate:
    def test_invalid_config_raises_listing_check_names(self, oauth_env: TailscaleProvider) -> None:
        with pytest.raises(SchemaValidationError) as excinfo:
            oauth_env.generate_terraform(
                [res("main", "acl"), res("k", "tailnet_key")]  # no input; OAuth key w/o tags
            )
        message = str(excinfo.value)
        assert "tailscale_acl_main" in message
        assert "tailscale_key_tags_k" in message
        assert SECRET_VALUE not in message

    def test_api_key_with_oauth_blocks_generation(
        self, provider: TailscaleProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            provider,
            "_load_environment_config",
            lambda: make_env({**OAUTH_URIS, "api_key": "secret://env_secrets/tailscale/k"}),
        )
        with pytest.raises(SchemaValidationError, match="tailscale_credentials_conflict"):
            provider.generate_terraform([])

    def test_stale_files_removed(self, oauth_env: TailscaleProvider) -> None:
        _generate(oauth_env, res("main", "acl", policy=POLICY))
        assert "acl.tf" not in _generate(oauth_env)

    def test_output_dir_under_provider_name(self, oauth_env: TailscaleProvider) -> None:
        _generate(oauth_env)
        assert oauth_env.terraform_dir == Path(oauth_env.base_output_dir) / "test" / (
            "terraform/tailscale"
        )
