"""Unit tests for the ACME-client list managers (#790)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from infrafoundry.core.exceptions import (
    APIError,
    InvalidConfigurationError,
    ReferenceValidationError,
)
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components import acmeclient as comp
from infrafoundry.providers.opnsense.components.acmeclient_settings import PLUGIN_MISSING_WARNING
from infrafoundry.providers.opnsense.services import acmeclient as svc

SECRET = "s3cr3t-sentinel-not-real"  # nosec B105  # test fixture
SUBS = ("accounts", "validations", "actions", "certificates")


def _res(type_name: str, name: str, **config: Any) -> ResourceConfig:
    config.setdefault("name", name)
    return ResourceConfig(name=name, type=type_name, provider="opnsense", config=config)


class FakeBox:
    """A fake ACME plugin: four controllers keyed by uuid."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, dict[str, Any]]] = {s: {} for s in SUBS}
        self.templates: dict[str, dict[str, Any]] = {
            s: {"name": "", "enabled": "1", "dns_cf_token": "", "dns_aws_secret": ""} for s in SUBS
        }
        self.calls: list[tuple[str, str, Any]] = []
        self.missing_plugin = False

    def request(self, method: str, path: str, data: Any = None) -> dict[str, Any]:
        self.calls.append((method, path, data))
        if self.missing_plugin:
            raise APIError("not found", status_code=404)
        parts = path.split("/")
        sub, action = parts[1], parts[2]
        if parts[0] != "acmeclient" or sub not in self.rows:
            return {"result": "saved"}
        item_key = {"certificates": "certificate"}.get(sub, sub.rstrip("s"))
        if action == "search":
            return {"rows": [{"uuid": u} for u in self.rows[sub]]}
        if action == "get" and len(parts) == 3:
            return {item_key: self.templates[sub]}
        if action == "get":
            return {item_key: self.rows[sub][parts[3]]}
        return {"result": "saved"}

    def writes(self) -> list[str]:
        return [p for m, p, _ in self.calls if m == "POST" and not p.endswith("/search")]

    def body(self, path: str) -> dict[str, Any]:
        return next(d for _, p, d in self.calls if p == path)


@pytest.fixture(autouse=True)
def _no_secret_lookup() -> Iterator[None]:
    with patch(
        "infrafoundry.providers.opnsense.components.acmeclient.resolve_resource_secrets",
        side_effect=lambda _d, _e, resources, _t: resources,
    ):
        yield


@pytest.fixture
def box() -> FakeBox:
    return FakeBox()


def _manager(cls: type[comp._AcmeListManager], box: FakeBox, tmp_path: Path) -> Any:
    client = MagicMock()
    client.request.side_effect = box.request
    service_cls = cls.SERVICE
    patcher = patch.object(service_cls, "from_environment", return_value=service_cls(client))
    patcher.start()
    return cls(tmp_path)


@pytest.fixture
def make(box: FakeBox, tmp_path: Path) -> Iterator[Callable[[type[comp._AcmeListManager]], Any]]:
    yield lambda cls: _manager(cls, box, tmp_path)
    patch.stopall()


A = "acmeclient.accounts"
V = "acmeclient.validations"
X = "acmeclient.actions"
C = "acmeclient.certs"


# -- shared behaviour ----------------------------------------------------------------


def test_class_attributes() -> None:
    for cls in (
        comp.AcmeClientAccountsManager,
        comp.AcmeClientValidationsManager,
        comp.AcmeClientActionsManager,
        comp.AcmeClientCertsManager,
    ):
        assert cls.DELETE_SCOPE == "managed_set"
        assert cls.FINALIZATION_HOOK == "acmeclient_reconfigure"
    assert comp.AcmeClientCertsManager.SPLIT_DELETE_PHASE is True
    assert not getattr(comp.AcmeClientAccountsManager, "SPLIT_DELETE_PHASE", False)
    assert comp.AcmeClientCertsManager.SIBLING_RESOURCE_TYPE == (A, V, X)


def test_plan_add_update_delete_and_apply_counts(make: Any, box: FakeBox) -> None:
    box.rows["accounts"] = {
        "u1": {"name": "chg", "email": "old@example.com"},
        "u2": {"name": "gone"},
    }
    manager = make(comp.AcmeClientAccountsManager)
    resources = [
        _res(A, "new", email="n@example.com"),
        _res(A, "chg", email="c@example.com"),
    ]
    diff = manager.plan("env", resources)
    assert [c.name for c in diff.adds] == ["new"]
    assert [w.name for _, w in diff.updates] == ["chg"]
    assert [d.name for d in diff.deletes] == ["gone"]
    result = manager.apply("env", resources)
    assert (result["resources_created"], result["resources_updated"]) == (1, 1)
    assert result["resources_deleted"] == 1
    assert [o.address for o in result["resource_outcomes"]] == [
        "opnsense_acmeclient_account.new",
        "opnsense_acmeclient_account.chg",
        "opnsense_acmeclient_account.gone",
    ]
    assert box.writes() == [
        "acmeclient/accounts/add",
        "acmeclient/accounts/update/u1",
        "acmeclient/accounts/del/u2",
    ]
    assert not any("reconfigure" in p for p in box.writes())  # the hook does that


def test_managed_set_keeps_unmanaged_rows(make: Any, box: FakeBox) -> None:
    box.rows["accounts"] = {"u1": {"name": "mine"}, "u2": {"name": "hand"}}
    manager = make(comp.AcmeClientAccountsManager)
    managed = [_res(A, "mine", email="x@example.com")]
    diff = manager.plan("env", [], managed_resources=managed)
    assert [d.name for d in diff.deletes] == ["mine"]
    assert [u.name for u in diff.unmanaged] == ["hand"]


@pytest.mark.parametrize(
    ("cls", "sub"),
    [
        (comp.AcmeClientAccountsManager, "accounts"),
        (comp.AcmeClientValidationsManager, "validations"),
        (comp.AcmeClientActionsManager, "actions"),
        (comp.AcmeClientCertsManager, "certificates"),
    ],
)
def test_add_only_produces_no_deletes(make: Any, box: FakeBox, cls: Any, sub: str) -> None:
    box.rows[sub] = {"u1": {"name": "stale"}}
    manager = make(cls)
    result = manager.apply("env", [], add_only=True)
    assert result["resources_deleted"] == 0
    assert not any("/del/" in p for p in box.writes())


def test_display_name_and_description_in_payload(make: Any, box: FakeBox) -> None:
    manager = make(comp.AcmeClientActionsManager)
    manager.apply(
        "env",
        [_res(X, "gui", type="configd_restart_gui", display_name="Restart GUI", description="d")],
    )
    assert box.body("acmeclient/actions/add") == {
        "action": {"name": "Restart GUI", "type": "configd_restart_gui", "description": "d"}
    }


def test_lock_skips_update_and_delete(make: Any, box: FakeBox) -> None:
    box.rows["accounts"] = {"u1": {"name": "a", "email": "old@example.com"}}
    manager = make(comp.AcmeClientAccountsManager)
    diff = manager.plan("env", [_res(A, "a", email="new@example.com", lock=True)])
    assert diff.is_empty and len(diff.locked) == 1


def test_account_switch_warning_names_no_values(make: Any, box: FakeBox) -> None:
    box.rows["accounts"] = {"u1": {"name": "a", "email": "old@example.com", "ca": "zerossl"}}
    manager = make(comp.AcmeClientAccountsManager)
    diff = manager.plan("env", [_res(A, "a", email="new@example.com", ca="letsencrypt_test")])
    (warning,) = diff.warnings
    assert "registration" in warning
    assert "example.com" not in warning


def test_account_key_is_never_sent(make: Any, box: FakeBox) -> None:
    box.rows["accounts"] = {"u1": {"name": "a", "email": "old@example.com", "key": "PRIVATE"}}
    manager = make(comp.AcmeClientAccountsManager)
    manager.apply("env", [_res(A, "a", email="new@example.com")])
    body = box.body("acmeclient/accounts/update/u1")["account"]
    assert set(body) == {"name", "email"}


def test_validation_stale_provider_warning_names_fields_only(make: Any, box: FakeBox) -> None:
    box.rows["validations"] = {
        "u1": {
            "name": "v",
            "method": "dns01",
            "dns_service": "dns_cf",
            "dns_cf_token": "tok",
            "dns_aws_secret": SECRET,
        }
    }
    manager = make(comp.AcmeClientValidationsManager)
    diff = manager.plan(
        "env",
        [_res(V, "v", method="dns01", dns_service="dns_cf", dns_cf_token="tok")],  # nosec B106
    )
    (warning,) = diff.warnings
    assert "dns_aws_secret" in warning
    assert SECRET not in warning


def test_validation_fields_at_their_template_default_are_not_stale(make: Any, box: FakeBox) -> None:
    # The plugin defaults some provider fields (a port, a host); every new row has them.
    box.templates["validations"]["dns_opnsense_port"] = "443"
    box.rows["validations"] = {
        "u1": {
            "name": "v",
            "method": "dns01",
            "dns_service": "dns_cf",
            "dns_cf_token": "tok",
            "dns_opnsense_port": "443",
        }
    }
    manager = make(comp.AcmeClientValidationsManager)
    diff = manager.plan(
        "env",
        [_res(V, "v", method="dns01", dns_service="dns_cf", dns_cf_token="tok")],  # nosec B106
    )
    assert diff.warnings == []

    box.rows["validations"]["u1"]["dns_opnsense_port"] = "8443"
    diff = manager.plan(
        "env",
        [_res(V, "v", method="dns01", dns_service="dns_cf", dns_cf_token="tok")],  # nosec B106
    )
    (warning,) = diff.warnings
    assert "dns_opnsense_port" in warning
    assert "8443" not in warning


def test_passthrough_key_missing_from_template_is_rejected(make: Any, box: FakeBox) -> None:
    manager = make(comp.AcmeClientValidationsManager)
    with pytest.raises(InvalidConfigurationError, match="dns_nope_token"):
        manager.plan(
            "env",
            [_res(V, "v", method="dns01", dns_service="dns_nope", dns_nope_token="x")],  # nosec B106
        )
    # known keys pass
    manager.plan("env", [_res(V, "v", method="dns01", dns_service="dns_cf", dns_cf_token="x")])  # nosec B106


def test_template_is_not_fetched_without_passthrough(make: Any, box: FakeBox) -> None:
    manager = make(comp.AcmeClientAccountsManager)
    manager.plan("env", [_res(A, "a", email="x@example.com")])
    assert "acmeclient/accounts/get" not in [p for _, p, _ in box.calls]


# -- secrets ---------------------------------------------------------------------------


def test_secret_resolved_before_diff_and_never_leaks(
    make: Any, box: FakeBox, caplog: pytest.LogCaptureFixture
) -> None:
    box.rows["validations"] = {
        "u1": {"name": "v", "method": "dns01", "dns_service": "dns_cf", "dns_cf_token": "old"}
    }
    uri = "secret://env_secrets/opnsense/acmeclient/validations/v/dns_cf_token"

    def resolve(_d: Any, _e: Any, resources: list[ResourceConfig], _t: str) -> list[ResourceConfig]:
        return [
            ResourceConfig(
                name=r.name,
                type=r.type,
                provider=r.provider,
                config={k: (SECRET if v == uri else v) for k, v in r.config.items()},
            )
            for r in resources
        ]

    manager = make(comp.AcmeClientValidationsManager)
    resources = [_res(V, "v", method="dns01", dns_service="dns_cf", dns_cf_token=uri)]
    with (
        patch(
            "infrafoundry.providers.opnsense.components.acmeclient.resolve_resource_secrets",
            side_effect=resolve,
        ),
        caplog.at_level(logging.DEBUG),
    ):
        diff = manager.plan("env", resources)
        result = manager.apply("env", resources)
    assert [w.name for _, w in diff.updates] == ["v"]
    assert box.body("acmeclient/validations/update/u1")["validation"]["dns_cf_token"] == SECRET
    assert SECRET not in caplog.text
    assert SECRET not in str(result["warnings"]) + str(diff.warnings)
    assert SECRET not in repr(diff.updates)


# -- plugin missing ---------------------------------------------------------------------


def test_plan_without_plugin_adds_everything_with_warning(make: Any, box: FakeBox) -> None:
    box.missing_plugin = True
    manager = make(comp.AcmeClientAccountsManager)
    diff = manager.plan("env", [_res(A, "a", email="x@example.com")])
    assert [c.name for c in diff.adds] == ["a"]
    assert diff.warnings == [PLUGIN_MISSING_WARNING]
    with pytest.raises(APIError):
        manager.apply("env", [_res(A, "a", email="x@example.com")])


# -- destroy / ids / migrate ------------------------------------------------------------


def test_destroy_deletes_unlocked_matches_and_reconfigures(make: Any, box: FakeBox) -> None:
    box.rows["accounts"] = {"u1": {"name": "a"}, "u2": {"name": "keep"}, "u3": {"name": "locked"}}
    manager = make(comp.AcmeClientAccountsManager)
    result = manager.destroy(
        "env", [_res(A, "a", email="x@example.com"), _res(A, "locked", email="y", lock=True)]
    )
    assert result["resources_destroyed"] == 1
    assert result["locked_skipped"] == 1
    assert box.writes() == ["acmeclient/accounts/del/u1", "acmeclient/service/reconfigure"]


def test_get_resource_ids_by_identity(make: Any, box: FakeBox) -> None:
    box.rows["certificates"] = {"c1": {"name": "a.example.com"}}
    manager = make(comp.AcmeClientCertsManager)
    ids = manager.get_resource_ids(
        "env", [_res(C, "web", common_name="a.example.com"), _res(C, "other", common_name="b")]
    )
    assert ids == {"web": "c1"}


def test_migrate_accounts_emits_yaml_without_secret_values(make: Any, box: FakeBox) -> None:
    box.rows["accounts"] = {"u1": {"name": "Main", "email": "a@example.com", "eab_hmac": SECRET}}
    text = make(comp.AcmeClientAccountsManager).migrate("env")
    assert SECRET not in text
    (entry,) = yaml.safe_load(text)["opnsense"]["acmeclient"]["accounts"]
    assert entry["name"] == "main"
    assert entry["config"]["display_name"] == "Main"


# -- certs ------------------------------------------------------------------------------


def _siblings() -> list[ResourceConfig]:
    return [
        _res(A, "acct", email="x@example.com", display_name="Main Account"),
        _res(V, "dns", method="dns01"),
        _res(X, "gui", type="configd_restart_gui"),
        _res(X, "proxy", type="configd_restart_haproxy"),
    ]


def _box_with_siblings(box: FakeBox) -> None:
    box.rows["accounts"] = {"ua": {"name": "Main Account"}}
    box.rows["validations"] = {"uv": {"name": "dns"}}
    box.rows["actions"] = {"ug": {"name": "gui"}, "up": {"name": "proxy"}}


def _cert(**overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "common_name": "fw-test.example.com",
        "account": "acct",
        "validation": "validations.dns",
        "restart_actions": ["gui", "acmeclient.actions.proxy"],
    }
    config.update(overrides)
    return _res(C, "web", **config)


def test_cert_refs_resolve_through_sibling_yaml_display_name(make: Any, box: FakeBox) -> None:
    _box_with_siblings(box)
    manager = make(comp.AcmeClientCertsManager)
    diff = manager.plan("env", [_cert()], sibling_resources=_siblings())
    assert [c.name for c in diff.adds] == ["web"]
    assert diff.warnings == []
    manager.apply("env", [_cert()], sibling_resources=_siblings())
    body = box.body("acmeclient/certificates/add")["certificate"]
    assert body["account"] == "ua"
    assert body["validationMethod"] == "uv"
    assert body["restartActions"] == "ug,up"
    assert body["name"] == "fw-test.example.com"


def test_cert_update_only_when_refs_differ(make: Any, box: FakeBox) -> None:
    _box_with_siblings(box)
    box.rows["certificates"] = {
        "c1": {
            "name": "fw-test.example.com",
            "account": {"ua": {"selected": 1}},
            "validationMethod": {"uv": {"selected": 1}},
            "restartActions": {"ug": {"selected": 1}, "up": {"selected": 1}},
        }
    }
    manager = make(comp.AcmeClientCertsManager)
    assert manager.plan("env", [_cert()], sibling_resources=_siblings()).is_empty
    box.rows["certificates"]["c1"]["account"] = {"other": {"selected": 1}}
    diff = manager.plan("env", [_cert()], sibling_resources=_siblings())
    assert [w.name for _, w in diff.updates] == ["web"]


def test_pending_ref_at_plan_is_add_plus_warning(make: Any, box: FakeBox) -> None:
    manager = make(comp.AcmeClientCertsManager)
    diff = manager.plan("env", [_cert()], sibling_resources=_siblings())
    assert [c.name for c in diff.adds] == ["web"]
    assert any("accounts 'acct' is not on the box yet" in w for w in diff.warnings)


def test_unresolved_ref_at_apply_raises_before_any_write(make: Any, box: FakeBox) -> None:
    manager = make(comp.AcmeClientCertsManager)
    with pytest.raises(ReferenceValidationError):
        manager.apply("env", [_cert()], sibling_resources=_siblings())
    assert box.writes() == []


def test_ref_to_undeclared_sibling_is_unresolved(make: Any, box: FakeBox) -> None:
    _box_with_siblings(box)
    manager = make(comp.AcmeClientCertsManager)
    with pytest.raises(ReferenceValidationError):
        manager.apply("env", [_cert()], sibling_resources=[])


def test_managed_siblings_are_honoured(make: Any, box: FakeBox) -> None:
    _box_with_siblings(box)
    manager = make(comp.AcmeClientCertsManager)
    diff = manager.plan("env", [_cert()], managed_sibling_resources=_siblings())
    assert diff.warnings == []


def test_deletes_only_does_only_deletes_and_drops_pending_warnings(make: Any, box: FakeBox) -> None:
    box.rows["certificates"] = {"c1": {"name": "stale.example.com"}}
    manager = make(comp.AcmeClientCertsManager)
    result = manager.apply("env", [_cert()], deletes_only=True, sibling_resources=_siblings())
    assert result["resources_created"] == 0 and result["resources_deleted"] == 1
    assert result["warnings"] == []
    assert box.writes() == ["acmeclient/certificates/del/c1"]


def test_cert_migrate_handles_match_sibling_migrations(make: Any, box: FakeBox) -> None:
    box.rows["accounts"] = {"ua": {"name": "Main Account", "email": "a@example.com"}}
    box.rows["validations"] = {"uv": {"name": "DNS One"}}
    box.rows["actions"] = {"ug": {"name": "Restart GUI"}}
    box.rows["certificates"] = {
        "c1": {
            "name": "fw-test.example.com",
            "account": {"ua": {"selected": 1}},
            "validationMethod": {"uv": {"selected": 1}},
            "restartActions": {"ug": {"selected": 1}},
        }
    }
    cert_yaml = yaml.safe_load(make(comp.AcmeClientCertsManager).migrate("env"))
    (cert,) = cert_yaml["opnsense"]["acmeclient"]["certs"]
    acct_yaml = yaml.safe_load(make(comp.AcmeClientAccountsManager).migrate("env"))
    val_yaml = yaml.safe_load(make(comp.AcmeClientValidationsManager).migrate("env"))
    act_yaml = yaml.safe_load(make(comp.AcmeClientActionsManager).migrate("env"))
    assert cert["config"]["account"] == acct_yaml["opnsense"]["acmeclient"]["accounts"][0]["name"]
    assert (
        cert["config"]["validation"] == val_yaml["opnsense"]["acmeclient"]["validations"][0]["name"]
    )
    assert cert["config"]["restart_actions"] == [
        act_yaml["opnsense"]["acmeclient"]["actions"][0]["name"]
    ]


def test_sibling_row_that_does_not_parse_is_skipped(make: Any, box: FakeBox) -> None:
    _box_with_siblings(box)
    manager = make(comp.AcmeClientCertsManager)
    siblings = [*_siblings(), _res(A, "broken", bogus=1)]
    assert manager.plan("env", [_cert()], sibling_resources=siblings).warnings == []


def test_runner_tuple_siblings_helper_is_used() -> None:
    from infrafoundry.core.runners.opnsense_direct_runner import OPNsenseDirectRunner

    rows = OPNsenseDirectRunner._sibling_resources_for(
        comp.AcmeClientCertsManager, [*_siblings(), _cert()]
    )
    assert rows is not None
    assert {r.type for r in rows} == {A, V, X}
    assert svc.REF_SUBS == ("accounts", "validations", "actions")


# -- migrate handles vs the environment (#1337) ---------------------------------------


def _write_env(tmp_path: Path, leaf: str, type_name: str, rows: list[dict[str, Any]]) -> None:
    from infrafoundry.providers.opnsense.services._nested_emit import emit_nested_list_yaml

    target = tmp_path / "env" / "resources"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{leaf}.yaml").write_text(emit_nested_list_yaml(type_name, rows), encoding="utf-8")


def _load_env(tmp_path: Path) -> list[ResourceConfig]:
    import warnings

    from infrafoundry.core.config import ConfigManager

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return ConfigManager(tmp_path).get_all_resources_all_providers("env")


def _cert_names(text: str) -> list[str]:
    return [r["name"] for r in yaml.safe_load(text)["opnsense"]["acmeclient"]["certs"]]


def test_cert_migrate_avoids_name_of_other_resource(
    make: Any, box: FakeBox, tmp_path: Path
) -> None:
    _write_env(
        tmp_path,
        "dns",
        "unbound.host_overrides",
        [
            {
                "name": "fw-prod-example-com",
                "config": {"hostname": "fw-prod", "domain": "example.com"},
            }
        ],
    )
    box.rows["certificates"] = {"c1": {"name": "fw-prod.example.com"}}
    text = make(comp.AcmeClientCertsManager).migrate("env")
    assert _cert_names(text) == ["fw-prod-example-com-2"]
    (tmp_path / "env" / "resources" / "certs.yaml").write_text(text, encoding="utf-8")
    assert len(_load_env(tmp_path)) == 2


def test_migrate_is_idempotent_over_its_own_output(make: Any, box: FakeBox, tmp_path: Path) -> None:
    box.rows["accounts"] = {"ua": {"name": "web", "email": "a@example.com"}}
    box.rows["certificates"] = {
        "c1": {"name": "web", "account": {"ua": {"selected": 1}}},
        "c2": {"name": "fw-test.example.com"},
    }
    first_certs = make(comp.AcmeClientCertsManager).migrate("env")
    first_accts = make(comp.AcmeClientAccountsManager).migrate("env")
    resources = tmp_path / "env" / "resources"
    resources.mkdir(parents=True)
    (resources / "certs.yaml").write_text(first_certs, encoding="utf-8")
    (resources / "accounts.yaml").write_text(first_accts, encoding="utf-8")
    assert make(comp.AcmeClientCertsManager).migrate("env") == first_certs
    assert make(comp.AcmeClientAccountsManager).migrate("env") == first_accts


def test_migrate_refs_follow_hand_renamed_env_handles(
    make: Any, box: FakeBox, tmp_path: Path
) -> None:
    _write_env(
        tmp_path,
        "accounts",
        A,
        [{"name": "my-acct", "config": {"display_name": "Main Account", "email": "a@example.com"}}],
    )
    box.rows["accounts"] = {"ua": {"name": "Main Account", "email": "a@example.com"}}
    box.rows["certificates"] = {
        "c1": {"name": "fw-test.example.com", "account": {"ua": {"selected": 1}}}
    }
    (cert,) = yaml.safe_load(make(comp.AcmeClientCertsManager).migrate("env"))["opnsense"][
        "acmeclient"
    ]["certs"]
    assert cert["config"]["account"] == "my-acct"
    acct_yaml = yaml.safe_load(make(comp.AcmeClientAccountsManager).migrate("env"))
    assert acct_yaml["opnsense"]["acmeclient"]["accounts"][0]["name"] == "my-acct"


def test_migrate_cross_type_names_are_consistent(make: Any, box: FakeBox) -> None:
    box.rows["accounts"] = {"ua": {"name": "web", "email": "a@example.com"}}
    box.rows["certificates"] = {"c1": {"name": "web", "account": {"ua": {"selected": 1}}}}
    acct = yaml.safe_load(make(comp.AcmeClientAccountsManager).migrate("env"))
    cert = yaml.safe_load(make(comp.AcmeClientCertsManager).migrate("env"))
    (acct_row,) = acct["opnsense"]["acmeclient"]["accounts"]
    (cert_row,) = cert["opnsense"]["acmeclient"]["certs"]
    assert acct_row["name"] == "web"
    assert cert_row["name"] == "web-2"
    assert cert_row["config"]["account"] == acct_row["name"]
