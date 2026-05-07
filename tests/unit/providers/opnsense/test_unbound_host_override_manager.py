"""Unit tests for ``UnboundHostOverrideManager`` (#776).

Coverage:
    - plan/apply/destroy delegate to ``UnboundHostOverrideService`` correctly.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes.
    - delete outcomes use the synthesized ``<hostname>-<dot-replaced-domain>``
      name (with ``-<rr>`` suffix on non-A records).
    - get_resource_ids maps live UUIDs to operator-facing names by
      ``(hostname, domain, rr)`` natural-key tuple match.
    - migrate exports YAML.
    - lock semantics honored on destroy.
    - add_only flag propagated to compute_diff.
    - FINALIZATION_HOOK ClassVar declared and apply does NOT call
      ``service.reconfigure`` inline (#776 — runner fires the shared
      ``unbound_reconfigure`` hook).
    - Per-rr_type apply (A / AAAA / MX) for resource-outcome smoke
      coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.unbound_host_override import (
    UnboundHostOverrideManager,
)
from infrafoundry.providers.opnsense.services.unbound_host_override import (
    Diff,
    LiveUnboundHostOverride,
    UnboundHostOverrideConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(
    name: str,
    *,
    hostname: str = "web",
    domain: str = "example.com",
    rr: str = "A",
    server: str = "192.168.1.10",
    mxprio: str = "",
    mx: str = "",
    lock: bool = False,
) -> ResourceConfig:
    config: dict[str, Any] = {
        "hostname": hostname,
        "domain": domain,
        "server": server,
        "description": f"{name} desc",
    }
    if rr != "A":
        config["rr"] = rr
    if mxprio:
        config["mxprio"] = mxprio
    if mx:
        config["mx"] = mx
    if lock:
        config["lock"] = True
    return ResourceConfig(
        name=name, type="unbound_host_override", provider="opnsense", config=config
    )


def _live(
    uuid: str,
    *,
    hostname: str = "web",
    domain: str = "example.com",
    rr: str = "A",
    server: str = "192.168.1.10",
) -> LiveUnboundHostOverride:
    return LiveUnboundHostOverride(
        uuid=uuid,
        hostname=hostname,
        domain=domain,
        rr=rr,
        raw={
            "uuid": uuid,
            "hostname": hostname,
            "domain": domain,
            "rr": rr,
            "server": server,
            "description": "",
            "enabled": "1",
            "mxprio": "",
            "mx": "",
        },
    )


def _override(name: str, **overrides: Any) -> UnboundHostOverrideConfig:
    return UnboundHostOverrideConfig(
        name=name,
        hostname=overrides.get("hostname", "web"),
        domain=overrides.get("domain", "example.com"),
        rr=overrides.get("rr", "A"),
        server=overrides.get("server", "192.168.1.10"),
        description=overrides.get("description", ""),
        enabled=overrides.get("enabled", True),
        mxprio=overrides.get("mxprio", ""),
        mx=overrides.get("mx", ""),
        lock=overrides.get("lock", False),
    )


SERVICE_PATH = (
    "infrafoundry.providers.opnsense.components.unbound_host_override.UnboundHostOverrideService"
)


def _make_service_mock(
    *,
    live: list[LiveUnboundHostOverride] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mocked ``UnboundHostOverrideService`` with sensible defaults."""
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
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_override("foo")])
        service_mock = _make_service_mock(diff=diff)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", resources)
        assert result.adds == diff.adds
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)
        service_mock.compute_diff.assert_called_once()

    def test_threads_add_only(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_returns_counts(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_override("foo")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        assert result["resources_created"] == 1
        assert result["success"] is True

    def test_apply_emits_add_outcome_for_a_record(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_override("foo")])
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
        assert outcomes[0].address == "opnsense_unbound_host_override.foo"

    def test_apply_emits_add_outcome_for_aaaa_record(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("v6", rr="AAAA", server="2001:db8::10")]
        diff = Diff(adds=[_override("v6", rr="AAAA", server="2001:db8::10")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].resource_name == "v6"

    def test_apply_emits_add_outcome_for_mx_record(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [
            _resource(
                "mx-host",
                hostname="mail",
                rr="MX",
                server="",
                mxprio="10",
                mx="mail.example.com",
            )
        ]
        diff = Diff(
            adds=[
                _override(
                    "mx-host",
                    hostname="mail",
                    rr="MX",
                    server="",
                    mxprio="10",
                    mx="mail.example.com",
                )
            ]
        )
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].resource_name == "mx-host"

    def test_apply_emits_update_outcome(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("foo")]
        live = _live("u1")
        want = _override("foo")
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
        assert outcomes[0].address == "opnsense_unbound_host_override.foo"

    def test_apply_emits_delete_outcome_with_synthetic_name(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = _live("u1", hostname="web", domain="example.com", rr="A")
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
        # Synthetic name: <hostname>-<dot-replaced-domain> (no rr suffix
        # for default A).
        assert outcomes[0].resource_name == "web-example-com"
        assert outcomes[0].address == "opnsense_unbound_host_override.web-example-com"

    def test_apply_emits_delete_outcome_aaaa_includes_rr_suffix(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = _live("u1", hostname="v6", domain="example.com", rr="AAAA")
        diff = Diff(deletes=[live])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 0, "deleted": 1}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert outcomes[0].resource_name == "v6-example-com-aaaa"

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_overrides(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("foo")]
        live = [_live("u1")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_called_once_with("u1")
        # destroy still calls reconfigure inline because the runner's
        # finalization-hook plumbing fires on apply only, not destroy.
        service_mock.reconfigure.assert_called_once()
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0

    def test_destroy_skips_when_no_live_match(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(live=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.reconfigure.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("survival", lock=True)]
        live = [_live("u1")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        assert result["locked_skipped"] == 1

    def test_destroy_matches_by_natural_key(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("foo", hostname="web", domain="example.com", rr="A")]
        live = [
            _live("u1", hostname="web", domain="example.com", rr="A"),
            _live("u2", hostname="other", domain="example.com", rr="A"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        # Only the matching tuple is deleted.
        service_mock.delete.assert_called_once_with("u1")
        assert result["resources_destroyed"] == 1


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids_by_tuple(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [
            _resource("foo", hostname="web"),
            _resource("bar", hostname="other"),
        ]
        live = [
            _live("u1", hostname="web"),
            _live("u2", hostname="other"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1", "bar": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [
            _resource("foo", hostname="web"),
            _resource("missing", hostname="absent"),
        ]
        live = [_live("u1", hostname="web")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}

    def test_distinguishes_a_from_aaaa(self, tmp_path: Path) -> None:
        # Same hostname+domain, different rr type — operator may have one
        # of each; tuple match keeps them distinct.
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [
            _resource("web-a", hostname="web", rr="A", server="192.168.1.10"),
            _resource("web-aaaa", hostname="web", rr="AAAA", server="2001:db8::10"),
        ]
        live = [
            _live("u1", hostname="web", rr="A"),
            _live("u2", hostname="web", rr="AAAA"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"web-a": "u1", "web-aaaa": "u2"}


# ---------------------------------------------------------------------------
# list / migrate
# ---------------------------------------------------------------------------


class TestListAndMigrate:
    def test_list_returns_live_overrides(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        live = [_live("u1"), _live("u2", hostname="other")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        assert result == live

    def test_migrate_returns_yaml_string(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")
        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once()

    def test_migrate_passes_provider_name_through(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.migrate("test-env", provider_name="alt-provider")
        svc_cls.from_environment.assert_called_once_with("test-env", "alt-provider", tmp_path)


# ---------------------------------------------------------------------------
# Finalization hook contract (#776)
# ---------------------------------------------------------------------------


class TestFinalizationHook:
    """The manager declares the shared ``unbound_reconfigure`` hook key and
    apply must NOT call ``service.reconfigure`` inline (the runner fires it
    via ``OPNsenseProvider.get_finalization_hooks()`` instead, coalescing
    across host_override / host_alias / forward managers).
    """

    def test_finalization_hook_classvar_declared(self) -> None:
        assert UnboundHostOverrideManager.FINALIZATION_HOOK == "unbound_reconfigure"

    def test_apply_does_not_call_reconfigure_inline(self, tmp_path: Path) -> None:
        manager = UnboundHostOverrideManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_override("foo")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", resources)
        service_mock.reconfigure.assert_not_called()
