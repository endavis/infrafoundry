"""Tests for the in-memory env-secrets backend.

Coverage:
    - ``__init__`` accepts a dict via the ``secrets`` config key, treats
      a missing ``secrets`` as an empty tree, and rejects non-dict types.
    - ``get_secret`` walks ``/``-split paths through nested dicts;
      raises ``SecretNotFoundError`` for missing segments and for paths
      that resolve to a sub-tree (not a leaf); coerces non-string leaves
      to ``str``.
    - ``list_secrets`` returns sorted leaf paths and supports a prefix
      filter; returns empty list for an empty tree.
    - ``health_check`` always True.
    - ``register()`` returns ``SecretBackendMetadata`` with the expected
      backend name and class.
    - End-to-end resolution through ``SecretResolver`` for the canonical
      ``secret://env_secrets/<dotted/path>`` URI form (validates that
      the registered plugin is discoverable).
"""

from __future__ import annotations

import pytest

from infrafoundry.secrets.backends.env_secrets import EnvSecretsBackend, register
from infrafoundry.secrets.plugin_type import SecretBackendMetadata
from infrafoundry.secrets.protocol import SecretBackendError, SecretNotFoundError

# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_with_secrets_dict(self) -> None:
        backend = EnvSecretsBackend({"secrets": {"db": {"password": "x"}}})
        assert backend.secrets == {"db": {"password": "x"}}

    def test_missing_secrets_treated_as_empty(self) -> None:
        backend = EnvSecretsBackend({})
        assert backend.secrets == {}

    def test_none_secrets_treated_as_empty(self) -> None:
        backend = EnvSecretsBackend({"secrets": None})
        assert backend.secrets == {}

    def test_non_dict_secrets_rejected(self) -> None:
        with pytest.raises(SecretBackendError, match="dict"):
            EnvSecretsBackend({"secrets": "oops"})

    def test_non_dict_secrets_list_rejected(self) -> None:
        with pytest.raises(SecretBackendError, match="dict"):
            EnvSecretsBackend({"secrets": ["nope"]})


# ---------------------------------------------------------------------------
# get_secret
# ---------------------------------------------------------------------------


class TestGetSecret:
    def test_flat_key(self) -> None:
        backend = EnvSecretsBackend({"secrets": {"token": "abc"}})
        assert backend.get_secret("token") == "abc"

    def test_nested_path(self) -> None:
        backend = EnvSecretsBackend(
            {"secrets": {"opnsense": {"carp_passwords": {"lan_carp_1": "s3kr1t"}}}}
        )
        assert backend.get_secret("opnsense/carp_passwords/lan_carp_1") == "s3kr1t"

    def test_missing_top_level_key(self) -> None:
        backend = EnvSecretsBackend({"secrets": {"db": {"password": "x"}}})
        with pytest.raises(SecretNotFoundError, match="missing segment 'api'"):
            backend.get_secret("api/token")

    def test_missing_intermediate_key(self) -> None:
        backend = EnvSecretsBackend({"secrets": {"db": {"password": "x"}}})
        with pytest.raises(SecretNotFoundError, match="missing segment 'host'"):
            backend.get_secret("db/host")

    def test_missing_deeply_nested(self) -> None:
        backend = EnvSecretsBackend({"secrets": {"a": {"b": {"c": "leaf"}}}})
        with pytest.raises(SecretNotFoundError, match="missing segment 'd'"):
            backend.get_secret("a/b/c/d")

    def test_path_resolves_to_dict_raises(self) -> None:
        # Operator named a sub-tree, not a leaf.
        backend = EnvSecretsBackend({"secrets": {"db": {"password": "x"}}})
        with pytest.raises(SecretNotFoundError, match="dict"):
            backend.get_secret("db")

    def test_int_value_coerced_to_string(self) -> None:
        backend = EnvSecretsBackend({"secrets": {"port": 8080}})
        assert backend.get_secret("port") == "8080"

    def test_float_value_coerced_to_string(self) -> None:
        backend = EnvSecretsBackend({"secrets": {"rate": 1.5}})
        assert backend.get_secret("rate") == "1.5"

    def test_bool_value_coerced_to_string(self) -> None:
        backend = EnvSecretsBackend({"secrets": {"flag": True}})
        assert backend.get_secret("flag") == "True"

    def test_empty_secrets_raises(self) -> None:
        backend = EnvSecretsBackend({"secrets": {}})
        with pytest.raises(SecretNotFoundError):
            backend.get_secret("anything")


# ---------------------------------------------------------------------------
# list_secrets
# ---------------------------------------------------------------------------


class TestListSecrets:
    def test_flat(self) -> None:
        backend = EnvSecretsBackend({"secrets": {"a": "1", "b": "2"}})
        assert backend.list_secrets() == ["a", "b"]

    def test_nested(self) -> None:
        backend = EnvSecretsBackend(
            {"secrets": {"db": {"host": "localhost", "password": "secret"}}}
        )
        assert backend.list_secrets() == ["db/host", "db/password"]

    def test_empty(self) -> None:
        backend = EnvSecretsBackend({"secrets": {}})
        assert backend.list_secrets() == []

    def test_prefix_filter(self) -> None:
        backend = EnvSecretsBackend(
            {
                "secrets": {
                    "db": {"host": "localhost", "password": "secret"},
                    "api": {"token": "tok"},
                }
            }
        )
        assert backend.list_secrets("db/") == ["db/host", "db/password"]
        assert backend.list_secrets("api/") == ["api/token"]
        assert backend.list_secrets("nothing/") == []

    def test_deep_nesting(self) -> None:
        backend = EnvSecretsBackend(
            {
                "secrets": {
                    "opnsense": {
                        "carp_passwords": {
                            "lan_carp_1": "x",
                            "wan_carp_1": "y",
                        },
                    }
                }
            }
        )
        assert backend.list_secrets() == [
            "opnsense/carp_passwords/lan_carp_1",
            "opnsense/carp_passwords/wan_carp_1",
        ]

    def test_sorted_output(self) -> None:
        # Keys inserted in non-sorted order; output must still be sorted.
        backend = EnvSecretsBackend({"secrets": {"z": "1", "a": "2", "m": "3"}})
        assert backend.list_secrets() == ["a", "m", "z"]


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_always_true(self) -> None:
        assert EnvSecretsBackend({"secrets": {}}).health_check() is True

    def test_true_with_data(self) -> None:
        assert EnvSecretsBackend({"secrets": {"x": "y"}}).health_check() is True


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


class TestRegister:
    def test_returns_metadata(self) -> None:
        metadata = register()
        assert isinstance(metadata, SecretBackendMetadata)

    def test_name_is_env_secrets(self) -> None:
        assert register().name == "env_secrets"

    def test_backend_class_is_env_secrets_backend(self) -> None:
        assert register().backend_class is EnvSecretsBackend

    def test_read_only(self) -> None:
        assert register().read_only is True

    def test_has_description(self) -> None:
        assert register().description


# ---------------------------------------------------------------------------
# End-to-end resolution via SecretResolver
# ---------------------------------------------------------------------------


class TestResolverIntegration:
    """End-to-end resolution through ``SecretResolver``.

    The plugin registry is not auto-loaded in the test environment, so
    each test registers the backend manually (mirrors the pattern in
    ``tests/unit/secrets/test_resolver.py``).
    """

    @staticmethod
    def _register_backend() -> None:
        # The registry is module-level; if a sibling test already
        # registered the backend we are good to go.
        import contextlib

        from infrafoundry.core.plugin_system import get_registry
        from infrafoundry.core.plugin_system.exceptions import PluginConflictError
        from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

        registry = get_registry()
        with contextlib.suppress(PluginConflictError):
            registry.register(
                PluginMetadata(
                    name="env_secrets",
                    version="1.0.0",
                    plugin_type="secret_backend",
                    description="Test",
                    implementation=EnvSecretsBackend,
                )
            )

    def test_resolve_uri_through_resolver(self) -> None:
        # Confirms the resolver hands a ``secret://env_secrets/<path>``
        # URI off to ``EnvSecretsBackend`` and returns its value.
        from infrafoundry.secrets.resolver import SecretResolver

        self._register_backend()
        resolver = SecretResolver()
        resolver.configure_backend(
            "env_secrets",
            {"secrets": {"opnsense": {"carp_passwords": {"lan_carp_1": "s3kr1t"}}}},
        )
        value = resolver.resolve("secret://env_secrets/opnsense/carp_passwords/lan_carp_1")
        assert value == "s3kr1t"
        resolver.close()

    def test_resolve_config_walks_nested_dict(self) -> None:
        from infrafoundry.secrets.resolver import SecretResolver

        self._register_backend()
        resolver = SecretResolver()
        resolver.configure_backend(
            "env_secrets",
            {"secrets": {"opnsense": {"carp_passwords": {"lan_carp_1": "s3kr1t"}}}},
        )
        config = {
            "address": "10.0.0.1",
            "password": "secret://env_secrets/opnsense/carp_passwords/lan_carp_1",
            "vhid": "1",
        }
        resolved = resolver.resolve_config(config)
        assert resolved["address"] == "10.0.0.1"
        assert resolved["password"] == "s3kr1t"
        assert resolved["vhid"] == "1"
        resolver.close()
