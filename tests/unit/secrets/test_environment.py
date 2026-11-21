"""Tests for the per-environment resolver helper, ``SecretRefLookup`` and the config models."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from infrafoundry.collectors.config import resolve_device
from infrafoundry.core.config.models import (
    BitwardenBackendConfig,
    CollectorDeviceConfig,
    EnvironmentConfig,
    SecretBackendsConfig,
)
from infrafoundry.providers.mikrotik.settings import PROVIDER_NAME as MIKROTIK
from infrafoundry.secrets.backends.bitwarden import close_bitwarden_sessions
from infrafoundry.secrets.environment import (
    SecretRefLookup,
    build_secret_resolver,
    configured_backends,
)
from infrafoundry.secrets.resolver import (
    SecretResolutionError,
    is_secret_uri,
    parse_secret_uri,
)
from tests.unit.secrets.bw_stub import FIXTURE_VALUE, SERVER, StubBw, install_stub


@pytest.fixture(autouse=True)
def _close_sessions() -> Iterator[None]:
    close_bitwarden_sessions()
    yield
    close_bitwarden_sessions()


@pytest.fixture
def stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StubBw:
    return install_stub(tmp_path, monkeypatch)


def env_with_vault(**extra: Any) -> EnvironmentConfig:
    return EnvironmentConfig(
        name="test",
        secrets={"db": {"password": "from-sops"}},
        secret_backends=SecretBackendsConfig(bitwarden=BitwardenBackendConfig(server=SERVER)),
        **extra,
    )


class TestModels:
    def test_defaults(self) -> None:
        cfg = BitwardenBackendConfig(server=SERVER)
        assert cfg.client_id == "secret://env/bw_clientid"
        assert cfg.client_secret == "secret://env/bw_clientsecret"
        assert cfg.master_password == "secret://env/bw_password"
        assert cfg.organization is None
        assert cfg.collection is None

    def test_http_rejected(self) -> None:
        with pytest.raises(ValidationError, match="https"):
            BitwardenBackendConfig(server="http://vault.example.com")

    def test_server_required(self) -> None:
        with pytest.raises(ValidationError):
            BitwardenBackendConfig.model_validate({})

    @pytest.mark.parametrize(
        "uri", ["plain", "secret://bitwarden/x/password", "secret://file/x", "secret://env/"]
    )
    def test_credential_uri_checked(self, uri: str) -> None:
        with pytest.raises(ValidationError, match="secret://env"):
            BitwardenBackendConfig(server=SERVER, master_password=uri)

    def test_env_secrets_uri_accepted(self) -> None:
        cfg = BitwardenBackendConfig(server=SERVER, client_id="secret://env_secrets/bw/id")
        assert cfg.client_id == "secret://env_secrets/bw/id"

    def test_unknown_keys_ignored_and_environment_field(self) -> None:
        env = EnvironmentConfig.model_validate(
            {
                "name": "t",
                "secret_backends": {"bitwarden": {"server": SERVER, "extra": 1}, "other": {}},
            }
        )
        assert env.secret_backends is not None
        assert env.secret_backends.bitwarden is not None
        assert EnvironmentConfig(name="t").secret_backends is None


class TestResolverHelpers:
    def test_is_secret_uri_and_parse(self) -> None:
        assert is_secret_uri("secret://bitwarden") is True
        assert is_secret_uri("a.b") is False
        assert parse_secret_uri("secret://bitwarden/A B/password") == ("bitwarden", "A B/password")
        with pytest.raises(SecretResolutionError):
            parse_secret_uri("secret://bitwarden")


class TestBuildSecretResolver:
    def test_without_block_only_env_secrets(self) -> None:
        env = EnvironmentConfig(name="t", secrets={"a": {"b": "v"}})
        assert configured_backends(env) == {"env_secrets"}
        with build_secret_resolver(env) as resolver:
            assert resolver.resolve("secret://env_secrets/a/b") == "v"
            assert sorted(resolver._backend_configs) == ["env_secrets"]

    def test_with_block_is_lazy(self, stub: StubBw, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("BW_CLIENTID", "BW_CLIENTSECRET", "BW_PASSWORD"):
            monkeypatch.delenv(name)
        env = env_with_vault()
        assert configured_backends(env) == {"env_secrets", "bitwarden"}
        with build_secret_resolver(env) as resolver:
            assert resolver.resolve("secret://env_secrets/db/password") == "from-sops"
        assert stub.calls() == []

    def test_vault_value_through_resolver(self, stub: StubBw) -> None:
        with build_secret_resolver(env_with_vault()) as resolver:
            assert resolver.resolve("secret://bitwarden/Router Admin/password") == FIXTURE_VALUE


class TestCallSites:
    def test_mikrotik_settings(self, stub: StubBw, tmp_path: Path) -> None:
        from unittest.mock import patch

        from infrafoundry.providers.mikrotik.settings import load_settings

        env = env_with_vault(
            provider_settings={
                MIKROTIK: {
                    "api_url": "https://192.0.2.1",
                    "username": "admin",
                    "password": "secret://bitwarden/Router Admin/password",
                }
            }
        )
        with patch("infrafoundry.providers.mikrotik.settings.ConfigManager") as manager:
            manager.return_value.load_environment.return_value = env
            settings = load_settings(tmp_path, "test")
        assert settings.password == FIXTURE_VALUE

    def test_collector_device(self, stub: StubBw) -> None:
        device = CollectorDeviceConfig(
            name="fw-test",
            type="opnsense",
            address="https://192.0.2.10",
            username="secret://bitwarden/Router Admin/username",
            password="secret://bitwarden/Router Admin/password",
        )
        assert resolve_device(env_with_vault(), device).password == FIXTURE_VALUE

    def test_provider_settings_mixin(self, stub: StubBw) -> None:
        from infrafoundry.core.provider_mixins import TerraformGeneratorMixin

        resolved = TerraformGeneratorMixin._resolve_settings_secret_uris(
            env_with_vault(), {"token": "secret://bitwarden/Router Admin/password"}
        )
        assert resolved == {"token": FIXTURE_VALUE}

    def test_opnsense_resolve(self, stub: StubBw, tmp_path: Path) -> None:
        from unittest.mock import patch

        from infrafoundry.core.provider import ResourceConfig
        from infrafoundry.providers.opnsense.components import _secrets

        res = ResourceConfig(
            name="vip",
            type="virtual_ip",
            provider="opnsense",
            config={"pw": "secret://bitwarden/Router Admin/password"},
        )
        with patch.object(_secrets, "ConfigManager") as manager:
            manager.return_value.load_environment.return_value = env_with_vault()
            out = _secrets.resolve_resource_secrets(tmp_path, "test", [res], "virtual_ip")
        assert out[0].config["pw"] == FIXTURE_VALUE


class TestSecretRefLookup:
    def test_dotted_never_builds_resolver(self, stub: StubBw) -> None:
        with SecretRefLookup(env_with_vault()) as lookup:
            assert lookup.lookup("db.password") == "from-sops"
        assert stub.calls() == []

    def test_env_secrets_uri_and_dotted_same_value(self) -> None:
        with SecretRefLookup(env_with_vault()) as lookup:
            assert lookup.lookup("secret://env_secrets/db/password") == "from-sops"

    def test_dotted_missing_keyerror_value_free(self) -> None:
        with SecretRefLookup(env_with_vault()) as lookup, pytest.raises(KeyError) as exc:
            lookup.lookup("db.nope")
        assert "from-sops" not in str(exc.value)

    @pytest.mark.parametrize("ref", ["secret://file/x", "secret://env/x"])
    def test_unconfigured_backend(self, ref: str) -> None:
        with SecretRefLookup(env_with_vault()) as lookup:
            assert lookup.problem(ref) is not None
            with pytest.raises(KeyError, match="not configured"):
                lookup.lookup(ref)

    def test_bitwarden_needs_block(self) -> None:
        env = EnvironmentConfig(name="t", secrets={})
        assert "not configured" in (SecretRefLookup(env).problem("secret://bitwarden/a/b") or "")

    def test_malformed_is_error_not_dotted(self) -> None:
        with SecretRefLookup(env_with_vault()) as lookup:
            assert "malformed" in (lookup.problem("secret://bitwarden") or "")
            with pytest.raises(KeyError, match="malformed"):
                lookup.lookup("secret://bitwarden")

    def test_problem_is_offline(self, stub: StubBw) -> None:
        with SecretRefLookup(env_with_vault()) as lookup:
            assert lookup.problem("secret://bitwarden/Router Admin/password") is None
            assert lookup.problem("secret://bitwarden/noslash") is not None
            assert lookup.problem("secret://env_secrets/db/password") is None
            assert lookup.problem("secret://env_secrets/db/missing") is not None
            assert lookup.problem("secret://env_secrets/db") is not None
        assert stub.calls() == []

    def test_vault_lookup_and_failure_value_free(self, stub: StubBw) -> None:
        with SecretRefLookup(env_with_vault()) as lookup:
            assert lookup.lookup("secret://bitwarden/Router Admin/password") == FIXTURE_VALUE
            with pytest.raises(KeyError) as exc:
                lookup.lookup("secret://bitwarden/Nope/password")
        assert FIXTURE_VALUE not in str(exc.value)
