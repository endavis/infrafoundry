"""Per-provider remote state locations (#1464)."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from infrafoundry.core.backend_keys import (
    assign_backend_peers,
    backend_provider_ids,
    migration_warning,
    resolve_backend_location,
)
from infrafoundry.core.config.backend_config import BackendConfig, BackendType
from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.providers.host import HostProvider

A = "opnsense"
B = "opnsense@fw-b"
BOTH = frozenset({A, B})


def _backend(kind: str, **overrides: Any) -> BackendConfig:
    configs: dict[str, dict[str, Any]] = {
        "s3": {"bucket": "example-tfstate", "key": "infra/dev/terraform.tfstate", "region": "r"},
        "azurerm": {
            "resource_group_name": "rg",
            "storage_account_name": "sa",
            "container_name": "c",
            "key": "dev/terraform.tfstate",
        },
        "gcs": {"bucket": "example-tfstate", "prefix": "infra/dev/"},
        "postgres": {"conn_str": "postgres://example.com/db", "schema_name": "tf"},
        "remote": {"organization": "example-org", "workspaces": {"name": "dev"}},
    }
    pin = overrides.pop("bare_key_provider", None)
    configs[kind].update(overrides)
    return BackendConfig(type=kind, bare_key_provider=pin, **{kind: configs[kind]})  # type: ignore[arg-type]


def _new(backend: BackendConfig, pid: str, peers: frozenset[str]) -> str | None:
    return resolve_backend_location(backend, pid, peers).new


@pytest.mark.parametrize("kind", ["s3", "azurerm", "gcs", "postgres", "remote"])
def test_single_provider_is_unchanged(kind: str) -> None:
    backend = _backend(kind)
    location = resolve_backend_location(backend, A, frozenset({A}))
    assert location.config == backend.get_backend_config()
    assert not location.auto_moved


@pytest.mark.parametrize("kind", ["s3", "azurerm", "gcs", "postgres", "remote"])
def test_multi_provider_locations_are_distinct_and_not_bare(kind: str) -> None:
    backend = _backend(kind)
    a, b = _new(backend, A, BOTH), _new(backend, B, BOTH)
    bare = resolve_backend_location(backend, A, frozenset({A})).new
    assert a != b
    assert bare not in {a, b}


def test_s3_inserts_segment_before_last() -> None:
    assert _new(_backend("s3"), B, BOTH) == "infra/dev/opnsense@fw-b/terraform.tfstate"


def test_s3_key_without_slash() -> None:
    assert _new(_backend("s3", key="terraform.tfstate"), B, BOTH) == (
        "opnsense@fw-b/terraform.tfstate"
    )


def test_gcs_trailing_slash_stripped() -> None:
    assert _new(_backend("gcs"), B, BOTH) == "infra/dev/opnsense@fw-b"


def test_remote_and_postgres_sanitize_at_sign() -> None:
    assert _new(_backend("remote"), B, BOTH) == "dev-opnsense-fw-b"
    assert _new(_backend("postgres"), B, BOTH) == "tf_opnsense_fw_b"


def test_remote_prefix() -> None:
    backend = BackendConfig(
        type=BackendType.TERRAFORM_CLOUD,
        remote={"organization": "o", "workspaces": {"prefix": "infra-"}},  # type: ignore[arg-type]
    )
    assert _new(backend, B, BOTH) == "infra-opnsense-fw-b-"


def test_pin_keeps_bare_key_and_only_others_move() -> None:
    backend = _backend("s3", bare_key_provider=A)
    assert _new(backend, A, BOTH) == "infra/dev/terraform.tfstate"
    assert resolve_backend_location(backend, B, BOTH).auto_moved
    assert not resolve_backend_location(backend, A, BOTH).auto_moved


def test_placeholder_overrides_pin_without_move() -> None:
    backend = _backend("s3", key="infra/{provider}/t.tfstate", bare_key_provider=A)
    location = resolve_backend_location(backend, A, BOTH)
    assert location.new == "infra/opnsense/t.tfstate"
    assert not location.auto_moved


def test_placeholder_works_for_single_provider() -> None:
    backend = _backend("s3", key="{provider}.tfstate")
    assert _new(backend, A, frozenset({A})) == "opnsense.tfstate"


def test_placeholder_remote_uses_slug() -> None:
    backend = _backend("remote", workspaces={"name": "dev-{provider}"})
    assert _new(backend, B, BOTH) == "dev-opnsense-fw-b"


def test_local_backend_renders_nothing_and_pin_is_not_validated() -> None:
    provider = Mock(renders_terraform_backend=True)
    backend = BackendConfig(bare_key_provider="nope")
    assert assign_backend_peers({A: provider}, [A], backend) == []


def test_invalid_pin_is_rejected() -> None:
    providers = {A: Mock(renders_terraform_backend=True)}
    with pytest.raises(InvalidConfigurationError, match="bare_key_provider"):
        assign_backend_peers(providers, [A], _backend("s3", bare_key_provider="nope"))


def test_host_provider_and_plain_mocks_are_not_peers(tmp_path: Any) -> None:
    providers = {
        A: Mock(renders_terraform_backend=True),
        "host": HostProvider(tmp_path, tmp_path),
        "other": Mock(),
    }
    assert backend_provider_ids(providers, ["host", A, "other", "missing"]) == {A}


def test_assignment_is_order_independent_and_sorted() -> None:
    def run(order: list[str]) -> list[str]:
        providers = {pid: Mock(renders_terraform_backend=True) for pid in order}
        moved = assign_backend_peers(providers, order, _backend("s3"))
        assert all(p.backend_peer_ids == BOTH for p in providers.values())
        return [m.provider_id for m in moved]

    assert run([A, B]) == run([B, A]) == sorted([A, B])


def test_warning_names_provider_keys_and_migration() -> None:
    location = resolve_backend_location(_backend("s3"), B, BOTH)
    text = migration_warning(location)
    for part in (B, location.old or "", location.new or "", "terraform init -migrate-state"):
        assert part in text
