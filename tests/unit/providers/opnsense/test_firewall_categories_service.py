"""Unit tests for the firewall category service (#1286)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services._identity import OpnsenseDriftError
from infrafoundry.providers.opnsense.services.firewall_categories import (
    FirewallCategoryConfig,
    FirewallCategoryService,
    LiveFirewallCategory,
    category_configs_from_resources,
    category_name_of,
    changed_fields,
    compute_diff,
    normalize_color,
)


def _want(name: str = "lab-servers", **kw: Any) -> FirewallCategoryConfig:
    kw.setdefault("category_name", name)
    return FirewallCategoryConfig(name=name, **kw)


def _live(name: str = "lab-servers", uuid: str | None = None, **kw: Any) -> LiveFirewallCategory:
    return LiveFirewallCategory(uuid=uuid or f"u-{name}", name=name, **kw)


def _res(name: str = "lab-servers", /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="firewall.categories", provider="opnsense", config=config)


# --- compute_diff ------------------------------------------------------------------


def test_add_update_noop_delete() -> None:
    diff = compute_diff(
        [_want("new"), _want("same"), _want("chg", auto=True)],
        [_live("same"), _live("chg"), _live("gone")],
        managed_keys={"gone"},
    )
    assert [c.name for c in diff.adds] == ["new"]
    assert [w.name for _, w in diff.updates] == ["chg"]
    assert [d.name for d in diff.deletes] == ["gone"]


def test_color_update() -> None:
    diff = compute_diff([_want(color="#336699")], [_live(color="112233")])
    assert len(diff.updates) == 1


def test_unmanaged_goes_to_unmanaged() -> None:
    diff = compute_diff([], [_live("hand")], managed_keys=set())
    assert [u.name for u in diff.unmanaged] == ["hand"]
    assert diff.deletes == []


def test_add_only_suppresses_deletes() -> None:
    diff = compute_diff([], [_live("gone")], add_only=True)
    assert diff.deletes == []


def test_locked_is_never_touched() -> None:
    diff = compute_diff([_want(auto=True, lock=True)], [_live()])
    assert diff.updates == [] and diff.adds == [] and diff.deletes == []
    assert len(diff.locked) == 1


def test_locked_not_deleted_when_unlisted_elsewhere() -> None:
    diff = compute_diff([_want(lock=True)], [_live()], managed_keys={"lab-servers"})
    assert diff.deletes == []


def test_rename_is_delete_plus_add() -> None:
    diff = compute_diff([_want("new-name")], [_live("old-name")], managed_keys={"old-name"})
    assert [c.name for c in diff.adds] == ["new-name"]
    assert [d.name for d in diff.deletes] == ["old-name"]


@pytest.mark.parametrize("managed", [None, {"infrafoundry"}, set()])
def test_marker_is_in_no_bucket(managed: set[str] | None) -> None:
    marker = _live("infrafoundry")
    diff = compute_diff([], [marker], managed_keys=managed)
    assert not (diff.adds or diff.updates or diff.deletes or diff.unmanaged or diff.blocked)
    assert diff.is_empty


def test_duplicate_marker_rows_do_not_raise() -> None:
    marker = [_live("infrafoundry", uuid="a"), _live("infrafoundry", uuid="b")]
    assert compute_diff([], marker, managed_keys={"infrafoundry"}).is_empty


def test_color_normalisation_no_drift() -> None:
    assert compute_diff([_want(color="#AABBCC")], [_live(color="aabbcc")]).is_empty
    assert compute_diff([_want(color="aabbcc")], [_live(color="#AABBCC")]).is_empty
    assert compute_diff([_want(color="")], [_live(color="")]).is_empty
    assert normalize_color(" #AbC123 ") == "abc123"


def test_auto_flag_compared() -> None:
    assert changed_fields(_live(auto=True), _want(auto=True)) == []
    assert changed_fields(_live(auto=False), _want(auto=True)) == ["auto"]


def test_duplicate_managed_name_raises() -> None:
    live = [_live("dup", uuid="a"), _live("dup", uuid="b")]
    with pytest.raises(OpnsenseDriftError):
        compute_diff([], live, managed_keys={"dup"})
    with pytest.raises(OpnsenseDriftError):
        compute_diff([_want("dup")], live, managed_keys=set())


def test_duplicate_unrelated_name_is_ignored() -> None:
    live = [_live("dup", uuid="a"), _live("dup", uuid="b"), _live("ok")]
    diff = compute_diff([], live, managed_keys={"ok"})
    assert [d.name for d in diff.deletes] == ["ok"]
    assert diff.unmanaged == []


# --- parser --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config",
    [
        {"bogus": 1},
        {"uuid": "x"},
        {"auto": "yes"},
        {"lock": 1},
        {"color": 5},
        {"name": ""},
        {"name": "infrafoundry"},
    ],
)
def test_parser_rejects_naming_the_resource(config: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="firewall category 'cat'"):
        category_configs_from_resources([_res("cat", **config)])


def test_reserved_resource_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="infrafoundry"):
        category_configs_from_resources([_res("infrafoundry")])


def test_config_name_overrides_resource_name() -> None:
    (cfg,) = category_configs_from_resources([_res("handle", name="Lab Servers")])
    assert cfg.name == "handle"
    assert cfg.diff_key == "Lab Servers"
    assert category_name_of("handle", {"name": "Lab Servers"}) == "Lab Servers"
    assert category_name_of("handle", {}) == "handle"


def test_other_types_are_skipped() -> None:
    other = ResourceConfig(name="x", type="firewall.rules", provider="opnsense", config={})
    assert category_configs_from_resources([other]) == []


# --- service -------------------------------------------------------------------------


@pytest.fixture
def client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(client: MagicMock) -> FirewallCategoryService:
    return FirewallCategoryService(client)


def test_search_is_one_call_and_parses_rows(
    service: FirewallCategoryService, client: MagicMock
) -> None:
    client.request.return_value = {
        "rows": [{"uuid": "u1", "name": "a", "auto": "1", "color": "336699"}]
    }
    (row,) = service.search()
    assert (row.uuid, row.name, row.auto, row.color) == ("u1", "a", True, "336699")
    assert [c.args for c in client.request.call_args_list] == [
        ("POST", "firewall/category/searchItem")
    ]


def test_search_tolerates_odd_responses(
    service: FirewallCategoryService, client: MagicMock
) -> None:
    client.request.return_value = []
    assert service.search() == []


def test_add_and_update_payloads(service: FirewallCategoryService, client: MagicMock) -> None:
    client.request.return_value = {"result": "saved"}
    want = _want("lab", auto=True, color="#336699")
    service.add(want)
    service.update("u1", want)
    body = {"category": {"name": "lab", "auto": "1", "color": "336699"}}
    assert client.request.call_args_list[0].args == ("POST", "firewall/category/addItem")
    assert client.request.call_args_list[0].kwargs["data"] == body
    assert client.request.call_args_list[1].args == ("POST", "firewall/category/setItem/u1")
    assert client.request.call_args_list[1].kwargs["data"] == body


def test_auto_false_serialises_zero() -> None:
    assert _want().to_payload()["category"]["auto"] == "0"


def test_failed_write_raises(service: FirewallCategoryService, client: MagicMock) -> None:
    client.request.return_value = {"result": "failed", "validations": {"category.name": "bad"}}
    with pytest.raises(APIError):
        service.add(_want())


def test_delete_success(service: FirewallCategoryService, client: MagicMock) -> None:
    client.request.return_value = {"result": "deleted"}
    assert service.delete(_live()) is True


#: The refusal shape a test firewall returned for an in-use category (HTTP 500).
IN_USE = APIError(
    "OPNsense API request failed: Server error '500 Internal Server Error'",
    status_code=500,
    response=(
        '{"errorMessage":"Filter - a rule {Filter.rules.rule.u-1}\\n",'
        '"errorTitle":"Item categories.category {busy} in use by:"}'
    ),
)


@pytest.mark.parametrize("response", [{"result": "failed"}, {"result": "not found"}, {}])
def test_delete_unexpected_reply_raises(
    service: FirewallCategoryService, client: MagicMock, response: dict[str, Any]
) -> None:
    client.request.return_value = response
    with pytest.raises(APIError):
        service.delete(_live())


def test_delete_refused_in_use(service: FirewallCategoryService, client: MagicMock) -> None:
    client.request.side_effect = IN_USE
    assert service.delete(_live()) is False


def test_delete_in_use_only_in_message_is_not_a_refusal(
    service: FirewallCategoryService, client: MagicMock
) -> None:
    client.request.side_effect = APIError("in use", status_code=500, response="oops")
    with pytest.raises(APIError):
        service.delete(_live())


def test_delete_other_api_error_propagates(
    service: FirewallCategoryService, client: MagicMock
) -> None:
    client.request.side_effect = APIError("server error", status_code=500, response="oops")
    with pytest.raises(APIError):
        service.delete(_live())


def test_apply_diff_blocks_refused_delete(
    service: FirewallCategoryService, client: MagicMock
) -> None:
    client.request.side_effect = IN_USE
    diff = compute_diff([], [_live("busy")], managed_keys={"busy"})
    counts = service.apply_diff(diff)
    assert counts == {"created": 0, "updated": 0, "deleted": 0}
    assert [b.name for b, _ in diff.blocked] == ["busy"]
    assert diff.deletes == []
    assert diff.warnings == ["firewall category 'busy' kept: the box reports it in use"]


def test_apply_diff_counts(service: FirewallCategoryService, client: MagicMock) -> None:
    client.request.return_value = {"result": "deleted"}
    diff = compute_diff(
        [_want("new"), _want("chg", auto=True)],
        [_live("chg"), _live("gone")],
        managed_keys={"gone"},
    )
    assert service.apply_diff(diff) == {"created": 1, "updated": 1, "deleted": 1}


# --- export --------------------------------------------------------------------------


def test_export_skips_marker_and_slugs(service: FirewallCategoryService, client: MagicMock) -> None:
    client.request.return_value = {
        "rows": [
            {"uuid": "u0", "name": "infrafoundry", "auto": "0", "color": ""},
            {"uuid": "u1", "name": "Lab Servers!", "auto": "0", "color": ""},
            {"uuid": "u2", "name": "lab servers", "auto": "1", "color": "336699"},
            {"uuid": "u3", "name": "!!!", "auto": "0", "color": ""},
        ]
    }
    yaml_text = service.export_to_yaml(reserved={"lab-servers"})
    assert "infrafoundry" not in yaml_text
    assert "name: lab-servers-2" in yaml_text
    assert "name: lab-servers-3" in yaml_text
    assert "name: category" in yaml_text
    assert "name: Lab Servers!" in yaml_text
