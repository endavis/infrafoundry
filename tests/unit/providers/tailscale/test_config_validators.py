"""Tests for the Tailscale resource-config and credential validators."""

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.tailscale.validators import (
    AclValidator,
    CredentialsValidator,
    DeviceReferenceValidator,
    DnsValidator,
    NamingValidator,
    TailnetKeyValidator,
)
from infrafoundry.providers.tailscale.validators.context import (
    TailscaleConfigContext,
    TailscaleCredentialsContext,
)

from .conftest import res

POLICY: dict[str, Any] = {"tagOwners": {"tag:server": ["autogroup:admin"]}}


def _errors(report: ValidationReport) -> set[str]:
    return {
        r.check_name for r in report.results if not r.passed and r.level == ValidationLevel.ERROR
    }


def _warnings(report: ValidationReport) -> set[str]:
    return {
        r.check_name for r in report.results if not r.passed and r.level == ValidationLevel.WARNING
    }


def _ctx(
    resources: list[ResourceConfig],
    auth_mode: str = "api_key",
    acl_policy: dict[str, Any] | None = None,
) -> TailscaleConfigContext:
    return TailscaleConfigContext(resources=resources, auth_mode=auth_mode, acl_policy=acl_policy)


class TestNaming:
    def test_duplicate_singleton(self) -> None:
        report = ValidationReport()
        NamingValidator(report).validate(
            _ctx([res("a", "acl", hujson="{}"), res("b", "acl", hujson="{}")])
        )
        assert _errors(report) == {"tailscale_singleton_acl"}

    def test_duplicate_dns_singletons(self) -> None:
        report = ValidationReport()
        NamingValidator(report).validate(
            _ctx(
                [
                    res("a", "dns_preferences", magic_dns=True),
                    res("b", "dns_preferences", magic_dns=False),
                    res("c", "dns_search_paths", search_paths=["example.com"]),
                ]
            )
        )
        assert _errors(report) == {"tailscale_singleton_dns_preferences"}

    def test_duplicate_name_across_types(self) -> None:
        report = ValidationReport()
        NamingValidator(report).validate(
            _ctx([res("x", "acl", hujson="{}"), res("x", "tailnet_key")])
        )
        assert _errors(report) == {"tailscale_duplicate_name_x"}

    def test_non_terraform_safe_name(self) -> None:
        report = ValidationReport()
        NamingValidator(report).validate(_ctx([res("1bad name", "tailnet_key")]))
        assert _errors(report) == {"tailscale_name_1bad name"}

    def test_valid_names_pass(self) -> None:
        report = ValidationReport()
        NamingValidator(report).validate(_ctx([res("good-name_1", "tailnet_key")]))
        assert not _errors(report)


class TestAcl:
    def test_both_inputs(self) -> None:
        report = ValidationReport()
        AclValidator(report).validate(_ctx([res("a", "acl", policy={}, hujson="{}")]))
        assert _errors(report) == {"tailscale_acl_a"}

    def test_neither_input(self) -> None:
        report = ValidationReport()
        AclValidator(report).validate(_ctx([res("a", "acl")]))
        assert _errors(report) == {"tailscale_acl_a"}

    def test_non_serialisable_policy(self) -> None:
        report = ValidationReport()
        AclValidator(report).validate(_ctx([res("a", "acl", policy={"x": {1, 2}})]))
        assert _errors(report) == {"tailscale_acl_a"}

    def test_non_mapping_policy_and_empty_hujson(self) -> None:
        report = ValidationReport()
        AclValidator(report).validate(
            _ctx([res("a", "acl", policy="text"), res("b", "acl", hujson="  ")])
        )
        assert _errors(report) == {"tailscale_acl_a", "tailscale_acl_b"}

    def test_flags_must_be_bool(self) -> None:
        report = ValidationReport()
        AclValidator(report).validate(
            _ctx([res("a", "acl", policy=POLICY, overwrite_existing_content="yes")])
        )
        assert _errors(report) == {"tailscale_acl_overwrite_existing_content_a"}

    def test_valid(self) -> None:
        report = ValidationReport()
        AclValidator(report).validate(
            _ctx([res("a", "acl", policy=POLICY, reset_acl_on_destroy=False)])
        )
        assert not _errors(report)


class TestTailnetKey:
    def test_oauth_requires_tags(self) -> None:
        report = ValidationReport()
        TailnetKeyValidator(report).validate(_ctx([res("k", "tailnet_key")], "oauth"))
        assert _errors(report) == {"tailscale_key_tags_k"}

    def test_api_key_allows_untagged(self) -> None:
        report = ValidationReport()
        TailnetKeyValidator(report).validate(_ctx([res("k", "tailnet_key")], "api_key"))
        assert not _errors(report)

    def test_bad_tag_format(self) -> None:
        report = ValidationReport()
        TailnetKeyValidator(report).validate(_ctx([res("k", "tailnet_key", tags=["server"])]))
        assert _errors(report) == {"tailscale_tags_k"}

    def test_bad_expiry_and_recreate(self) -> None:
        report = ValidationReport()
        TailnetKeyValidator(report).validate(
            _ctx(
                [
                    res("a", "tailnet_key", expiry=0),
                    res("b", "tailnet_key", expiry=True),
                    res("c", "tailnet_key", recreate_if_invalid="sometimes"),
                    res("d", "tailnet_key", reusable="no", description=5),
                ]
            )
        )
        assert _errors(report) == {
            "tailscale_key_expiry_a",
            "tailscale_key_expiry_b",
            "tailscale_key_recreate_c",
            "tailscale_key_reusable_d",
            "tailscale_key_description_d",
        }

    def test_tag_missing_from_tag_owners_warns(self) -> None:
        report = ValidationReport()
        TailnetKeyValidator(report).validate(
            _ctx([res("k", "tailnet_key", tags=["tag:other"])], "oauth", POLICY)
        )
        assert not _errors(report)
        assert _warnings(report) == {"tailscale_tag_owners_k"}

    def test_known_tag_does_not_warn(self) -> None:
        report = ValidationReport()
        TailnetKeyValidator(report).validate(
            _ctx([res("k", "tailnet_key", tags=["tag:server"])], "oauth", POLICY)
        )
        assert not _warnings(report)


class TestDevice:
    def _routes(self, name: str = "r", **config: Any) -> ResourceConfig:
        config.setdefault("routes", ["192.0.2.0/24"])
        return res(name, "device_subnet_routes", **config)

    def test_valid_forms(self) -> None:
        report = ValidationReport()
        DeviceReferenceValidator(report).validate(
            _ctx(
                [
                    self._routes("a", device={"hostname": "fw-test", "wait_for": "60s"}),
                    self._routes("b", device_id="1", routes=["2001:db8::/64"]),
                ]
            )
        )
        assert not _errors(report)

    def test_both_or_neither_reference(self) -> None:
        report = ValidationReport()
        DeviceReferenceValidator(report).validate(
            _ctx(
                [
                    self._routes("a", device={"hostname": "x"}, device_id="1"),
                    self._routes("b"),
                ]
            )
        )
        assert _errors(report) == {"tailscale_device_a", "tailscale_device_b"}

    def test_device_selector_rules(self) -> None:
        report = ValidationReport()
        DeviceReferenceValidator(report).validate(
            _ctx(
                [
                    self._routes("a", device={"hostname": "x", "name": "y"}),
                    self._routes("b", device={}),
                    self._routes("c", device={"hostname": "x", "wait_for": 5}),
                    self._routes("d", device={"hostname": "x", "bogus": 1}),
                    self._routes("e", device="fw"),
                ]
            )
        )
        assert _errors(report) == {f"tailscale_device_{c}" for c in "abcde"}

    def test_bad_cidr_and_host_bits(self) -> None:
        report = ValidationReport()
        DeviceReferenceValidator(report).validate(
            _ctx(
                [
                    self._routes("a", device_id="1", routes=["nope"]),
                    self._routes("b", device_id="2", routes=["192.0.2.1/24"]),
                    self._routes("c", device_id="3", routes=[]),
                ]
            )
        )
        assert _errors(report) == {f"tailscale_routes_{c}" for c in "abc"}

    def test_two_routes_resources_on_one_device(self) -> None:
        report = ValidationReport()
        DeviceReferenceValidator(report).validate(
            _ctx(
                [
                    self._routes("a", device={"hostname": "fw-test"}),
                    self._routes("b", device={"hostname": "fw-test"}),
                ]
            )
        )
        assert _errors(report) == {"tailscale_device_duplicate_b"}

    def test_routes_and_tags_on_one_device_is_fine(self) -> None:
        report = ValidationReport()
        DeviceReferenceValidator(report).validate(
            _ctx(
                [
                    self._routes("a", device={"hostname": "fw-test"}),
                    res("t", "device_tags", device={"hostname": "fw-test"}, tags=["tag:server"]),
                ]
            )
        )
        assert not _errors(report)

    def test_device_tags_validated_with_owner_warning(self) -> None:
        report = ValidationReport()
        DeviceReferenceValidator(report).validate(
            _ctx(
                [res("t", "device_tags", device_id="1", tags=["tag:other"])],
                "oauth",
                POLICY,
            )
        )
        assert _warnings(report) == {"tailscale_tag_owners_t"}
        assert not _errors(report)


class TestDns:
    def test_valid(self) -> None:
        report = ValidationReport()
        DnsValidator(report).validate(
            _ctx(
                [
                    res("n", "dns_nameservers", nameservers=["192.0.2.53", "2001:db8::53"]),
                    res("p", "dns_preferences", magic_dns=False),
                    res("s", "dns_search_paths", search_paths=["example.com"]),
                ]
            )
        )
        assert not _errors(report)

    def test_invalid(self) -> None:
        report = ValidationReport()
        DnsValidator(report).validate(
            _ctx(
                [
                    res("n", "dns_nameservers", nameservers=["dns.example.com"]),
                    res("e", "dns_nameservers", nameservers=[]),
                    res("p", "dns_preferences", magic_dns="true"),
                    res("s", "dns_search_paths", search_paths=[""]),
                ]
            )
        )
        assert _errors(report) == {
            "tailscale_dns_n",
            "tailscale_dns_e",
            "tailscale_dns_p",
            "tailscale_dns_s",
        }

    def test_ignores_other_types(self) -> None:
        report = ValidationReport()
        DnsValidator(report).validate(_ctx([res("k", "tailnet_key")]))
        assert not report.results


class TestCredentials:
    def _run(
        self, settings: dict[str, Any], env_oauth: bool = False, env_api_key: bool = False
    ) -> ValidationReport:
        report = ValidationReport()
        CredentialsValidator(report).validate(
            TailscaleCredentialsContext(
                provider_settings=settings, env_oauth=env_oauth, env_api_key=env_api_key
            )
        )
        return report

    def test_oauth_ok_with_unresolved_uris(self) -> None:
        report = self._run(
            {
                "oauth_client_id": "secret://env_secrets/tailscale/oauth_client_id",
                "oauth_client_secret": "secret://env_secrets/tailscale/oauth_client_secret",
                "scopes": ["dns"],
            }
        )
        assert not _errors(report)
        assert not _warnings(report)

    def test_api_key_with_oauth_conflicts(self) -> None:
        report = self._run({"api_key": "k", "oauth_client_id": "i", "oauth_client_secret": "s"})
        assert "tailscale_credentials_conflict" in _errors(report)

    def test_client_id_without_secret(self) -> None:
        report = self._run({"oauth_client_id": "i"})
        assert _errors(report) == {"tailscale_credentials_oauth_pair"}

    def test_scopes_without_oauth(self) -> None:
        report = self._run({"api_key": "k", "scopes": ["dns"]})
        assert _errors(report) == {"tailscale_credentials_scopes"}

    def test_nothing_set_warns(self) -> None:
        report = self._run({})
        assert _warnings(report) == {"tailscale_credentials_missing"}
        assert not _errors(report)

    def test_env_fallbacks_suppress_warning(self) -> None:
        assert not _warnings(self._run({}, env_oauth=True))
        assert not _warnings(self._run({}, env_api_key=True))
