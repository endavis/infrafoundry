"""Unit tests for ``FirewallCategoryManager`` (#1286)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.firewall_categories import (
    FirewallCategoryManager,
)
from infrafoundry.providers.opnsense.services.firewall_categories import (
    FirewallCategoryService,
)


def _cat(name: str = "lab-servers", /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="firewall.categories", provider="opnsense", config=config)


def _row(name: str, uuid: str | None = None, **kw: Any) -> dict[str, Any]:
    return {"uuid": uuid or f"u-{name}", "name": name, "auto": "0", "color": "", **kw}


@pytest.fixture
def client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def manager(client: MagicMock, tmp_path: Any) -> Iterator[FirewallCategoryManager]:
    with patch.object(
        FirewallCategoryService, "from_environment", return_value=FirewallCategoryService(client)
    ):
        yield FirewallCategoryManager(tmp_path)


#: The refusal shape a test firewall returned for an in-use category (HTTP 500).
IN_USE = APIError(
    "OPNsense API request failed: Server error '500 Internal Server Error'",
    status_code=500,
    response='{"errorTitle":"Item categories.category {busy} in use by:"}',
)


def _set_live(client: MagicMock, rows: list[dict[str, Any]], *, delete: Any = None) -> None:
    def fake(method: str, path: str, data: Any = None) -> Any:
        if path.endswith("searchItem"):
            return {"rows": rows}
        if "delItem" in path:
            if isinstance(delete, Exception):
                raise delete
            return delete if delete is not None else {"result": "deleted"}
        return {"result": "saved"}

    client.request.side_effect = fake


def _paths(client: MagicMock) -> list[str]:
    return [c.args[1] for c in client.request.call_args_list]


def test_class_markers() -> None:
    assert FirewallCategoryManager.DELETE_SCOPE == "managed_set"
    assert not getattr(FirewallCategoryManager, "SPLIT_DELETE_PHASE", False)
    assert not getattr(FirewallCategoryManager, "FINALIZATION_HOOK", None)


def test_apply_adds_updates_and_reports_outcomes(
    manager: FirewallCategoryManager, client: MagicMock
) -> None:
    _set_live(client, [_row("chg")])
    result = manager.apply("env", [_cat("new"), _cat("chg", auto=True)])
    assert (result["resources_created"], result["resources_updated"]) == (1, 1)
    assert [(o.address, o.action) for o in result["resource_outcomes"]] == [
        ("opnsense_firewall_category.new", "add"),
        ("opnsense_firewall_category.chg", "update"),
    ]
    assert result["unresolved_managed"] == []


def test_plan_passes_managed_resources_through(
    manager: FirewallCategoryManager, client: MagicMock
) -> None:
    _set_live(client, [_row("mine"), _row("hand"), _row("infrafoundry")])
    diff = manager.plan("env", [], managed_resources=[_cat("mine")])
    assert [d.name for d in diff.deletes] == ["mine"]
    assert [u.name for u in diff.unmanaged] == ["hand"]


def test_refused_delete_is_kept_and_unresolved(
    manager: FirewallCategoryManager, client: MagicMock
) -> None:
    _set_live(client, [_row("Busy Cat")], delete=IN_USE)
    managed = [_cat("busy", name="Busy Cat")]
    result = manager.apply("env", [], managed_resources=managed)
    assert result["resources_deleted"] == 0
    assert result["resource_outcomes"] == []
    assert result["unresolved_managed"] == ["busy"]
    assert any("kept" in w for w in result["warnings"])


def test_managed_delete_and_marker_untouched(
    manager: FirewallCategoryManager, client: MagicMock
) -> None:
    _set_live(client, [_row("old"), _row("infrafoundry", "marker")])
    result = manager.apply("env", [], managed_resources=[_cat("old"), _cat("infrafoundry")])
    assert result["resources_deleted"] == 1
    assert "firewall/category/delItem/u-old" in _paths(client)
    assert not [p for p in _paths(client) if p.endswith("/marker")]


def test_destroy_counts_locked_and_keeps_refused(
    manager: FirewallCategoryManager, client: MagicMock
) -> None:
    _set_live(client, [_row("a"), _row("keep"), _row("infrafoundry")])
    result = manager.destroy("env", [_cat("a"), _cat("keep", lock=True)])
    assert result["resources_destroyed"] == 1
    assert result["locked_skipped"] == 1
    deleted = [p for p in _paths(client) if "delItem" in p]
    assert deleted == ["firewall/category/delItem/u-a"]


def test_destroy_keeps_in_use_with_warning(
    manager: FirewallCategoryManager, client: MagicMock
) -> None:
    _set_live(client, [_row("busy")], delete=IN_USE)
    result = manager.destroy("env", [_cat("busy")])
    assert result["resources_destroyed"] == 0
    assert result["warnings"]


def test_get_resource_ids_skips_marker(manager: FirewallCategoryManager, client: MagicMock) -> None:
    _set_live(client, [_row("a", "u1"), _row("infrafoundry", "m")])
    ids = manager.get_resource_ids("env", [_cat("a"), _cat("infrafoundry"), _cat("absent")])
    assert ids == {"a": "u1"}


def test_list_returns_live(manager: FirewallCategoryManager, client: MagicMock) -> None:
    _set_live(client, [_row("a")])
    assert [x.name for x in manager.list("env")] == ["a"]


def test_migrate_reserves_names_of_other_types(
    manager: FirewallCategoryManager, client: MagicMock
) -> None:
    _set_live(client, [_row("Lab Servers"), _row("infrafoundry")])
    alias = ResourceConfig(
        name="lab-servers", type="firewall.aliases", provider="opnsense", config={}
    )
    with patch(
        "infrafoundry.providers.opnsense.components.firewall_categories.env_provider_resources",
        return_value=[alias],
    ):
        yaml_text = manager.migrate("env")
    assert "name: lab-servers-2" in yaml_text
    assert "name: Lab Servers" in yaml_text
    assert "infrafoundry" not in yaml_text
