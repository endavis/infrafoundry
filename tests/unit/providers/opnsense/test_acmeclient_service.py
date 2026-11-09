"""Unit tests for the ACME-client list engine (#790)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.exceptions import (
    APIError,
    InvalidConfigurationError,
    ReferenceValidationError,
)
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services import acmeclient as svc
from infrafoundry.providers.opnsense.services._identity import OpnsenseDriftError

SECRET = "s3cr3t-sentinel-not-real"  # nosec B105  # test fixture


def _res(spec: svc.ListSpec, name: str, **config: Any) -> ResourceConfig:
    config.setdefault("name", name)  # the loader injects it
    return ResourceConfig(name=name, type=spec.type_name, provider="opnsense", config=config)


def _live(uuid: str, name: str, **raw: Any) -> svc.LiveAcmeItem:
    return svc.LiveAcmeItem(uuid=uuid, name=name, raw={"name": name, **raw})


def _configs(spec: svc.ListSpec, *resources: ResourceConfig) -> list[svc.AcmeItemConfig]:
    return svc.configs_from_resources(spec, list(resources))


def _one(spec: svc.ListSpec, name: str, **config: Any) -> svc.AcmeItemConfig:
    return _configs(spec, _res(spec, name, **config))[0]


# -- identity ---------------------------------------------------------------------


def test_account_identity_is_handle_or_display_name() -> None:
    assert _one(svc.ACCOUNTS, "acct").wire_name == "acct"
    assert _one(svc.ACCOUNTS, "acct", display_name="Main Account").wire_name == "Main Account"


def test_cert_identity_is_common_name_and_required() -> None:
    cert = _one(svc.CERTS, "web", common_name="fw-test.example.com")
    assert cert.wire_name == "fw-test.example.com"
    assert cert.name == "web"
    with pytest.raises(ValueError, match="common_name"):
        _one(svc.CERTS, "web")
    with pytest.raises(ValueError, match="unknown keys"):
        _one(svc.CERTS, "web", common_name="a.example.com", display_name="x")


def test_loader_injected_name_is_ignored_in_payload() -> None:
    config = _one(svc.ACCOUNTS, "acct", email="admin@example.com")
    body = config.to_payload("account", {})["account"]
    assert body["name"] == "acct"
    assert body["email"] == "admin@example.com"


def test_unknown_and_server_managed_keys_rejected() -> None:
    with pytest.raises(ValueError, match="unknown keys"):
        _one(svc.ACCOUNTS, "a", id="1")
    with pytest.raises(ValueError, match="unknown keys"):
        _one(svc.ACCOUNTS, "a", key="x")
    with pytest.raises(ValueError, match="unknown keys"):
        _one(svc.ACCOUNTS, "a", bogus=1)


# -- serialization ----------------------------------------------------------------


def test_serialize_bool_enum_int_set() -> None:
    cfg = _one(
        svc.VALIDATIONS,
        "v",
        enabled=True,
        method="dns01",
        dns_sleep=30,
        http_opn_ipaddresses=["b", "a", "b"],
        http_haproxy_inject=False,
    )
    fields = {wire: (value, kind) for wire, value, kind in cfg.fields}
    assert fields["enabled"] == ("1", svc.BOOL)
    assert fields["method"] == ("dns01", svc.ENUM)
    assert fields["dns_sleep"] == ("30", svc.INT)
    assert fields["http_opn_ipaddresses"] == ("a,b", svc.SET)
    assert fields["http_haproxyInject"] == ("0", svc.BOOL)


@pytest.mark.parametrize(
    ("spec", "config"),
    [
        (svc.ACCOUNTS, {"enabled": "yes"}),
        (svc.ACCOUNTS, {"ca": "nope"}),
        (svc.VALIDATIONS, {"dns_sleep": True}),
        (svc.VALIDATIONS, {"dns_sleep": -1}),
        (svc.CERTS, {"common_name": "a.example.com", "renew_interval": 0}),
        (svc.CERTS, {"common_name": "a.example.com", "key_length": "rsa"}),
        (svc.CERTS, {"common_name": "a.example.com", "alt_names": "a.example.com"}),
        (svc.CERTS, {"common_name": "a.example.com", "alt_names": ["a,b"]}),
        (svc.ACTIONS, {"type": "nope"}),
        (svc.ACCOUNTS, {"lock": "yes"}),
    ],
)
def test_serialization_errors_do_not_echo_values(
    spec: svc.ListSpec, config: dict[str, Any]
) -> None:
    with pytest.raises(ValueError) as exc:
        _one(spec, "x", **config)
    assert "yes" not in str(exc.value)


def test_passthrough_accepts_provider_and_action_fields() -> None:
    cfg = _one(
        svc.VALIDATIONS,
        "v",
        method="dns01",
        dns_service="dns_cf",
        dns_cf_token="tok",  # nosec B106
        dns_hostingde_apiKey="k",  # nosec B106
    )
    assert cfg.extra_wires == {"dns_cf_token", "dns_hostingde_apiKey"}
    assert cfg.secret_wires == {"dns_cf_token", "dns_hostingde_apiKey"}
    act = _one(svc.ACTIONS, "a", type="configd_upload_sftp", sftp_host="h", sftp_password="p")
    assert act.extra_wires == {"sftp_host", "sftp_password"}
    assert act.secret_wires == {"sftp_password"}


# -- references -------------------------------------------------------------------


def test_ref_handle_accepts_three_forms_and_rejects_others() -> None:
    assert svc.ref_handle("acct", "accounts") == "acct"
    assert svc.ref_handle("accounts.acct", "accounts") == "acct"
    assert svc.ref_handle("acmeclient.accounts.acct", "accounts") == "acct"
    for bad in ("validations.acct", "other.accounts.acct", "a.b.c.d", "accounts."):
        with pytest.raises(InvalidConfigurationError):
            svc.ref_handle(bad, "accounts")


def test_cert_refs_parsed_to_handles() -> None:
    cfg = _one(
        svc.CERTS,
        "web",
        common_name="a.example.com",
        account="accounts.acct",
        validation="acmeclient.validations.dns",
        restart_actions=["gui", "actions.proxy"],
    )
    assert {w: (s, h) for w, s, h in cfg.refs} == {
        "account": ("accounts", ("acct",)),
        "validationMethod": ("validations", ("dns",)),
        "restartActions": ("actions", ("gui", "proxy")),
    }
    assert cfg.pending_refs({}) == [
        ("accounts", "acct"),
        ("actions", "gui"),
        ("actions", "proxy"),
        ("validations", "dns"),
    ]


def test_cert_payload_sends_comma_joined_uuids() -> None:
    cfg = _one(
        svc.CERTS,
        "web",
        common_name="a.example.com",
        account="acct",
        validation="dns",
        restart_actions=["a1", "a2"],
    )
    uuids = {
        ("accounts", "acct"): "u-acct",
        ("validations", "dns"): "u-dns",
        ("actions", "a1"): "u1",
        ("actions", "a2"): "u2",
    }
    body = cfg.to_payload("certificate", uuids)["certificate"]
    assert body["account"] == "u-acct"
    assert body["validationMethod"] == "u-dns"
    assert body["restartActions"] == "u1,u2"
    assert body["name"] == "a.example.com"


# -- handles ----------------------------------------------------------------------


def test_slug_and_assign_handles_are_deterministic_and_collision_free() -> None:
    assert svc.slug_handle("Main Account!") == "main-account"
    assert svc.slug_handle("a.b.example.com") == "a-b-example-com"
    items = [_live("1", "Foo Bar"), _live("2", "foo-bar"), _live("3", "!!!"), _live("4", "foo-bar")]
    assert svc.assign_handles("accounts", items) == {
        "1": "foo-bar",
        "2": "foo-bar-2",
        "3": "accounts-3",
        "4": "foo-bar-3",
    }


# -- diff -------------------------------------------------------------------------


def test_compute_diff_add_update_delete_and_sparse() -> None:
    desired = _configs(
        svc.ACCOUNTS,
        _res(svc.ACCOUNTS, "new", email="a@example.com"),
        _res(svc.ACCOUNTS, "same", email="b@example.com"),
        _res(svc.ACCOUNTS, "chg", email="c@example.com"),
    )
    live = [
        _live("1", "same", email="b@example.com", ca="letsencrypt", description="untouched"),
        _live("2", "chg", email="old@example.com"),
        _live("3", "gone"),
    ]
    diff = svc.compute_diff(svc.ACCOUNTS, desired, live)
    assert [c.name for c in diff.adds] == ["new"]
    assert [w.name for _, w in diff.updates] == ["chg"]
    assert [d.name for d in diff.deletes] == ["gone"]
    assert not diff.is_empty


def test_add_only_suppresses_deletes() -> None:
    diff = svc.compute_diff(svc.ACCOUNTS, [], [_live("1", "gone")], add_only=True)
    assert diff.deletes == []


def test_managed_keys_send_unmanaged_rows_aside() -> None:
    live = [_live("1", "mine"), _live("2", "hand")]
    diff = svc.compute_diff(svc.ACCOUNTS, [], live, managed_keys={"mine"})
    assert [d.name for d in diff.deletes] == ["mine"]
    assert [u.name for u in diff.unmanaged] == ["hand"]


def test_lock_keeps_row_out_of_updates_and_deletes() -> None:
    desired = _configs(svc.ACCOUNTS, _res(svc.ACCOUNTS, "a", email="x@example.com", lock=True))
    diff = svc.compute_diff(svc.ACCOUNTS, desired, [_live("1", "a", email="other@example.com")])
    assert diff.updates == [] and diff.deletes == []
    assert len(diff.locked) == 1


def test_duplicate_live_names_raise_drift_error() -> None:
    with pytest.raises(OpnsenseDriftError):
        svc.compute_diff(svc.ACCOUNTS, [], [_live("1", "a"), _live("2", "a")])


def test_sets_compare_order_insensitively_and_option_dicts_flatten() -> None:
    desired = _configs(
        svc.CERTS,
        _res(
            svc.CERTS,
            "web",
            common_name="a.example.com",
            alt_names=["b.example.com", "a2.example.com"],
        ),
    )
    live_same = _live("1", "a.example.com", altNames="a2.example.com,b.example.com")
    assert svc.changed_fields(live_same, desired[0]) == []
    live_dict = _live(
        "1",
        "a.example.com",
        altNames={
            "a2.example.com": {"value": "a2.example.com", "selected": 1},
            "b.example.com": {"value": "b.example.com", "selected": 1},
            "c.example.com": {"value": "c.example.com", "selected": 0},
        },
    )
    assert svc.changed_fields(live_dict, desired[0]) == []


def test_bool_normalised_and_server_managed_never_compared() -> None:
    cfg = _one(svc.ACCOUNTS, "a", enabled=False)
    live = _live("1", "a", enabled="0", statusCode="100", id="x", key="k", lastUpdate="1")
    assert svc.changed_fields(live, cfg) == []
    body = cfg.to_payload("account", {})["account"]
    assert set(body) == {"name", "enabled"}


def test_ref_comparison_waits_for_resolution() -> None:
    cfg = _one(svc.CERTS, "web", common_name="a.example.com", account="acct")
    live = _live("1", "a.example.com", account={"u-acct": {"value": "x", "selected": 1}})
    assert svc.changed_fields(live, cfg, {("accounts", "acct"): "u-acct"}) == []
    assert svc.changed_fields(live, cfg, {("accounts", "acct"): "u-other"}) == ["account"]
    assert svc.changed_fields(live, cfg, {}) == ["account"]  # pending counts as changed


def test_changed_fields_never_contains_values() -> None:
    cfg = _one(svc.VALIDATIONS, "v", method="dns01", dns_service="dns_cf", dns_cf_token=SECRET)
    live = _live("1", "v", method="dns01", dns_service="dns_cf", dns_cf_token="other")
    changed = svc.changed_fields(live, cfg)
    assert changed == ["dns_cf_token"]
    assert SECRET not in repr(cfg)
    assert SECRET not in repr(live) and "other" not in repr(live)


def test_stale_provider_fields_names_only() -> None:
    raw = {
        "dns_service": "dns_cf",
        "dns_cf_token": "a",
        "dns_aws_secret": SECRET,
        "dns_gd_key": "",
        "dns_sleep": "10",
    }
    assert svc.stale_provider_fields(raw, "dns_cf") == ["dns_aws_secret"]


# -- service ----------------------------------------------------------------------


class _Box:
    """A tiny fake of one list controller."""

    def __init__(self, spec: svc.ListSpec, rows: dict[str, dict[str, Any]]) -> None:
        self.spec = spec
        self.rows = rows
        self.calls: list[tuple[str, str, Any]] = []
        self.write_result: dict[str, Any] = {"result": "saved"}

    def request(self, method: str, path: str, data: Any = None) -> dict[str, Any]:
        self.calls.append((method, path, data))
        base = f"acmeclient/{self.spec.crud.search.template.split('/')[1]}"
        if path == f"{base}/search":
            return {"rows": [{"uuid": u} for u in self.rows]}
        if path == f"{base}/get":
            return {self.spec.item_key: {"name": "", "enabled": "1", "dns_cf_token": ""}}
        if path.startswith(f"{base}/get/"):
            return {self.spec.item_key: self.rows[path.rsplit("/", 1)[1]]}
        return self.write_result

    def writes(self) -> list[tuple[str, str, Any]]:
        return [c for c in self.calls if c[0] == "POST"]


def _service(
    spec: svc.ListSpec, rows: dict[str, dict[str, Any]]
) -> tuple[svc.AcmeListService, _Box]:
    box = _Box(spec, rows)
    client = MagicMock()
    client.request.side_effect = box.request
    service = type("_TestService", (svc.AcmeListService,), {"SPEC": spec})(client)
    return service, box


def test_search_reads_each_row_by_uuid() -> None:
    service, _ = _service(svc.ACCOUNTS, {"u1": {"name": "a"}, "u2": {"name": "b"}})
    assert [(x.uuid, x.name) for x in service.search()] == [("u1", "a"), ("u2", "b")]


def test_template_keys() -> None:
    service, _ = _service(svc.ACCOUNTS, {})
    assert "dns_cf_token" in service.template_keys()


def test_apply_diff_add_update_delete_use_update_endpoint() -> None:
    service, box = _service(
        svc.ACCOUNTS, {"u1": {"name": "chg", "email": "old@example.com"}, "u2": {"name": "gone"}}
    )
    desired = _configs(
        svc.ACCOUNTS,
        _res(svc.ACCOUNTS, "new", email="n@example.com"),
        _res(svc.ACCOUNTS, "chg", email="c@example.com"),
    )
    diff = svc.compute_diff(svc.ACCOUNTS, desired, service.search())
    counts = service.apply_diff(diff)
    assert counts == {"created": 1, "updated": 1, "deleted": 1}
    paths = [p for _, p, _ in box.writes()]
    assert paths == [
        "acmeclient/accounts/add",
        "acmeclient/accounts/update/u1",
        "acmeclient/accounts/del/u2",
    ]
    assert box.writes()[0][2] == {"account": {"name": "new", "email": "n@example.com"}}
    forbidden = ("register", "sign", "revoke", "removekey", "automation", "import", "toggle")
    assert not any(f in p for p in paths for f in forbidden)


def test_failed_write_surfaces() -> None:
    service, box = _service(svc.ACCOUNTS, {})
    box.write_result = {"result": "failed", "validations": {"account.email": "bad"}}
    with pytest.raises(APIError, match="rejected"):
        service.add(_one(svc.ACCOUNTS, "a", email="x"), {})


def test_unresolved_ref_raises_before_any_write() -> None:
    service, box = _service(svc.ACCOUNTS, {})
    diff = svc.Diff(
        adds=[
            _one(svc.ACCOUNTS, "ok", email="x@example.com"),
            _one(svc.CERTS, "web", common_name="a.example.com", account="missing"),
        ]
    )
    with pytest.raises(ReferenceValidationError, match=r"accounts\.missing"):
        service.apply_diff(diff, {})
    assert box.writes() == []


def test_apply_update_logs_field_names_not_values(caplog: pytest.LogCaptureFixture) -> None:
    service, _ = _service(svc.VALIDATIONS, {"u1": {"name": "v", "dns_cf_token": "old-value"}})
    cfg = _one(svc.VALIDATIONS, "v", method="dns01", dns_service="dns_cf", dns_cf_token=SECRET)
    diff = svc.compute_diff(svc.VALIDATIONS, [cfg], service.search())
    with caplog.at_level(logging.INFO):
        service.apply_diff(diff)
    assert SECRET not in caplog.text and "old-value" not in caplog.text
    assert "dns_cf_token" in caplog.text


# -- export -----------------------------------------------------------------------


def test_export_rows_secret_placeholders_and_display_name() -> None:
    service, _ = _service(svc.VALIDATIONS, {})
    items = [
        _live(
            "1",
            "Example DNS",
            enabled="1",
            method={"dns01": {"value": "dns01", "selected": 1}, "http01": {"selected": 0}},
            dns_service="dns_cf",
            dns_cf_token=SECRET,
            dns_aws_secret="",
            dns_sleep="30",
            statusCode="100",
        )
    ]
    (row,) = service.export_rows(items)
    assert row["name"] == "example-dns"
    config = row["config"]
    assert config["display_name"] == "Example DNS"
    assert config["method"] == "dns01"
    assert config["dns_sleep"] == 30
    assert config["enabled"] is True
    assert config["dns_cf_token"] == (
        "secret://env_secrets/opnsense/acmeclient/validations/example-dns/dns_cf_token"
    )
    assert "dns_aws_secret" not in config
    assert "statusCode" not in config
    assert SECRET not in yaml.safe_dump(row)


def test_export_validation_emits_only_the_selected_provider_fields() -> None:
    # The plugin fills defaults for other providers' fields (a port, a host) on every row.
    service, _ = _service(svc.VALIDATIONS, {})
    items = [
        _live(
            "1",
            "v",
            method="dns01",
            dns_service="dns_cf",
            dns_cf_token=SECRET,
            dns_opnsense_port="443",
            dns_kas_authtype={"plain": {"value": "plain", "selected": 1}},
        )
    ]
    (row,) = service.export_rows(items)
    assert "dns_cf_token" in row["config"]
    assert "dns_opnsense_port" not in row["config"]
    assert "dns_kas_authtype" not in row["config"]


def test_export_validation_with_a_non_dns_method_emits_no_provider_fields() -> None:
    service, _ = _service(svc.VALIDATIONS, {})
    items = [_live("1", "v", method="http01", dns_service="dns_cf", dns_cf_token=SECRET)]
    (row,) = service.export_rows(items)
    assert "dns_cf_token" not in row["config"]


def test_export_action_emits_only_its_type_fields() -> None:
    service, _ = _service(svc.ACTIONS, {})
    items = [
        _live(
            "1",
            "a",
            type="acme_proxmoxve",
            acme_proxmoxve_port="8006",
            acme_proxmoxve_tokenkey=SECRET,
            acme_proxmoxbs_port="8007",
            sftp_port="22",
        )
    ]
    (row,) = service.export_rows(items)
    config = row["config"]
    assert config["acme_proxmoxve_port"] == "8006"
    assert config["acme_proxmoxve_tokenkey"].startswith("secret://")
    assert "acme_proxmoxbs_port" not in config
    assert "sftp_port" not in config

    items = [_live("2", "b", type="configd_restart_gui", sftp_port="22", remote_ssh_port="22")]
    (row,) = service.export_rows(items)
    assert not {"sftp_port", "remote_ssh_port"} & set(row["config"])


def test_export_cert_refs_become_handles_and_unknown_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, _ = _service(svc.CERTS, {})
    items = [
        _live(
            "c1",
            "a.example.com",
            account={"u-acct": {"selected": 1}},
            validationMethod={"u-gone": {"selected": 1}},
            restartActions={"u-a1": {"selected": 1}, "u-a2": {"selected": 1}},
            altNames="x.example.com,y.example.com",
            renewInterval="60",
        )
    ]
    refs = {"accounts": {"u-acct": "acct"}, "actions": {"u-a1": "gui", "u-a2": "proxy"}}
    with caplog.at_level(logging.WARNING):
        (row,) = service.export_rows(items, refs)
    config = row["config"]
    assert row["name"] == "a-example-com"
    assert config["common_name"] == "a.example.com"
    assert config["account"] == "acct"
    assert "validation" not in config
    assert config["restart_actions"] == ["gui", "proxy"]
    assert config["alt_names"] == ["x.example.com", "y.example.com"]
    assert config["renew_interval"] == 60
    assert "unknown validations row" in caplog.text


def test_exported_yaml_round_trips_through_the_parser() -> None:
    service, _ = _service(
        svc.ACCOUNTS,
        {
            "u1": {
                "name": "Main",
                "email": "admin@example.com",
                "ca": "letsencrypt_test",
                "eab_hmac": SECRET,
            }
        },
    )
    text = service.export_to_yaml()
    assert SECRET not in text
    data = yaml.safe_load(text)
    (entry,) = data["opnsense"]["acmeclient"]["accounts"]
    resource = ResourceConfig(
        name=entry["name"], type="acmeclient.accounts", provider="opnsense", config=entry["config"]
    )
    (cfg,) = svc.configs_from_resources(svc.ACCOUNTS, [resource])
    assert cfg.wire_name == "Main"
    assert cfg.secret_wires == {"eab_hmac"}


# -- migrate handles (#1337) --------------------------------------------------------


def test_assign_migrate_handles_avoids_reserved_names() -> None:
    live = {"certs": [_live("c1", "fw-prod.example.com")]}
    handles = svc.assign_migrate_handles(live, reserved={"fw-prod-example-com"})
    assert handles["certs"] == {"c1": "fw-prod-example-com-2"}


def test_assign_migrate_handles_separates_types() -> None:
    live = {"accounts": [_live("a1", "web")], "certs": [_live("c1", "web")]}
    handles = svc.assign_migrate_handles(live)
    assert handles["accounts"] == {"a1": "web"}
    assert handles["certs"] == {"c1": "web-2"}


def test_assign_migrate_handles_pins_existing_handle() -> None:
    live = {"certs": [_live("c1", "fw-prod.example.com")]}
    existing = {"certs": {"fw-prod.example.com": "edge-cert"}}
    handles = svc.assign_migrate_handles(live, existing, reserved={"edge-cert"})
    assert handles["certs"] == {"c1": "edge-cert"}


def test_assign_migrate_handles_fresh_row_never_takes_pinned_handle() -> None:
    live = {"accounts": [_live("a1", "b"), _live("a2", "other")]}
    existing = {"accounts": {"other": "b"}}
    handles = svc.assign_migrate_handles(live, existing)
    assert handles["accounts"] == {"a2": "b", "a1": "b-2"}


def test_assign_migrate_handles_pins_only_first_row_per_wire_name() -> None:
    live = {"accounts": [_live("a1", "dup"), _live("a2", "dup")]}
    existing = {"accounts": {"dup": "mine"}}
    handles = svc.assign_migrate_handles(live, existing)
    assert handles["accounts"] == {"a1": "mine", "a2": "dup"}


def test_assign_migrate_handles_empty_slug_falls_back_to_index() -> None:
    live = {"actions": [_live("x1", "ok"), _live("x2", "!!!")]}
    assert svc.assign_migrate_handles(live)["actions"] == {"x1": "ok", "x2": "actions-2"}


def test_assign_migrate_handles_is_deterministic() -> None:
    live = {"accounts": [_live("a1", "web")], "certs": [_live("c1", "web"), _live("c2", "web")]}
    assert svc.assign_migrate_handles(live) == svc.assign_migrate_handles(live)


def test_export_uses_explicit_items_and_handles_without_searching() -> None:
    client = MagicMock()
    service = svc.AcmeAccountsService(client)
    items = [_live("a1", "Main Account", email="a@example.com")]
    text = service.export_to_yaml(items=items, handles={"a1": "custom"})
    (row,) = yaml.safe_load(text)["opnsense"]["acmeclient"]["accounts"]
    assert row["name"] == "custom"
    client.request.assert_not_called()
    assert service.export_rows(items, handles={"a1": "other"})[0]["name"] == "other"
