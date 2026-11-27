"""Tests for the certificate switch-over lock-out guards."""

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.mikrotik.components.certificate_bootstrap import (
    check_certificate_changes,
)
from infrafoundry.providers.mikrotik.components.diff import TypeDiff, compute_type_diff
from infrafoundry.providers.mikrotik.schema import SPECS, desired_from_resources

from .conftest import bootstrap_https, resource

_SIGNED = "AA:" * 31 + "AA"
_CERT = {".id": "*9", "name": "old", "common-name": "x", "fingerprint": _SIGNED}
_WWW_SSL = {".id": "*41", "name": "www-ssl", "port": "443", "disabled": "true"}


def _check(
    resources: list[ResourceConfig],
    live: dict[str, list[dict[str, str]]],
    *,
    scheme: str = "http",
    verify_ssl: bool = True,
    managed: set[Any] | None = None,
) -> list[str]:
    diffs: dict[str, TypeDiff] = {}
    for type_name in ("certificate", "ip.service"):
        desired = desired_from_resources([r for r in resources if r.type == type_name])
        keys = managed if type_name == "certificate" else None
        if not desired and keys is None:
            continue
        diffs[type_name] = compute_type_diff(
            SPECS[type_name],
            desired,
            live.get(SPECS[type_name].path, []),
            add_only=False,
            managed_keys=keys,
        )
    full = {t: live.get(spec.path, []) for t, spec in SPECS.items()}
    return check_certificate_changes(diffs, full, scheme=scheme, verify_ssl=verify_ssl).refusals


def _live() -> dict[str, list[dict[str, str]]]:
    return {"certificate": [], "ip/service": [dict(_WWW_SSL)]}


def test_refuses_a_service_naming_a_certificate_that_will_not_exist() -> None:
    res = [resource("ip.service", "www-ssl", certificate="missing", disabled=False)]
    (message,) = _check(res, _live())
    assert "www-ssl" in message and "missing" in message


def test_accepts_a_certificate_created_in_the_same_plan() -> None:
    assert _check(bootstrap_https()[:2], _live()) == []


def test_accepts_a_live_signed_certificate() -> None:
    live = {"certificate": [dict(_CERT)], "ip/service": [dict(_WWW_SSL)]}
    res = [resource("ip.service", "www-ssl", certificate="old", disabled=False)]
    assert _check(res, live) == []


def test_refuses_a_live_unsigned_certificate_not_in_the_plan() -> None:
    unsigned = {k: v for k, v in _CERT.items() if k != "fingerprint"}
    live = {"certificate": [unsigned], "ip/service": [dict(_WWW_SSL)]}
    res = [resource("ip.service", "www-ssl", certificate="old", disabled=False)]
    assert len(_check(res, live)) == 1


def test_refuses_deleting_a_certificate_a_live_service_uses() -> None:
    service = {**_WWW_SSL, "certificate": "old"}
    live = {"certificate": [dict(_CERT)], "ip/service": [service]}
    (message,) = _check([], live, managed={("old",)})
    assert "old" in message and "www-ssl" in message


def test_refuses_new_self_signed_certificate_on_verified_https() -> None:
    refusals = _check(bootstrap_https()[:2], _live(), scheme="https", verify_ssl=True)
    assert len(refusals) == 1 and "verify_ssl" in refusals[0]


def test_accepts_the_same_with_verification_off_or_http() -> None:
    assert _check(bootstrap_https()[:2], _live(), scheme="https", verify_ssl=False) == []
    assert _check(bootstrap_https()[:2], _live(), scheme="http", verify_ssl=True) == []
