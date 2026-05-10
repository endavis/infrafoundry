"""Unit tests for the nested ``opnsense:`` provider-namespace YAML format.

Covers ``PackageLoader._parse_nested_provider_format`` and the
``_parse_resources_from_data`` detection branch added in #793 Phase 2 per
ADR-0016. The flat (resource-centric / provider-centric) parse paths are
covered by ``tests/unit/test_package_loader.py`` and remain unchanged in
this phase.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from infrafoundry.core.config.package_loader import (
    DOTTED_RESOURCE_SHAPES,
    DOTTED_RESOURCE_TYPES,
    NESTED_PROVIDER_NAMESPACE,
    PackageLoader,
)
from infrafoundry.core.config.provider_centric_loader import ProviderCentricLoader
from infrafoundry.core.config.resource_centric_loader import ResourceCentricLoader
from infrafoundry.core.exceptions import InvalidConfigurationError


@pytest.mark.unit
class TestNestedFormatConstants:
    """Sanity checks for the ADR-0016 dotted-path tables."""

    def test_namespace_is_opnsense(self):
        """Top-level YAML key is ``opnsense:`` per ADR-0016."""
        assert NESTED_PROVIDER_NAMESPACE == "opnsense"

    def test_dotted_shapes_includes_existing_list_types(self):
        """The 15 currently-shipped direct-OPNsense paths are list-shape."""
        assert DOTTED_RESOURCE_SHAPES["firewall.aliases"] == "list"
        assert DOTTED_RESOURCE_SHAPES["firewall.rules"] == "list"
        assert DOTTED_RESOURCE_SHAPES["routing.gateways"] == "list"
        assert DOTTED_RESOURCE_SHAPES["routing.static"] == "list"
        assert DOTTED_RESOURCE_SHAPES["interfaces.vlans"] == "list"
        assert DOTTED_RESOURCE_SHAPES["unbound.host_overrides"] == "list"
        assert DOTTED_RESOURCE_SHAPES["kea.dhcp4.subnets"] == "list"
        assert DOTTED_RESOURCE_SHAPES["kea.dhcp6.reservations"] == "list"

    def test_dotted_shapes_includes_documented_singletons(self):
        """ADR-0016 future singletons are registered as dict-shape."""
        # #786 firewall_log
        assert DOTTED_RESOURCE_SHAPES["firewall.log"] == "dict"
        # #787 tailscale settings
        assert DOTTED_RESOURCE_SHAPES["tailscale.settings"] == "dict"
        # #788 radvd
        assert DOTTED_RESOURCE_SHAPES["radvd"] == "dict"

    def test_dotted_resource_types_matches_shapes(self):
        """``DOTTED_RESOURCE_TYPES`` mirrors ``DOTTED_RESOURCE_SHAPES`` keys."""
        assert frozenset(DOTTED_RESOURCE_SHAPES) == DOTTED_RESOURCE_TYPES


@pytest.mark.unit
class TestParseNestedSingleton:
    """Singleton (dict-leaf) shape — emits one ResourceConfig with name='settings'."""

    def test_firewall_log_singleton_emits_one_settings(self, temp_dir):
        """``opnsense.firewall.log`` dict leaf becomes a ``settings`` resource."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "log": {
                        "log_default_block": False,
                        "log_default_pass": False,
                    }
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "test.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].name == "settings"
        assert resources[0].type == "firewall.log"
        assert resources[0].provider == "opnsense"
        assert resources[0].config == {
            "log_default_block": False,
            "log_default_pass": False,
        }

    def test_tailscale_settings_singleton(self, temp_dir):
        """``opnsense.tailscale.settings`` is a registered singleton."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "tailscale": {
                    "settings": {"enabled": True, "exit_node": False},
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "ts.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].name == "settings"
        assert resources[0].type == "tailscale.settings"
        assert resources[0].config == {"enabled": True, "exit_node": False}

    def test_radvd_singleton_at_first_level(self, temp_dir):
        """``opnsense.radvd`` is a registered single-segment singleton."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"radvd": {"interfaces": ["lan"], "ra_lifetime": 1800}}}
        resources = loader._parse_resources_from_data(data, "radvd.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].name == "settings"
        assert resources[0].type == "radvd"
        assert resources[0].config == {"interfaces": ["lan"], "ra_lifetime": 1800}

    def test_singleton_config_is_a_copy(self, temp_dir):
        """Mutating the emitted ``config`` does not leak into source data."""
        loader = PackageLoader(temp_dir)
        original = {"log_default_block": False}
        data = {"opnsense": {"firewall": {"log": original}}}
        resources = loader._parse_resources_from_data(data, "test.yaml", "opnsense")
        resources[0].config["log_default_block"] = True
        assert original == {"log_default_block": False}

    def test_system_hostname_singleton_round_trip(self, temp_dir):
        """``opnsense.system.hostname`` (#806) emits exactly one settings resource.

        Round-trip check: the nested YAML dict at ``opnsense.system.hostname``
        becomes one ``ResourceConfig`` with ``type="system.hostname"``,
        ``name="settings"``, and the dict carried verbatim as ``.config``.
        Confirms the seven ``system.*`` singletons added in #806 work
        through the nested-format loader.
        """
        loader = PackageLoader(temp_dir)
        hostname_config = {
            "hostname": "opnsense-a",
            "domain": "endavis.net",
            "timezone": "Etc/UTC",
            "language": "en_US",
        }
        data = {"opnsense": {"system": {"hostname": hostname_config}}}
        resources = loader._parse_resources_from_data(data, "system.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].name == "settings"
        assert resources[0].type == "system.hostname"
        assert resources[0].provider == "opnsense"
        assert resources[0].config == hostname_config


@pytest.mark.unit
class TestParseNestedList:
    """List (sequence-leaf) shape — emits one ResourceConfig per entry."""

    def test_firewall_aliases_list(self, temp_dir):
        """``opnsense.firewall.aliases`` list leaf emits one config per entry."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "aliases": [
                        {
                            "name": "web-servers",
                            "config": {"type": "host", "content": "10.0.0.1"},
                        },
                        {
                            "name": "db-servers",
                            "config": {"type": "host", "content": "10.0.0.5"},
                        },
                    ]
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        assert len(resources) == 2
        names = {r.name for r in resources}
        assert names == {"web-servers", "db-servers"}
        for resource in resources:
            assert resource.type == "firewall.aliases"
            assert resource.provider == "opnsense"

    def test_kea_dhcp4_subnets_three_levels_deep(self, temp_dir):
        """Three-level dotted path (kea.dhcp4.subnets) walks correctly."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "kea": {
                    "dhcp4": {
                        "subnets": [
                            {"name": "lan", "config": {"subnet": "10.0.0.0/24"}},
                        ]
                    }
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "kea.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].type == "kea.dhcp4.subnets"
        assert resources[0].name == "lan"

    def test_routing_gateways_list_carries_per_entry_metadata(self, temp_dir):
        """List entries' ``provider`` / ``import_id`` / ``events`` propagate."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "routing": {
                    "gateways": [
                        {
                            "name": "wan-gw",
                            "import_id": "GWID_WAN",
                            "config": {"gateway": "1.2.3.4"},
                            "events": {
                                "AFTER_APPLY": [{"type": "webhook", "url": "https://x"}],
                            },
                        }
                    ]
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "gw.yaml", "opnsense")
        assert len(resources) == 1
        gw = resources[0]
        assert gw.import_id == "GWID_WAN"
        assert gw.events is not None
        assert gw.events["AFTER_APPLY"][0]["url"] == "https://x"

    def test_empty_list_emits_nothing(self, temp_dir):
        """An empty list at a known list-shape path emits zero resources."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"firewall": {"aliases": []}}}
        resources = loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        assert resources == []


@pytest.mark.unit
class TestParseNestedMixed:
    """Mixed dict + list shapes coexisting under the same plugin sub-tree."""

    def test_dict_singleton_and_list_collection_under_firewall(self, temp_dir):
        """``firewall: {log: {...}, aliases: [...], rules: [...]}`` works."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "log": {"log_default_block": False},
                    "aliases": [{"name": "trusted", "config": {"type": "host"}}],
                    "rules": [{"name": "allow-web", "config": {"interface": "lan"}}],
                }
            }
        }
        resources = loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        types = {r.type for r in resources}
        assert types == {"firewall.log", "firewall.aliases", "firewall.rules"}
        # Singleton has name="settings"; list entries keep their own names.
        log_resource = next(r for r in resources if r.type == "firewall.log")
        assert log_resource.name == "settings"
        alias_resource = next(r for r in resources if r.type == "firewall.aliases")
        assert alias_resource.name == "trusted"

    def test_multi_plugin_under_opnsense(self, temp_dir):
        """Multiple plugins (firewall, routing, kea, unbound) coexist."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "aliases": [{"name": "a1", "config": {}}],
                },
                "routing": {
                    "gateways": [{"name": "g1", "config": {}}],
                    "static": [{"name": "s1", "config": {}}],
                },
                "unbound": {
                    "host_overrides": [{"name": "h1", "config": {}}],
                },
                "kea": {
                    "dhcp4": {
                        "subnets": [{"name": "k1", "config": {}}],
                    }
                },
            }
        }
        resources = loader._parse_resources_from_data(data, "all.yaml", "opnsense")
        types = {r.type for r in resources}
        assert types == {
            "firewall.aliases",
            "routing.gateways",
            "routing.static",
            "unbound.host_overrides",
            "kea.dhcp4.subnets",
        }
        assert len(resources) == 5


@pytest.mark.unit
class TestParseNestedEmpty:
    """Empty / missing nested structures."""

    def test_empty_namespace_emits_nothing(self, temp_dir):
        """``opnsense: {}`` returns an empty list."""
        loader = PackageLoader(temp_dir)
        data: dict = {"opnsense": {}}
        resources = loader._parse_resources_from_data(data, "empty.yaml", "opnsense")
        assert resources == []

    def test_empty_data_returns_empty_list(self, temp_dir):
        """Empty data dict returns an empty list (existing behaviour)."""
        loader = PackageLoader(temp_dir)
        resources = loader._parse_resources_from_data({}, "empty.yaml", "opnsense")
        assert resources == []

    def test_namespace_value_none_falls_through_to_flat(self, temp_dir):
        """``opnsense: null`` does not trigger nested parsing.

        ``null`` is not a dict, so the existing flat-format code path is
        used. Filename stem ``opnsense`` is not a known type so nothing
        is emitted (consistent with passing through to the flat branch).
        """
        loader = PackageLoader(temp_dir)
        data: dict = {"opnsense": None}
        resources = loader._parse_resources_from_data(data, "opnsense.yaml", "opnsense")
        # Flat path treats opnsense: null as an empty resource list for the
        # filename-derived stem.
        assert resources == []


@pytest.mark.unit
class TestParseNestedUnknownPath:
    """Unknown dotted paths under ``opnsense:`` are rejected."""

    def test_unknown_top_level_plugin_with_list_leaf(self, temp_dir):
        """``opnsense.bogus.thing: [...]`` raises with the bad path."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"bogus": {"thing": [{"name": "x"}]}}}
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bogus.yaml", "opnsense")
        assert "bogus.thing" in str(excinfo.value)
        assert "unknown nested resource path" in str(excinfo.value)

    def test_unknown_path_under_known_plugin(self, temp_dir):
        """``opnsense.firewall.unknown: [...]`` is rejected."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"firewall": {"unknown": [{"name": "x"}]}}}
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")
        assert "firewall.unknown" in str(excinfo.value)


@pytest.mark.unit
class TestParseNestedShapeMismatch:
    """Shape mismatches (list vs dict) are rejected with a clear error."""

    def test_known_list_path_with_dict_leaf_rejected(self, temp_dir):
        """``firewall.aliases: {...}`` (dict where list expected) errors."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {"aliases": {"name": "oops", "config": {}}},
            }
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.aliases" in msg
        assert "list" in msg

    def test_known_dict_path_with_list_leaf_rejected(self, temp_dir):
        """``firewall.log: [...]`` (list where dict expected) errors."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"firewall": {"log": [{"x": 1}]}}}
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.log" in msg
        assert "dict" in msg


@pytest.mark.unit
class TestParseNestedMalformedLeaf:
    """Scalar / malformed leaves at known paths are rejected."""

    def test_string_leaf_rejected(self, temp_dir):
        """A string at a leaf raises a clear error."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"firewall": {"aliases": "not-a-list"}}}
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.aliases" in msg
        assert "str" in msg

    def test_int_leaf_rejected(self, temp_dir):
        """An int at a leaf raises a clear error."""
        loader = PackageLoader(temp_dir)
        data = {"opnsense": {"firewall": {"log": 42}}}
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "bad.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.log" in msg

    def test_top_level_list_under_namespace_rejected(self, temp_dir):
        """A bare list directly under ``opnsense:`` is rejected.

        ``opnsense:`` itself is not a dict in this case, so the nested
        branch is not entered. The existing flat path treats ``opnsense:``
        like a top-level list keyed off the filename stem.
        """
        loader = PackageLoader(temp_dir)
        data = {"opnsense": ["a", "b"]}
        # Not a dict — falls through to flat parsing. Filename stem
        # 'opnsense' is not a known type, so we look up data['opnsense'],
        # which is a list of non-dicts; result is an empty list (existing
        # behaviour for non-dict items).
        resources = loader._parse_resources_from_data(data, "opnsense.yaml", "opnsense")
        assert resources == []


@pytest.mark.unit
class TestParseNestedListEntryValidation:
    """Each list entry must be a dict with a ``name:`` field."""

    def test_missing_name_in_list_entry_raises(self, temp_dir):
        """List entry without ``name:`` raises a clear error."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "aliases": [{"config": {"type": "host"}}],
                }
            }
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.aliases" in msg
        assert "name" in msg

    def test_non_dict_list_entry_raises(self, temp_dir):
        """List entry that is a scalar raises a clear error."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {"aliases": ["bare-string-not-dict"]},
            }
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "firewall.aliases" in msg
        assert "str" in msg

    def test_list_entry_index_in_error_message(self, temp_dir):
        """Error message references the offending list entry index."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {
                "firewall": {
                    "aliases": [
                        {"name": "ok", "config": {}},
                        {"config": {}},  # missing name at index 1
                    ]
                }
            }
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "fw.yaml", "opnsense")
        # Either order of stack pop is fine as long as index 1 is named.
        assert "1" in str(excinfo.value)


@pytest.mark.unit
class TestNestedFlatAmbiguity:
    """Mixing nested ``opnsense:`` with other top-level keys is rejected."""

    def test_nested_alongside_flat_aliases_rejected(self, temp_dir):
        """``opnsense:`` plus a flat top-level key is ambiguous."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {"firewall": {"log": {"log_default_block": False}}},
            "aliases": [{"name": "x", "config": {}}],
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "mixed.yaml", "opnsense")
        msg = str(excinfo.value)
        assert "cannot mix" in msg
        assert "aliases" in msg

    def test_nested_alongside_resource_centric_rejected(self, temp_dir):
        """``opnsense:`` plus ``resources:`` is ambiguous."""
        loader = PackageLoader(temp_dir)
        data = {
            "opnsense": {"firewall": {"log": {"log_default_block": False}}},
            "resources": [{"provider": "opnsense", "type": "x", "name": "y", "config": {}}],
        }
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_resources_from_data(data, "mixed.yaml", "opnsense")
        assert "cannot mix" in str(excinfo.value)


@pytest.mark.unit
class TestFlatFormatNoLongerTranslated:
    """After Phase 5 hard cutover (#793), legacy flat OPNsense type names
    no longer auto-translate to dotted paths. Operators must use the nested
    ``opnsense:`` schema (or already-dotted types in resource-centric files);
    the conversion script in #793 Phase 6 does the one-shot migration.
    """

    def test_flat_provider_centric_keeps_stem_type(self, temp_dir):
        """``aliases.yaml`` with top-level ``aliases:`` no longer translates.

        The loader still parses the document but emits ``ResourceConfig.type
        == 'aliases'`` (the filename stem). Dispatch will not match any
        OPNsense direct-API component — the operator sees a clear "unknown
        type" error downstream rather than silent acceptance.
        """
        loader = PackageLoader(temp_dir)
        data = {"aliases": [{"name": "trusted", "config": {"type": "host"}}]}
        resources = loader._parse_resources_from_data(data, "aliases.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].type == "aliases"
        assert resources[0].name == "trusted"

    def test_flat_resource_centric_keeps_raw_type(self, temp_dir):
        """``resources:`` with legacy ``type: kea_subnet`` no longer translates."""
        loader = PackageLoader(temp_dir)
        data = {
            "resources": [
                {
                    "provider": "opnsense",
                    "type": "kea_subnet",
                    "name": "lan",
                    "config": {"subnet": "10.0.0.0/24"},
                }
            ]
        }
        resources = loader._parse_resources_from_data(data, "rc.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].type == "kea_subnet"
        assert resources[0].name == "lan"

    def test_resource_centric_dotted_type_passes_through(self, temp_dir):
        """``resources:`` with already-dotted ``type:`` is unchanged."""
        loader = PackageLoader(temp_dir)
        data = {
            "resources": [
                {
                    "provider": "opnsense",
                    "type": "kea.dhcp4.subnets",
                    "name": "lan",
                    "config": {"subnet": "10.0.0.0/24"},
                }
            ]
        }
        resources = loader._parse_resources_from_data(data, "rc.yaml", "opnsense")
        assert len(resources) == 1
        assert resources[0].type == "kea.dhcp4.subnets"

    def test_unknown_nested_key_with_dict_value_recurses(self, temp_dir):
        """Unknown interior dict key recurses without error if no leaves."""
        loader = PackageLoader(temp_dir)
        # ``opnsense.foo.bar`` has no list/dict leaf at a known path —
        # walking finds nothing and returns empty.
        data: dict = {"opnsense": {"foo": {"bar": {"baz": {}}}}}
        resources = loader._parse_resources_from_data(data, "x.yaml", "opnsense")
        assert resources == []


@pytest.mark.unit
class TestNestedFormatProviderCentricLoader:
    """ProviderCentricLoader recognises the nested format too."""

    def _write_yaml(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_provider_centric_loader_parses_nested_singleton(self, temp_dir):
        """Top-level ``opnsense:`` in a flat-style provider file is parsed."""
        loader = ProviderCentricLoader(temp_dir)
        # Filename stem is 'log' but the file is nested-format. The
        # nested branch should win regardless.
        self._write_yaml(
            temp_dir / "dev" / "opnsense" / "log.yaml",
            "opnsense:\n  firewall:\n    log:\n      log_default_block: false\n",
        )
        resources = loader.load_resources("dev", "opnsense", "log")
        assert len(resources) == 1
        assert resources[0].type == "firewall.log"
        assert resources[0].name == "settings"
        assert resources[0].provider == "opnsense"

    def test_provider_centric_loader_parses_nested_list(self, temp_dir):
        """Top-level ``opnsense:`` with list leaves works."""
        loader = ProviderCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "opnsense" / "fw.yaml",
            (
                "opnsense:\n"
                "  firewall:\n"
                "    aliases:\n"
                "      - name: a1\n"
                "        config:\n"
                "          type: host\n"
            ),
        )
        resources = loader.load_resources("dev", "opnsense", "fw")
        assert len(resources) == 1
        assert resources[0].type == "firewall.aliases"
        assert resources[0].name == "a1"

    def test_provider_centric_loader_rejects_mixed_format(self, temp_dir):
        """Mixing ``opnsense:`` with other top-level keys raises."""
        loader = ProviderCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "opnsense" / "fw.yaml",
            (
                "opnsense:\n"
                "  firewall:\n"
                "    log:\n"
                "      log_default_block: false\n"
                "aliases:\n"
                "  - name: x\n"
                "    config: {}\n"
            ),
        )
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader.load_resources("dev", "opnsense", "fw")
        assert "cannot mix" in str(excinfo.value)

    def test_provider_centric_loader_flat_keeps_stem_type(self, temp_dir):
        """After #793 Phase 5, flat OPNsense YAML no longer auto-translates.

        The file parses (so existing test/blueprint fixtures don't break
        outright), but the emitted ``ResourceConfig.type`` is the filename
        stem (``aliases``) rather than the dotted path (``firewall.aliases``).
        Dispatch will reject it downstream — operators must convert to the
        nested ``opnsense:`` schema (see #793 Phase 6 conversion script).
        """
        loader = ProviderCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "opnsense" / "aliases.yaml",
            ("aliases:\n  - name: trusted\n    type: host\n    content: 10.0.0.1\n"),
        )
        resources = loader.load_resources("dev", "opnsense", "aliases")
        assert len(resources) == 1
        assert resources[0].type == "aliases"


@pytest.mark.unit
class TestNestedFormatResourceCentricLoader:
    """ResourceCentricLoader recognises the nested format too."""

    def _write_yaml(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_resource_centric_loader_parses_nested(self, temp_dir):
        """A resource-centric file with ``opnsense:`` at the top is nested."""
        loader = ResourceCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "resources" / "opnsense.yaml",
            (
                "opnsense:\n"
                "  firewall:\n"
                "    log:\n"
                "      log_default_block: false\n"
                "      log_default_pass: true\n"
            ),
        )
        resources = loader.load_resources("dev")
        assert len(resources) == 1
        assert resources[0].type == "firewall.log"
        assert resources[0].name == "settings"
        assert resources[0].provider == "opnsense"
        assert resources[0].config == {
            "log_default_block": False,
            "log_default_pass": True,
        }

    def test_resource_centric_loader_rejects_mixed_format(self, temp_dir):
        """Mixing ``opnsense:`` with ``resources:`` raises."""
        loader = ResourceCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "resources" / "mixed.yaml",
            (
                "opnsense:\n"
                "  firewall:\n"
                "    log:\n"
                "      log_default_block: false\n"
                "resources:\n"
                "  - provider: opnsense\n"
                "    type: kea_subnet\n"
                "    name: lan\n"
                "    config:\n"
                "      subnet: 10.0.0.0/24\n"
            ),
        )
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader.load_resources("dev")
        assert "cannot mix" in str(excinfo.value)

    def test_resource_centric_loader_flat_still_works(self, temp_dir):
        """Existing resource-centric YAML still parses through the loader."""
        loader = ResourceCentricLoader(temp_dir)
        self._write_yaml(
            temp_dir / "dev" / "resources" / "vms.yaml",
            (
                "resources:\n"
                "  - provider: proxmox\n"
                "    type: vm\n"
                "    name: web-01\n"
                "    config:\n"
                "      cores: 4\n"
            ),
        )
        resources = loader.load_resources("dev")
        assert len(resources) == 1
        assert resources[0].name == "web-01"
        assert resources[0].provider == "proxmox"
        assert resources[0].type == "vm"


@pytest.mark.unit
class TestParseNestedDirect:
    """Direct calls to ``_parse_nested_provider_format`` for edge cases."""

    def test_direct_call_with_empty_namespace(self, temp_dir):
        """Calling with an empty dict returns an empty list."""
        loader = PackageLoader(temp_dir)
        result = loader._parse_nested_provider_format({}, "opnsense", "x.yaml")
        assert result == []

    def test_direct_call_carries_provider_argument(self, temp_dir):
        """Provider passed in is reflected in emitted resources."""
        loader = PackageLoader(temp_dir)
        result = loader._parse_nested_provider_format(
            {"firewall": {"log": {"x": 1}}}, "opnsense", "x.yaml"
        )
        assert result[0].provider == "opnsense"

    def test_direct_call_non_string_key_rejected(self, temp_dir):
        """Non-string interior key raises a clear error."""
        loader = PackageLoader(temp_dir)
        # Build a dict with an int key — Python allows it; YAML normally
        # wouldn't, but the loader must defend against it.
        data: dict = {123: {}}
        with pytest.raises(InvalidConfigurationError) as excinfo:
            loader._parse_nested_provider_format(data, "opnsense", "x.yaml")
        assert "must be a string" in str(excinfo.value)
