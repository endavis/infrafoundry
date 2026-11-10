"""Unit tests for the Tailscale subnet service (#787)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services._identity import OpnsenseDriftError
from infrafoundry.providers.opnsense.services.tailscale_subnets import (
    LiveTailscaleSubnet,
    TailscaleSubnetConfig,
    TailscaleSubnetService,
    compute_diff,
    normalize_cidr,
    subnet_configs_from_resources,
)


def _want(subnet: str, description: str = "", *, lock: bool = False) -> TailscaleSubnetConfig:
    return TailscaleSubnetConfig(
        name=f"n-{subnet}", subnet=normalize_cidr(subnet), description=description, lock=lock
    )


def _live(uuid: str, subnet: str, description: str = "") -> LiveTailscaleSubnet:
    return LiveTailscaleSubnet(uuid=uuid, subnet=subnet, description=description)


def _service(*responses: Any) -> TailscaleSubnetService:
    client = MagicMock()
    client.request.side_effect = list(responses)
    return TailscaleSubnetService(client)


def test_normalize_cidr() -> None:
    assert normalize_cidr("2001:DB8:0::/64") == "2001:db8::/64"
    assert normalize_cidr(" 192.0.2.0/24 ") == "192.0.2.0/24"
    assert normalize_cidr("not-a-cidr") == "not-a-cidr"
    assert normalize_cidr("192.0.2.1/24") == "192.0.2.1/24"  # host bits: kept raw


def test_payload_envelope() -> None:
    assert _want("192.0.2.0/24", "lab").to_payload() == {
        "subnet4": {"subnet": "192.0.2.0/24", "description": "lab"}
    }


def test_diff_add_update_noop() -> None:
    diff = compute_diff(
        [_want("192.0.2.0/24", "new"), _want("198.51.100.0/24", "same"), _want("2001:db8::/64")],
        [_live("u1", "192.0.2.0/24", "old"), _live("u2", "198.51.100.0/24", "same")],
    )
    assert [a.subnet for a in diff.adds] == ["2001:db8::/64"]
    assert [(h.uuid, w.description) for h, w in diff.updates] == [("u1", "new")]
    assert diff.deletes == []


def test_diff_ipv6_case_is_same_identity() -> None:
    diff = compute_diff([_want("2001:DB8::/64")], [_live("u1", "2001:db8::/64")])
    assert diff.is_empty


def test_diff_deletes_managed_only() -> None:
    live = [_live("u1", "192.0.2.0/24"), _live("u2", "198.51.100.0/24")]
    diff = compute_diff([], live, managed_keys={"192.0.2.0/24"})
    assert [d.uuid for d in diff.deletes] == ["u1"]
    assert [d.uuid for d in diff.unmanaged] == ["u2"]


def test_diff_add_only_and_lock() -> None:
    live = [_live("u1", "192.0.2.0/24", "x")]
    assert compute_diff([], live, add_only=True).deletes == []
    diff = compute_diff([_want("192.0.2.0/24", "y", lock=True)], live)
    assert diff.is_empty
    assert len(diff.locked) == 1
    assert compute_diff([_want("192.0.2.0/24", lock=True)], [], managed_keys=set()).adds == []


def test_duplicate_live_cidr_raises() -> None:
    live = [_live("u1", "192.0.2.0/24"), _live("u2", "192.0.2.0/24")]
    with pytest.raises(OpnsenseDriftError):
        compute_diff([_want("192.0.2.0/24")], live)
    # An unrelated duplicate under a managed set is ignored.
    diff = compute_diff([], live, managed_keys={"198.51.100.0/24"})
    assert diff.deletes == []


def _res(name: str, /, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type="tailscale.subnets", provider="opnsense", config=config)


def test_parser_validates() -> None:
    (cfg,) = subnet_configs_from_resources(
        [_res("a", name="a", subnet="2001:DB8::/64", description="d")]
    )
    assert cfg.subnet == "2001:db8::/64"
    for bad in (
        {"subnet": "192.0.2.1/24"},
        {"subnet": "x"},
        {},
        {"subnet": "192.0.2.0/24", "uuid": "u"},
        {"subnet": "192.0.2.0/24", "description": 3},
        {"subnet": "192.0.2.0/24", "lock": "yes"},
    ):
        with pytest.raises(ValueError, match="tailscale subnet 'a'"):
            subnet_configs_from_resources([_res("a", **bad)])


def test_search_reads_grid_rows() -> None:
    svc = _service({"rows": [{"uuid": "u1", "subnet": "192.0.2.0/24", "description": "d"}, "junk"]})
    (row,) = svc.search()
    assert (row.uuid, row.subnet, row.description) == ("u1", "192.0.2.0/24", "d")
    assert _service({"unexpected": 1}).search() == []


def test_calls_use_the_subnet_endpoints() -> None:
    svc = _service({"rows": []}, {"result": "saved"}, {"result": "saved"}, {"result": "deleted"})
    svc.search()
    svc.add(_want("192.0.2.0/24"))
    svc.update("u1", _want("192.0.2.0/24"))
    svc.delete(_live("u1", "192.0.2.0/24"))
    calls = [(c.args[0], c.args[1]) for c in svc.client.request.call_args_list]  # type: ignore[attr-defined]
    assert calls == [
        ("POST", "tailscale/settings/searchSubnet"),
        ("POST", "tailscale/settings/addSubnet"),
        ("POST", "tailscale/settings/setSubnet/u1"),
        ("POST", "tailscale/settings/delSubnet/u1"),
    ]


def test_delete_unexpected_reply_raises() -> None:
    with pytest.raises(APIError):
        _service({"result": "nope"}).delete(_live("u1", "192.0.2.0/24"))


def test_add_failed_write_raises() -> None:
    with pytest.raises(APIError):
        _service({"result": "failed", "validations": {}}).add(_want("192.0.2.0/24"))


def test_apply_diff_counts() -> None:
    svc = _service({"result": "saved"}, {"result": "saved"}, {"result": "deleted"})
    diff = compute_diff(
        [_want("192.0.2.0/24", "new"), _want("2001:db8::/64")],
        [_live("u1", "192.0.2.0/24", "old"), _live("u3", "203.0.113.0/24")],
    )
    assert svc.apply_diff(diff) == {"created": 1, "updated": 1, "deleted": 1}


def test_export_handles_and_round_trip(tmp_path: Path) -> None:
    svc = _service(
        {
            "rows": [
                {"uuid": "1", "subnet": "192.0.2.0/24", "description": "Lab Net"},
                {"uuid": "2", "subnet": "198.51.100.0/24", "description": "Lab Net"},
                {"uuid": "3", "subnet": "2001:DB8::/64", "description": ""},
                {"uuid": "4", "subnet": "203.0.113.0/24", "description": "taken"},
            ]
        }
    )
    text = svc.export_to_yaml(reserved={"taken"})
    leaf = yaml.safe_load(text)["opnsense"]["tailscale"]["subnets"]
    assert [e["name"] for e in leaf] == ["lab-net", "lab-net-2", "2001-db8-64", "taken-2"]
    assert leaf[2]["config"] == {"subnet": "2001:db8::/64"}
    parsed = PackageLoader(tmp_path)._parse_nested_provider_format(
        yaml.safe_load(text)["opnsense"], "opnsense", "s.yaml"
    )
    assert len(parsed) == 4
