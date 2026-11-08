"""Unit tests for the trust service (#807): diff engine, parsers, payloads, CA lookup."""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError, ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services._identity import OpnsenseDriftError
from infrafoundry.providers.opnsense.services.trust import (
    ACME_ISSUED_CA_DESCR,
    LiveTrustObject,
    TrustCaConfig,
    TrustCertConfig,
    TrustService,
    ca_refids_by_name,
    compute_diff,
    is_acme_issued_descr,
    normalize_pem,
    trust_ca_configs_from_resources,
    trust_cert_configs_from_resources,
)

CRT = "-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----"
CRT2 = "-----BEGIN CERTIFICATE-----\nFAKE2\n-----END CERTIFICATE-----"
KEY = "-----BEGIN PRIVATE" + " KEY-----\nFAKEKEY\n-----END PRIVATE" + " KEY-----"
KEY2 = "-----BEGIN PRIVATE" + " KEY-----\nOTHER\n-----END PRIVATE" + " KEY-----"


def _res(name: str, rtype: str, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type=rtype, provider="opnsense", config=config)


def _live(descr: str, *, crt: str = CRT, prv: str = "", **kw: Any) -> LiveTrustObject:
    return LiveTrustObject(
        uuid=f"u-{descr}", refid=kw.pop("refid", f"r-{descr}"), description=descr, crt=crt,
        prv=prv, **kw,
    )  # fmt: skip


def _ca(name: str = "vpn-ca", **kw: Any) -> TrustCaConfig:
    return TrustCaConfig(
        name=name, description=kw.pop("description", name), crt=kw.pop("crt", CRT), **kw
    )


def _cert(name: str = "web-cert", **kw: Any) -> TrustCertConfig:
    return TrustCertConfig(
        name=name, description=kw.pop("description", name), crt=kw.pop("crt", CRT), **kw
    )


class TestDiff:
    def test_no_change(self) -> None:
        diff = compute_diff([_ca()], [_live("vpn-ca")], kind="ca")
        assert diff.is_empty

    def test_normalized_pem_compare(self) -> None:
        live = _live("vpn-ca", crt=CRT.replace("\n", "\r\n") + "\n")
        assert compute_diff([_ca()], [live], kind="ca").is_empty

    def test_add(self) -> None:
        diff = compute_diff([_ca()], [], kind="ca")
        assert [c.name for c in diff.adds] == ["vpn-ca"]

    def test_update_on_crt(self) -> None:
        diff = compute_diff([_ca(crt=CRT2)], [_live("vpn-ca")], kind="ca")
        assert len(diff.updates) == 1

    def test_prv_compared_only_when_both_non_empty(self) -> None:
        assert compute_diff([_ca(prv=KEY)], [_live("vpn-ca", prv="")], kind="ca").is_empty
        assert compute_diff([_ca(prv="")], [_live("vpn-ca", prv=KEY)], kind="ca").is_empty
        assert compute_diff([_ca(prv=KEY2)], [_live("vpn-ca", prv=KEY)], kind="ca").updates
        assert compute_diff([_ca(prv=KEY)], [_live("vpn-ca", prv=KEY)], kind="ca").is_empty

    def test_cert_type_does_not_trigger_update(self) -> None:
        diff = compute_diff([_cert(type="server")], [_live("web-cert")], kind="cert")
        assert diff.is_empty

    def test_caref_drift_updates(self) -> None:
        refids = {"vpn-ca": "r-ca"}
        diff = compute_diff(
            [_cert(ca_ref="vpn-ca")],
            [_live("web-cert", caref="r-old")],
            kind="cert",
            ca_refids=refids,
        )
        assert len(diff.updates) == 1
        same = compute_diff(
            [_cert(ca_ref="vpn-ca")],
            [_live("web-cert", caref="r-ca")],
            kind="cert",
            ca_refids=refids,
        )
        assert same.is_empty

    def test_pending_ca_not_compared(self) -> None:
        diff = compute_diff([_cert(ca_ref="vpn-ca")], [_live("web-cert")], kind="cert")
        assert diff.is_empty

    def test_delete_only_managed_keys(self) -> None:
        live = [_live("old"), _live("other")]
        diff = compute_diff([], live, kind="ca", managed_keys={"old"})
        assert [d.description for d in diff.deletes] == ["old"]
        assert [d.description for d in diff.unmanaged] == ["other"]

    def test_add_only_suppresses_deletes(self) -> None:
        diff = compute_diff([], [_live("old")], kind="ca", add_only=True)
        assert diff.is_empty
        assert not diff.deletes

    def test_lock(self) -> None:
        diff = compute_diff([_ca(crt=CRT2, lock=True)], [_live("vpn-ca")], kind="ca")
        assert diff.is_empty
        assert len(diff.locked) == 1
        kept = compute_diff([_ca(lock=True)], [_live("vpn-ca")], kind="ca")
        assert not kept.deletes

    def test_in_use_blocked(self) -> None:
        diff = compute_diff([], [_live("old", in_use=True)], kind="cert")
        assert not diff.deletes
        assert len(diff.blocked) == 1
        assert diff.warnings
        assert diff.is_empty

    def test_acme_ca_blocked_but_not_cert(self) -> None:
        ca = compute_diff([], [_live("R10")], kind="ca")
        assert len(ca.blocked) == 1
        cert = compute_diff([], [_live("R10")], kind="cert")
        assert len(cert.deletes) == 1

    def test_duplicate_live_descr(self) -> None:
        with pytest.raises(OpnsenseDriftError):
            compute_diff([], [_live("dup"), _live("dup")], kind="ca")


def test_acme_descr_pattern() -> None:
    assert ACME_ISSUED_CA_DESCR
    assert is_acme_issued_descr("R10")
    assert is_acme_issued_descr("E5")
    assert not is_acme_issued_descr("vpn.example.com CA")
    assert not is_acme_issued_descr("R")


def test_normalize_pem() -> None:
    assert normalize_pem(" a \r\n\n b \n") == "a\nb"


class TestParsers:
    def test_ca_accepts_unresolved_secret(self) -> None:
        res = [
            _res(
                "vpn-ca",
                "trust.cas",
                crt="secret://env_secrets/ca/crt",
                prv="secret://env_secrets/ca/prv",
            )
        ]
        cfg = trust_ca_configs_from_resources(res)
        assert cfg[0].description == "vpn-ca"
        assert cfg[0].prv.startswith("secret://")

    def test_description_overrides_name(self) -> None:
        res = [_res("vpn-ca", "trust.cas", crt=CRT, description="vpn.example.com CA")]
        assert trust_ca_configs_from_resources(res)[0].diff_key == "vpn.example.com CA"

    def test_missing_crt(self) -> None:
        with pytest.raises(ValueError, match="vpn-ca"):
            trust_ca_configs_from_resources([_res("vpn-ca", "trust.cas")])

    def test_non_pem_after_resolution_names_resource_only(self) -> None:
        secret_value = "super-secret-value"
        res = [_res("vpn-ca", "trust.cas", crt=CRT, prv=secret_value)]
        with pytest.raises(ValueError) as exc:
            trust_ca_configs_from_resources(res, require_pem=True)
        assert "vpn-ca" in str(exc.value)
        assert secret_value not in str(exc.value)

    def test_cert_type_validated(self) -> None:
        with pytest.raises(ValueError, match="type"):
            trust_cert_configs_from_resources([_res("c", "trust.certs", crt=CRT, type="bogus")])

    def test_cert_fields(self) -> None:
        res = [
            _res(
                "web-cert",
                "trust.certs",
                crt=CRT,
                prv=KEY,
                csr=CRT,
                ca_ref="vpn-ca",
                type="server",
                lock=True,
            )
        ]
        cfg = trust_cert_configs_from_resources(res, require_pem=True)[0]
        assert (cfg.ca_ref, cfg.type, cfg.lock) == ("vpn-ca", "server", True)

    def test_skips_other_types(self) -> None:
        assert trust_ca_configs_from_resources([_res("x", "trust.certs", crt=CRT)]) == []

    def test_repr_hides_key_material(self) -> None:
        assert "FAKEKEY" not in repr(_ca(prv=KEY))
        assert "FAKEKEY" not in repr(_cert(prv=KEY))


def test_ca_refids_by_name() -> None:
    cas = [
        _res("vpn-ca", "trust.cas", crt=CRT, description="vpn.example.com CA"),
        _res("gone", "trust.cas", crt=CRT),
    ]
    live = [_live("vpn.example.com CA", refid="abc123"), _live("noref", refid="")]
    assert ca_refids_by_name(cas, live) == {"vpn-ca": "abc123"}


class TestService:
    def _service(self, response: Any = None) -> tuple[TrustService, MagicMock]:
        client = MagicMock()
        client.request.return_value = response if response is not None else {"result": "saved"}
        return TrustService(client), client

    def test_search_rows_and_paths(self) -> None:
        crt_b64 = base64.b64encode(CRT.encode()).decode()
        rows = {
            "rows": [
                {
                    "uuid": "u1",
                    "refid": "r1",
                    "descr": "web-cert",
                    "caref": "c1",
                    "in_use": "1",
                    "crt": crt_b64,
                }
            ]
        }
        service, client = self._service(rows)
        live = service.search_certs()
        assert live[0].crt == CRT
        assert live[0].in_use is True
        assert client.request.call_args.args[1] == "trust/cert/search"
        service.search_cas()
        assert client.request.call_args.args[1] == "trust/ca/search"

    def test_add_ca_payload(self) -> None:
        service, client = self._service()
        service.add("ca", _ca(prv=KEY))
        args, kwargs = client.request.call_args
        assert args == ("POST", "trust/ca/add")
        body = kwargs["data"]["ca"]
        assert body["descr"] == "vpn-ca"
        assert body["crt_payload"] == CRT
        assert body["prv_payload"] == KEY

    def test_add_cert_payload_with_caref(self) -> None:
        service, client = self._service()
        service.add("cert", _cert(prv=KEY, type="server"), "ref1")
        args, kwargs = client.request.call_args
        assert args == ("POST", "trust/cert/add")
        body = kwargs["data"]["cert"]
        assert body["caref"] == "ref1"
        assert body["cert_type"] == "server_cert"
        assert "csr_payload" not in body

    def test_update_and_delete_paths(self) -> None:
        service, client = self._service()
        service.update("cert", "u1", _cert())
        assert client.request.call_args.args == ("POST", "trust/cert/set/u1")
        service.delete("ca", "u2", "vpn-ca")
        assert client.request.call_args.args == ("POST", "trust/ca/del/u2")

    def test_failed_write_raises_without_key_material(self) -> None:
        service, _ = self._service({"result": "failed", "validations": {"ca.crt_payload": "bad"}})
        with pytest.raises(APIError) as exc:
            service.add("ca", _ca(prv=KEY))
        assert "FAKEKEY" not in str(exc.value)
        assert "vpn-ca" in str(exc.value)

    def test_apply_diff_unresolved_ca_ref_raises_before_writes(self) -> None:
        service, client = self._service()
        diff = compute_diff([_cert(ca_ref="vpn-ca")], [], kind="cert")
        with pytest.raises(ReferenceValidationError):
            service.apply_diff(diff, kind="cert", ca_refids={})
        client.request.assert_not_called()

    def test_apply_diff_counts(self) -> None:
        service, _ = self._service()
        diff = compute_diff(
            [_cert("new", ca_ref="vpn-ca"), _cert("chg", crt=CRT2)],
            [_live("chg"), _live("gone")],
            kind="cert",
            managed_keys={"gone"},
            ca_refids={"vpn-ca": "r"},
        )
        counts = service.apply_diff(diff, kind="cert", ca_refids={"vpn-ca": "r"})
        assert counts == {"created": 1, "updated": 1, "deleted": 1}
