"""Unit tests for ``FirewallRuleManager``.

Coverage:
    - ``plan`` returns ``Diff`` and threads ``add_only``.
    - ``apply`` returns counts dict + ``resource_outcomes`` for adds /
      updates / deletes; ``ResourceOutcome.address`` is
      ``opnsense_firewall_rule.<name>``.
    - ``destroy`` deletes managed rules, honors ``lock``, calls
      ``apply_changes`` only when at least one delete happened.
    - ``get_resource_ids`` maps operator names to live UUIDs.
    - ``list`` and ``migrate`` delegate to the service layer correctly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import AuthenticationError, PartialExtractionError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.firewall_rule import FirewallRuleManager
from infrafoundry.providers.opnsense.services.firewall_rule import (
    Diff,
    FirewallRuleConfig,
    LiveFirewallRule,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(name: str, *, lock: bool = False, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "interface": "lan",
        "description": f"{name} desc",
    }
    if lock:
        config["lock"] = True
    config.update(overrides)
    return ResourceConfig(name=name, type="firewall.rules", provider="opnsense", config=config)


def _live_managed(uuid: str, name: str) -> LiveFirewallRule:
    return LiveFirewallRule(
        uuid=uuid,
        managed_name=name,
        description="",
        raw={"uuid": uuid, "description": f"[infrafoundry:{name}]"},
    )


SERVICE_PATH = "infrafoundry.providers.opnsense.components.firewall_rule.FirewallRuleService"


def _make_service_mock(
    *,
    live: list[LiveFirewallRule] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mocked ``FirewallRuleService`` with sensible defaults."""
    service = MagicMock()
    service.search.return_value = live if live is not None else []
    service.compute_diff.return_value = diff if diff is not None else Diff()
    service.apply_diff.return_value = (
        apply_counts if apply_counts is not None else {"created": 0, "updated": 0, "deleted": 0}
    )
    return service


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_returns_diff(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[FirewallRuleConfig(name="foo", interface="lan")])
        service_mock = _make_service_mock(diff=diff)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", resources)
        assert result.adds == diff.adds
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)
        service_mock.compute_diff.assert_called_once()

    def test_threads_add_only(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True

    def test_passes_provider_name(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", [], provider_name="opnsense-prod")
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense-prod", tmp_path)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_returns_counts_dict(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[FirewallRuleConfig(name="foo", interface="lan")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        assert result["resources_created"] == 1
        assert result["resources_updated"] == 0
        assert result["resources_deleted"] == 0
        assert result["success"] is True

    def test_apply_emits_add_outcome(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[FirewallRuleConfig(name="foo", interface="lan")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "add"
        assert outcomes[0].resource_name == "foo"
        assert outcomes[0].address == "opnsense_firewall_rule.foo"

    def test_apply_emits_update_outcome(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        live = _live_managed("u1", "foo")
        want = FirewallRuleConfig(name="foo", interface="lan")
        diff = Diff(updates=[(live, want)])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 1, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "update"
        assert outcomes[0].resource_name == "foo"
        assert outcomes[0].address == "opnsense_firewall_rule.foo"

    def test_apply_emits_delete_outcome(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = _live_managed("u1", "stale")
        diff = Diff(deletes=[live])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 0, "deleted": 1}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "delete"
        assert outcomes[0].resource_name == "stale"
        assert outcomes[0].address == "opnsense_firewall_rule.stale"

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True

    def test_apply_outcomes_order_adds_updates_deletes(self, tmp_path: Path) -> None:
        # Mixed diff — outcomes list must preserve the
        # adds → updates → deletes ordering used by the manager.
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("a"), _resource("b"), _resource("c")]
        live_b = _live_managed("u-b", "b")
        live_c = _live_managed("u-c", "c")
        diff = Diff(
            adds=[FirewallRuleConfig(name="a", interface="lan")],
            updates=[(live_b, FirewallRuleConfig(name="b", interface="lan"))],
            deletes=[live_c],
        )
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 1, "deleted": 1}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert [o.action for o in outcomes] == ["add", "update", "delete"]
        assert [o.resource_name for o in outcomes] == ["a", "b", "c"]

    def test_apply_synthesizes_delete_name_from_managed_name(self, tmp_path: Path) -> None:
        # The manager synthesizes the address from ``live.managed_name``;
        # the diff engine guarantees that's non-None for delete entries.
        manager = FirewallRuleManager(tmp_path)
        live = _live_managed("u1", "stale-rule")
        diff = Diff(deletes=[live])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 0, "deleted": 1}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", [])
        assert result["resource_outcomes"][0].address == "opnsense_firewall_rule.stale-rule"


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_managed_rules(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        live = [_live_managed("u1", "foo")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_called_once_with("u1")
        service_mock.apply_changes.assert_called_once()
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0
        assert result["success"] is True

    def test_destroy_skips_when_no_live_match(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(live=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        # Apply must NOT be called when nothing was deleted.
        service_mock.apply_changes.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("wan-survival", lock=True)]
        live = [_live_managed("u1", "wan-survival")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.apply_changes.assert_not_called()
        assert result["locked_skipped"] == 1
        assert result["resources_destroyed"] == 0

    def test_destroy_mixed_locked_and_unlocked(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [
            _resource("locked-one", lock=True),
            _resource("normal-two"),
        ]
        live = [
            _live_managed("u-locked", "locked-one"),
            _live_managed("u-normal", "normal-two"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        # Only the unlocked rule is deleted.
        service_mock.delete.assert_called_once_with("u-normal")
        service_mock.apply_changes.assert_called_once()
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 1


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo"), _resource("bar")]
        live = [_live_managed("u1", "foo"), _live_managed("u2", "bar")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1", "bar": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo"), _resource("missing")]
        live = [_live_managed("u1", "foo")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}

    def test_unmanaged_live_excluded(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        # Live list contains an unmanaged row plus the matching managed one.
        live = [
            LiveFirewallRule(
                uuid="u-unmanaged",
                managed_name=None,
                description="manual rule",
                raw={"uuid": "u-unmanaged", "description": "manual rule"},
            ),
            _live_managed("u1", "foo"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}


# ---------------------------------------------------------------------------
# list / migrate
# ---------------------------------------------------------------------------


class TestListAndMigrate:
    def test_list_returns_live_rules(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        live = [_live_managed("u1", "foo")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        assert result == live
        service_mock.search.assert_called_once()

    def test_migrate_returns_yaml_string(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")
        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once()


# ---------------------------------------------------------------------------
# deletes_only (delete phase, #1269)
# ---------------------------------------------------------------------------


class TestDeletesOnly:
    def test_deletes_only_drops_adds_and_updates(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        live_keep = _live_managed("u-keep", "keep")
        live_gone = _live_managed("u-gone", "gone")
        diff = Diff(
            adds=[FirewallRuleConfig(name="new", interface="lan")],
            updates=[(live_keep, FirewallRuleConfig(name="keep", interface="lan"))],
            deletes=[live_gone],
        )
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 0, "deleted": 1}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply(
                "test-env",
                [_resource("keep")],
                deletes_only=True,
            )
        sent = service_mock.apply_diff.call_args.args[0]
        assert sent.adds == []
        assert sent.updates == []
        assert len(sent.deletes) == 1
        assert result["resources_created"] == 0
        assert result["resources_updated"] == 0
        assert result["resources_deleted"] == 1
        assert [o.action for o in result["resource_outcomes"]] == ["delete"]


# ---------------------------------------------------------------------------
# migrate --include-legacy (#1497)
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures"
_COMPONENT = "infrafoundry.providers.opnsense.components.firewall_rule"


class _RecordingClient:
    """Fake OPNsense client that allows only the read-only calls migrate makes.

    ``searchRule`` is a POST on the wire but read-only; every other request raises.
    """

    def __init__(self, rows: list[dict[str, Any]], backup: str | Exception) -> None:
        self.rows = rows
        self.backup = backup
        self.requests: list[tuple[str, str]] = []
        self.text_requests: list[str] = []

    def request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.requests.append((method, endpoint))
        if (method, endpoint) == ("POST", "firewall/filter/searchRule"):
            return {"rows": self.rows}
        raise AssertionError(f"unexpected call {method} {endpoint}")

    def get_text(self, endpoint: str, params: dict[str, Any] | None = None) -> str:
        self.text_requests.append(endpoint)
        if isinstance(self.backup, Exception):
            raise self.backup
        return self.backup


def _legacy_migrate(
    tmp_path: Path,
    client: _RecordingClient,
    *,
    reserved: list[ResourceConfig] | None = None,
) -> str:
    from infrafoundry.providers.opnsense.services.config_backup import ConfigBackupService
    from infrafoundry.providers.opnsense.services.firewall_rule import FirewallRuleService

    service = FirewallRuleService(client)
    service._category_uuid = "marker-uuid"
    with (
        patch(SERVICE_PATH) as svc_cls,
        patch(f"{_COMPONENT}.ConfigBackupService") as backup_cls,
        patch(f"{_COMPONENT}.env_provider_resources", return_value=reserved or []),
    ):
        svc_cls.from_environment.return_value = service
        backup_cls.from_environment.return_value = ConfigBackupService(client)  # type: ignore[arg-type]
        return FirewallRuleManager(tmp_path).migrate("test-env", include_legacy=True)


def _live_row(uuid: str, description: str, sequence: str, **extra: str) -> dict[str, Any]:
    return {
        "uuid": uuid,
        "description": description,
        "sequence": sequence,
        "interface": "lan",
        "action": "pass",
        "enabled": "1",
        **extra,
    }


def _entries(yaml_text: str) -> list[dict[str, Any]]:
    data = yaml.safe_load(yaml_text)
    leaf: list[dict[str, Any]] = data["opnsense"]["firewall"]["rules"]
    return leaf


class TestMigrateIncludeLegacy:
    def test_exclusion_never_builds_the_backup_service(self, tmp_path: Path) -> None:
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "x: y\n"
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(f"{_COMPONENT}.ConfigBackupService") as backup_cls,
        ):
            svc_cls.from_environment.return_value = service_mock
            result = FirewallRuleManager(tmp_path).migrate("test-env")
        assert result == "x: y\n"
        backup_cls.from_environment.assert_not_called()

    def test_clean_backup_is_exported_after_the_highest_live_sequence(self, tmp_path: Path) -> None:
        clean = (_FIXTURES / "legacy_filter_config_clean.xml").read_text()
        client = _RecordingClient(
            [
                _live_row("u1", "managed one [infrafoundry:managed-one]", "20"),
                _live_row("u2", "unmanaged but high", "450"),
            ],
            clean,
        )
        entries = _entries(_legacy_migrate(tmp_path, client))
        names = [e["name"] for e in entries]
        assert names[0] == "managed-one"
        assert names[1:] == [
            "allow-web",
            "block-host",
            "floating-block",
            "reject-ssh",
            "guest-ping",
            "trusted-rule-6",
        ]
        assert [e["config"]["sequence"] for e in entries[1:]] == [
            550,
            560,
            570,
            580,
            590,
            600,
        ]
        assert client.text_requests == ["core/backup/download/this"]
        assert all(call == ("POST", "firewall/filter/searchRule") for call in client.requests)

    def test_sequence_starts_at_100_with_no_live_rules(self, tmp_path: Path) -> None:
        clean = (_FIXTURES / "legacy_filter_config_clean.xml").read_text()
        entries = _entries(_legacy_migrate(tmp_path, _RecordingClient([], clean)))
        assert entries[0]["config"]["sequence"] == 100

    def test_existing_resource_names_are_avoided(self, tmp_path: Path) -> None:
        clean = (_FIXTURES / "legacy_filter_config_clean.xml").read_text()
        taken = ResourceConfig(
            name="allow-web", type="firewall.aliases", provider="opnsense", config={}
        )
        entries = _entries(_legacy_migrate(tmp_path, _RecordingClient([], clean), reserved=[taken]))
        assert entries[0]["name"] == "allow-web-2"

    def test_issues_raise_partial_error_with_header_and_parseable_yaml(
        self, tmp_path: Path
    ) -> None:
        backup = (_FIXTURES / "legacy_filter_config.xml").read_text()
        with pytest.raises(PartialExtractionError) as excinfo:
            _legacy_migrate(tmp_path, _RecordingClient([], backup))
        exc = excinfo.value
        assert exc.issues
        assert exc.yaml_content.startswith("# Legacy rule fields not exported")
        for issue in exc.issues:
            assert f"# - {issue}" in exc.yaml_content
        assert "allow-web" in [e["name"] for e in _entries(exc.yaml_content)]

    def test_backup_download_failure_reports_the_privilege_and_keeps_automation_rules(
        self, tmp_path: Path
    ) -> None:
        client = _RecordingClient(
            [_live_row("u1", "managed one [infrafoundry:managed-one]", "20")],
            AuthenticationError("denied", status_code=403),
        )
        with pytest.raises(PartialExtractionError) as excinfo:
            _legacy_migrate(tmp_path, client)
        assert "backup-download privilege" in excinfo.value.issues[0]
        assert [e["name"] for e in _entries(excinfo.value.yaml_content)] == ["managed-one"]

    def test_invalid_backup_xml_is_reported_without_the_document(self, tmp_path: Path) -> None:
        client = _RecordingClient([], "<opnsense><secret>hunter2</opnsense>")
        with pytest.raises(PartialExtractionError) as excinfo:
            _legacy_migrate(tmp_path, client)
        assert "hunter2" not in "\n".join(excinfo.value.issues)
        assert "hunter2" not in excinfo.value.yaml_content

    def test_nothing_is_written_to_the_firewall(self, tmp_path: Path) -> None:
        """Only the read-only search and the backup download run; any other call fails."""
        clean = (_FIXTURES / "legacy_filter_config_clean.xml").read_text()
        client = _RecordingClient([], clean)
        _legacy_migrate(tmp_path, client)
        assert set(client.requests) == {("POST", "firewall/filter/searchRule")}
        assert client.text_requests == ["core/backup/download/this"]


class TestLegacyRoundTrip:
    """The exported YAML loads, validates and plans as an empty diff once applied."""

    def _exported(self, tmp_path: Path) -> tuple[str, list[ResourceConfig]]:
        clean = (_FIXTURES / "legacy_filter_config_clean.xml").read_text()
        yaml_text = _legacy_migrate(tmp_path, _RecordingClient([], clean))
        nested = yaml.safe_load(yaml_text)["opnsense"]
        loader = PackageLoader(base_dir=Path("/tmp/unused"))
        resources = loader._parse_nested_provider_format(nested, "opnsense", "legacy.yaml")
        return yaml_text, resources

    def test_loader_reads_the_expected_automation_set(self, tmp_path: Path) -> None:
        _, resources = self._exported(tmp_path)
        by_name = {r.name: r.config for r in resources}
        assert list(by_name) == [
            "allow-web",
            "block-host",
            "floating-block",
            "reject-ssh",
            "guest-ping",
            "trusted-rule-6",
        ]
        assert by_name["floating-block"] == {
            "name": "floating-block",
            "action": "block",
            "interface": "",
            "description": "Floating block",
            "state_policy": "floating",
            "quick": True,
            "direction": "any",
            "ipprotocol": "inet",
            "protocol": "UDP",
            "source_net": "any",
            "destination_port": "53",
            "destination_net": "198.51.100.0/24",
            "sequence": 100 + 20,
        }

    def test_exported_rules_pass_the_validator(self, tmp_path: Path) -> None:
        from infrafoundry.core.validation import ValidationLevel, ValidationReport
        from infrafoundry.providers.opnsense.validators.context import (
            OPNsenseValidationContext,
        )
        from infrafoundry.providers.opnsense.validators.firewall_rule_validator import (
            FirewallRuleValidator,
        )

        _, resources = self._exported(tmp_path)
        report = ValidationReport()
        FirewallRuleValidator(report).validate(
            OPNsenseValidationContext(
                firewall_rules=resources,
                alias_names={"example_hosts"},
                interface_assignment_names={"lan", "opt1", "opt2", "trusted"},
                gateway_names={"WAN_GW"},
                existing_interfaces={},
                existing_aliases={},
                existing_gateways=set(),
            )
        )
        errors = [i for i in report.results if not i.passed and i.level == ValidationLevel.ERROR]
        assert report.results
        assert errors == []

    def test_plan_over_the_applied_set_is_empty(self, tmp_path: Path) -> None:
        from infrafoundry.providers.opnsense.services.firewall_rule import (
            FirewallRuleService,
            firewall_rule_configs_from_resources,
        )

        _, resources = self._exported(tmp_path)
        builder = FirewallRuleService(MagicMock())
        builder._category_uuid = "marker-uuid"
        rows = []
        for n, cfg in enumerate(firewall_rule_configs_from_resources(resources)):
            row: dict[str, Any] = dict(builder._payload_with_category(cfg)["rule"])
            row["uuid"] = f"live-{n}"
            rows.append(row)

        service = FirewallRuleService(_RecordingClient(rows, ""))
        service._category_uuid = "marker-uuid"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = FirewallRuleManager(tmp_path).plan("test-env", resources)
        assert diff.is_empty
