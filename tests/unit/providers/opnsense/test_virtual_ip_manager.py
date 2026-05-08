"""Unit tests for ``VirtualIPManager``.

Coverage:
    - ``plan/apply/destroy`` delegate to ``VirtualIPService`` correctly.
    - ``apply`` emits ``ResourceOutcome`` entries for adds/updates/deletes.
    - delete outcomes use the synthesized ``vip-<mode>-<iface>-<addr>...``
      name.
    - ``get_resource_ids`` maps live UUIDs to operator-facing names by
      tuple match.
    - ``migrate`` exports YAML.
    - ``lock`` semantics honored on destroy.
    - ``add_only`` flag propagated to ``compute_diff``.
    - **Secret resolution path**: ``secret://env_secrets/<path>`` URIs
      in resource configs are resolved via ``SecretResolver`` /
      ``EnvSecretsBackend`` before the parser sees them. Unresolvable
      URIs raise ``SecretResolutionError`` at plan/apply time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.virtual_ip import VirtualIPManager
from infrafoundry.providers.opnsense.services.virtual_ip import (
    Diff,
    LiveVirtualIP,
    VirtualIPConfig,
)
from infrafoundry.secrets.resolver import SecretResolutionError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(
    name: str,
    *,
    interface: str = "lan",
    mode: str = "ipalias",
    address: str = "10.0.0.10",
    network: str = "24",
    lock: bool = False,
    extras: dict[str, Any] | None = None,
) -> ResourceConfig:
    config: dict[str, Any] = {
        "interface": interface,
        "mode": mode,
        "address": address,
        "network": network,
        "description": f"{name} desc",
    }
    if lock:
        config["lock"] = True
    if extras:
        config.update(extras)
    return ResourceConfig(
        name=name, type="interfaces.virtual_ips", provider="opnsense", config=config
    )


def _live(
    uuid: str,
    *,
    interface: str = "lan",
    mode: str = "ipalias",
    address: str = "10.0.0.10",
    vhid: str = "",
) -> LiveVirtualIP:
    return LiveVirtualIP(
        uuid=uuid,
        interface=interface,
        mode=mode,
        address=address,
        vhid=vhid,
        raw={
            "uuid": uuid,
            "interface": interface,
            "mode": mode,
            "address": address,
            "network": "24",
            "vhid": vhid,
        },
    )


def _vip(name: str, **overrides: Any) -> VirtualIPConfig:
    return VirtualIPConfig(
        name=name,
        interface=overrides.get("interface", "lan"),
        mode=overrides.get("mode", "ipalias"),  # type: ignore[arg-type]
        address=overrides.get("address", "10.0.0.10"),
        network=overrides.get("network", "24"),
        description=overrides.get("description", ""),
        enabled=overrides.get("enabled", True),
        lock=overrides.get("lock", False),
        password=overrides.get("password", ""),
        vhid=overrides.get("vhid", ""),
        advbase=overrides.get("advbase", "1"),
        advskew=overrides.get("advskew", "0"),
        peer=overrides.get("peer", ""),
        peer6=overrides.get("peer6", ""),
        nosync=overrides.get("nosync", False),
        gateway=overrides.get("gateway", ""),
        noexpand=overrides.get("noexpand", False),
        nobind=overrides.get("nobind", False),
    )


SERVICE_PATH = "infrafoundry.providers.opnsense.components.virtual_ip.VirtualIPService"
CONFIG_MANAGER_PATH = "infrafoundry.providers.opnsense.components.virtual_ip.ConfigManager"


def _make_service_mock(
    *,
    live: list[LiveVirtualIP] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mocked ``VirtualIPService`` with sensible defaults."""
    service = MagicMock()
    service.search.return_value = live if live is not None else []
    service.compute_diff.return_value = diff if diff is not None else Diff()
    service.apply_diff.return_value = (
        apply_counts if apply_counts is not None else {"created": 0, "updated": 0, "deleted": 0}
    )
    return service


def _patch_config_manager(secrets: dict[str, Any] | None = None) -> Any:
    """Patch ``ConfigManager.load_environment`` to return an env with given secrets."""
    env_config = MagicMock()
    env_config.secrets = secrets
    cm_class = MagicMock()
    cm_instance = MagicMock()
    cm_instance.load_environment.return_value = env_config
    cm_class.return_value = cm_instance
    return cm_class


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_returns_diff(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_vip("foo")])
        service_mock = _make_service_mock(diff=diff)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", resources)
        assert result.adds == diff.adds
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)
        service_mock.compute_diff.assert_called_once()

    def test_threads_add_only(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_returns_counts(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_vip("foo")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        assert result["resources_created"] == 1
        assert result["success"] is True

    def test_apply_emits_add_outcome(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_vip("foo")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "add"
        assert outcomes[0].resource_name == "foo"
        assert outcomes[0].address == "opnsense_virtual_ip.foo"

    def test_apply_emits_update_outcome(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources = [_resource("foo")]
        live = _live("u1")
        want = _vip("foo")
        diff = Diff(updates=[(live, want)])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 1, "deleted": 0}
        )
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "update"
        assert outcomes[0].address == "opnsense_virtual_ip.foo"

    def test_apply_emits_delete_outcome_with_synthetic_name(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = _live("u1", interface="lan", mode="ipalias", address="172.16.0.10")
        diff = Diff(deletes=[live])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 0, "deleted": 1}
        )
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "delete"
        # Synthetic ``vip-<mode>-<iface>-<addr>`` form.
        assert outcomes[0].resource_name == "vip-ipalias-lan-172-16-0-10"
        assert outcomes[0].address == "opnsense_virtual_ip.vip-ipalias-lan-172-16-0-10"

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_vips(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources = [_resource("foo")]
        live = [_live("u1")]
        service_mock = _make_service_mock(live=live)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_called_once_with("u1")
        service_mock.reconfigure.assert_called_once()
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0

    def test_destroy_skips_when_no_live_match(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(live=[])
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.reconfigure.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources = [_resource("survival", lock=True)]
        live = [_live("u1")]
        service_mock = _make_service_mock(live=live)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        assert result["locked_skipped"] == 1


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids_by_tuple(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources = [
            _resource("foo", address="10.0.0.10"),
            _resource("bar", address="10.0.0.20"),
        ]
        live = [
            _live("u1", address="10.0.0.10"),
            _live("u2", address="10.0.0.20"),
        ]
        service_mock = _make_service_mock(live=live)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1", "bar": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        resources = [
            _resource("foo", address="10.0.0.10"),
            _resource("missing", address="192.168.0.10"),
        ]
        live = [_live("u1", address="10.0.0.10")]
        service_mock = _make_service_mock(live=live)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager()),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}


# ---------------------------------------------------------------------------
# list / migrate
# ---------------------------------------------------------------------------


class TestListAndMigrate:
    def test_list_returns_live_vips(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        live = [_live("u1"), _live("u2", address="10.0.0.20")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        assert result == live

    def test_migrate_returns_yaml_string(self, tmp_path: Path) -> None:
        manager = VirtualIPManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")
        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once()


# ---------------------------------------------------------------------------
# Secret resolution path
# ---------------------------------------------------------------------------


def _register_env_secrets_backend() -> None:
    """Register the env_secrets backend in the test plugin registry.

    Mirrors ``tests/unit/secrets/backends/test_env_secrets.py``.
    """
    import contextlib

    from infrafoundry.core.plugin_system import get_registry
    from infrafoundry.core.plugin_system.exceptions import PluginConflictError
    from infrafoundry.core.plugin_system.plugin_type import PluginMetadata
    from infrafoundry.secrets.backends.env_secrets import EnvSecretsBackend

    registry = get_registry()
    with contextlib.suppress(PluginConflictError):
        registry.register(
            PluginMetadata(
                name="env_secrets",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretsBackend,
            )
        )


class TestSecretResolution:
    def test_secret_uri_resolved_before_parser(self, tmp_path: Path) -> None:
        # Build a CARP resource with a secret:// URI. The manager must
        # call resolve_config so the parser sees plaintext.
        _register_env_secrets_backend()
        secrets = {"opnsense": {"carp_passwords": {"lan_carp_1": "s3kr1t-carp-pass"}}}
        resources = [
            _resource(
                "lan-carp",
                mode="carp",
                extras={
                    "vhid": "1",
                    "password": "secret://env_secrets/opnsense/carp_passwords/lan_carp_1",
                },
            )
        ]
        service_mock = _make_service_mock(diff=Diff(adds=[]))
        manager = VirtualIPManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager(secrets=secrets)),
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources)

        # Verify the parser received plaintext via ``compute_diff``.
        # ``compute_diff`` is called with positional arg desired
        # configs.
        compute_call = service_mock.compute_diff.call_args
        desired_list = compute_call.args[0]
        assert len(desired_list) == 1
        assert desired_list[0].password == "s3kr1t-carp-pass"

    def test_secret_resolution_failure_surfaces(self, tmp_path: Path) -> None:
        # Operator referenced a secret path that does not exist in
        # env_config.secrets. Manager must raise SecretResolutionError.
        _register_env_secrets_backend()
        secrets = {"opnsense": {"carp_passwords": {"lan_carp_1": "x"}}}
        resources = [
            _resource(
                "lan-carp",
                mode="carp",
                extras={
                    "vhid": "1",
                    "password": "secret://env_secrets/opnsense/carp_passwords/MISSING",
                },
            )
        ]
        service_mock = _make_service_mock()
        manager = VirtualIPManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager(secrets=secrets)),
        ):
            svc_cls.from_environment.return_value = service_mock
            with pytest.raises(SecretResolutionError):
                manager.plan("test-env", resources)

    def test_no_secrets_attribute_treated_as_empty(self, tmp_path: Path) -> None:
        # ``env_config.secrets`` may be None when SOPS isn't configured;
        # the manager should not crash for resources without secret URIs.
        _register_env_secrets_backend()
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        manager = VirtualIPManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager(secrets=None)),
        ):
            svc_cls.from_environment.return_value = service_mock
            # Should not raise.
            manager.plan("test-env", resources)

    def test_plaintext_password_passes_through(self, tmp_path: Path) -> None:
        # If the operator provides plaintext (validator warns), the
        # resolver leaves it alone.
        _register_env_secrets_backend()
        resources = [
            _resource(
                "lan-carp",
                mode="carp",
                extras={"vhid": "1", "password": "plaintext-pass"},
            )
        ]
        service_mock = _make_service_mock(diff=Diff())
        manager = VirtualIPManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(CONFIG_MANAGER_PATH, _patch_config_manager(secrets={})),
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources)

        compute_call = service_mock.compute_diff.call_args
        desired_list = compute_call.args[0]
        assert desired_list[0].password == "plaintext-pass"
