"""Which host name a provider's device serves a production certificate for."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from infrafoundry.core.certs.models import LETSENCRYPT_PRODUCTION, LETSENCRYPT_STAGING
from infrafoundry.core.certs.target_lookup import installed_server_name
from infrafoundry.core.provider import ResourceConfig

pytestmark = pytest.mark.unit

NOW = dt.datetime(2026, 6, 1, tzinfo=dt.UTC)
NAMES = ["router.example.com"]


def cert(
    *,
    provider: str = "mikrotik",
    names: list[str] | None = None,
    verify: dict[str, Any] | None = None,
    **entry: Any,
) -> ResourceConfig:
    sha = "ab" * 32
    stored = {
        "sha256": sha,
        "installed_sha256": sha,
        "directory": LETSENCRYPT_PRODUCTION,
        "not_after": (NOW + dt.timedelta(days=30)).isoformat(),
    }
    stored.update(entry)
    target: dict[str, Any] = {"provider": provider, "resource": "edge-services"}
    if verify is not None:
        target["verify"] = verify
    return ResourceConfig(
        name="router-cert",
        type="certificate",
        provider="acme",
        config={"names": names or NAMES, "target": target},
        package_secrets={"acme_certificates": {"router-cert": stored}},
    )


def lookup(*resources: ResourceConfig) -> str | None:
    return installed_server_name(resources, "mikrotik", NOW)


def test_an_installed_production_certificate_names_the_server() -> None:
    assert lookup(cert()) == "router.example.com"


def test_an_explicit_server_name_wins() -> None:
    assert lookup(cert(verify={"server_name": "gw.example.com"})) == "gw.example.com"


@pytest.mark.parametrize(
    "entry",
    [
        {"directory": LETSENCRYPT_STAGING},
        {"directory": "https://ca.example.test/directory"},
        {"installed_sha256": ""},
        {"installed_sha256": "cd" * 32},
        {"not_after": (NOW - dt.timedelta(days=1)).isoformat()},
        {"not_after": "garbage"},
    ],
)
def test_a_certificate_that_is_not_in_service_gives_nothing(entry: dict[str, Any]) -> None:
    assert lookup(cert(**entry)) is None


def test_a_certificate_without_a_stored_entry_gives_nothing() -> None:
    resource = cert()
    resource.package_secrets = {}
    assert lookup(resource) is None


def test_other_providers_and_resources_are_ignored() -> None:
    assert lookup(cert(provider="host")) is None
    other = ResourceConfig(name="x", type="ip.service", provider="mikrotik", config={})
    assert lookup(other) is None


def test_an_invalid_target_is_skipped() -> None:
    assert lookup(cert(names=["*.example.com"])) is None


def test_the_kind_filter_ignores_a_target_of_another_kind() -> None:
    resource = cert(provider="ontap")
    resource.config["target"] = {"provider": "ontap", "kind": "svm", "svm": "svm1"}
    resources = [resource]
    assert installed_server_name(resources, "ontap", NOW, kind="cluster") is None
    assert installed_server_name(resources, "ontap", NOW, kind="svm") == "router.example.com"
    assert installed_server_name(resources, "ontap", NOW) == "router.example.com"


def test_an_installed_cluster_target_needs_no_resource() -> None:
    resource = cert(provider="ontap")
    resource.config["target"] = {"provider": "ontap", "kind": "cluster"}
    assert installed_server_name([resource], "ontap", NOW, kind="cluster") == "router.example.com"
