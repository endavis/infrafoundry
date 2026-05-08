"""Unit tests for the shared dotted-path cross-reference resolver (#793).

Coverage:
    - ``build_xref_index``: empty input, single resource, multi-type,
      multi-name, round-trip.
    - ``resolve_xref`` bare-name form: hit, miss, miss with empty index.
    - ``resolve_xref`` in-plugin relative form: hit (with current_plugin),
      miss (with current_plugin), no current_plugin returns None.
    - ``resolve_xref`` cross-plugin absolute form: hit, miss, deeply
      nested type (e.g. ``kea.dhcp4.subnets``).
    - ``resolve_xref`` malformed values: empty string, leading dot,
      trailing dot, consecutive dots — all raise ``ValueError``.
    - Interaction round-trip: build index from list, resolve each
      resource by its (type, name) and verify identity.
"""

from __future__ import annotations

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.validators._xref import (
    XRefIndex,
    build_xref_index,
    resolve_xref,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(
    name: str,
    type_: str,
    *,
    provider: str = "opnsense",
) -> ResourceConfig:
    """Return a minimal ResourceConfig — config is empty since the resolver
    only inspects ``name`` and ``type``."""
    return ResourceConfig(name=name, type=type_, provider=provider, config={})


# ---------------------------------------------------------------------------
# build_xref_index
# ---------------------------------------------------------------------------


class TestBuildXRefIndex:
    def test_empty_input_returns_empty_dict(self) -> None:
        assert build_xref_index([]) == {}

    def test_single_resource_indexed(self) -> None:
        gw = _resource("WAN_GW", "routing.gateways")
        index = build_xref_index([gw])
        assert index == {"routing.gateways": {"WAN_GW": gw}}

    def test_multiple_types_grouped_separately(self) -> None:
        gw = _resource("WAN_GW", "routing.gateways")
        alias = _resource("admins", "firewall.aliases")
        rule = _resource("allow_admin", "firewall.rules")
        index = build_xref_index([gw, alias, rule])
        assert set(index.keys()) == {
            "routing.gateways",
            "firewall.aliases",
            "firewall.rules",
        }
        assert index["routing.gateways"]["WAN_GW"] is gw
        assert index["firewall.aliases"]["admins"] is alias
        assert index["firewall.rules"]["allow_admin"] is rule

    def test_multiple_names_per_type_indexed(self) -> None:
        a1 = _resource("admins", "firewall.aliases")
        a2 = _resource("guests", "firewall.aliases")
        a3 = _resource("trusted", "firewall.aliases")
        index = build_xref_index([a1, a2, a3])
        assert set(index["firewall.aliases"].keys()) == {"admins", "guests", "trusted"}
        assert index["firewall.aliases"]["admins"] is a1
        assert index["firewall.aliases"]["guests"] is a2
        assert index["firewall.aliases"]["trusted"] is a3

    def test_deeply_nested_type_preserved_verbatim(self) -> None:
        subnet = _resource("vlan10", "kea.dhcp4.subnets")
        index = build_xref_index([subnet])
        assert "kea.dhcp4.subnets" in index
        assert index["kea.dhcp4.subnets"]["vlan10"] is subnet

    def test_collision_last_resource_wins(self) -> None:
        # Uniqueness is enforced by ResourceNameValidator, not here —
        # the index silently overwrites collisions.
        first = _resource("admins", "firewall.aliases")
        second = _resource("admins", "firewall.aliases")
        index = build_xref_index([first, second])
        assert index["firewall.aliases"]["admins"] is second


# ---------------------------------------------------------------------------
# resolve_xref — bare name form
# ---------------------------------------------------------------------------


class TestResolveXRefBareName:
    def test_bare_name_hit(self) -> None:
        gw = _resource("WAN_GW", "routing.gateways")
        index = build_xref_index([gw])
        result = resolve_xref("WAN_GW", "routing.gateways", index)
        assert result is gw

    def test_bare_name_miss(self) -> None:
        gw = _resource("WAN_GW", "routing.gateways")
        index = build_xref_index([gw])
        result = resolve_xref("UNKNOWN", "routing.gateways", index)
        assert result is None

    def test_bare_name_miss_unknown_type(self) -> None:
        gw = _resource("WAN_GW", "routing.gateways")
        index = build_xref_index([gw])
        # Bare name lookup uses ``expected_type``; if the type isn't
        # in the index the result is None.
        result = resolve_xref("WAN_GW", "firewall.aliases", index)
        assert result is None

    def test_bare_name_miss_with_empty_index(self) -> None:
        result = resolve_xref("WAN_GW", "routing.gateways", {})
        assert result is None

    def test_bare_name_ignores_current_plugin(self) -> None:
        # ``current_plugin`` is only consulted for the single-dot form.
        gw = _resource("WAN_GW", "routing.gateways")
        index = build_xref_index([gw])
        result = resolve_xref("WAN_GW", "routing.gateways", index, current_plugin="opnsense")
        assert result is gw


# ---------------------------------------------------------------------------
# resolve_xref — in-plugin relative form
# ---------------------------------------------------------------------------


class TestResolveXRefInPluginRelative:
    def test_in_plugin_relative_hit(self) -> None:
        # ``accounts.letsencrypt-prod`` with current_plugin=acmeclient
        # resolves to type ``acmeclient.accounts``, name ``letsencrypt-prod``.
        account = _resource("letsencrypt-prod", "acmeclient.accounts")
        index = build_xref_index([account])
        result = resolve_xref(
            "accounts.letsencrypt-prod",
            expected_type="acmeclient.accounts",
            index=index,
            current_plugin="acmeclient",
        )
        assert result is account

    def test_in_plugin_relative_miss_unknown_name(self) -> None:
        account = _resource("letsencrypt-prod", "acmeclient.accounts")
        index = build_xref_index([account])
        result = resolve_xref(
            "accounts.unknown",
            expected_type="acmeclient.accounts",
            index=index,
            current_plugin="acmeclient",
        )
        assert result is None

    def test_in_plugin_relative_miss_unknown_sub(self) -> None:
        # ``unknown.foo`` with current_plugin=acmeclient resolves to
        # type ``acmeclient.unknown`` — not in the index.
        account = _resource("letsencrypt-prod", "acmeclient.accounts")
        index = build_xref_index([account])
        result = resolve_xref(
            "unknown.letsencrypt-prod",
            expected_type="acmeclient.accounts",
            index=index,
            current_plugin="acmeclient",
        )
        assert result is None

    def test_in_plugin_relative_without_current_plugin_returns_none(self) -> None:
        # Without current_plugin, the single-dot form is unresolvable.
        account = _resource("letsencrypt-prod", "acmeclient.accounts")
        index = build_xref_index([account])
        result = resolve_xref(
            "accounts.letsencrypt-prod",
            expected_type="acmeclient.accounts",
            index=index,
            current_plugin=None,
        )
        assert result is None

    def test_in_plugin_relative_uses_current_plugin_not_expected_type(self) -> None:
        # Even when expected_type and current_plugin disagree, the
        # current_plugin wins for the single-dot form. Useful for
        # explicit dotted refs that don't match the field's default.
        gw = _resource("WAN_GW", "routing.gateways")
        index = build_xref_index([gw])
        result = resolve_xref(
            "gateways.WAN_GW",
            expected_type="firewall.aliases",  # ignored for dotted form
            index=index,
            current_plugin="routing",
        )
        assert result is gw


# ---------------------------------------------------------------------------
# resolve_xref — cross-plugin absolute form
# ---------------------------------------------------------------------------


class TestResolveXRefCrossPluginAbsolute:
    def test_two_segment_dotted_type_hit(self) -> None:
        # ``cron.jobs.acmeclient-auto-renew`` resolves to type
        # ``cron.jobs``, name ``acmeclient-auto-renew``.
        job = _resource("acmeclient-auto-renew", "cron.jobs")
        index = build_xref_index([job])
        result = resolve_xref(
            "cron.jobs.acmeclient-auto-renew",
            expected_type="cron.jobs",
            index=index,
        )
        assert result is job

    def test_three_segment_dotted_type_hit(self) -> None:
        # ``kea.dhcp4.subnets.vlan10`` resolves to type
        # ``kea.dhcp4.subnets``, name ``vlan10``.
        subnet = _resource("vlan10", "kea.dhcp4.subnets")
        index = build_xref_index([subnet])
        result = resolve_xref(
            "kea.dhcp4.subnets.vlan10",
            expected_type="kea.dhcp4.subnets",
            index=index,
        )
        assert result is subnet

    def test_cross_plugin_absolute_miss_unknown_name(self) -> None:
        job = _resource("acmeclient-auto-renew", "cron.jobs")
        index = build_xref_index([job])
        result = resolve_xref(
            "cron.jobs.unknown",
            expected_type="cron.jobs",
            index=index,
        )
        assert result is None

    def test_cross_plugin_absolute_miss_unknown_type(self) -> None:
        # Type ``cron.unknown`` not in index.
        job = _resource("acmeclient-auto-renew", "cron.jobs")
        index = build_xref_index([job])
        result = resolve_xref(
            "cron.unknown.acmeclient-auto-renew",
            expected_type="cron.jobs",
            index=index,
        )
        assert result is None

    def test_cross_plugin_absolute_ignores_current_plugin(self) -> None:
        # Cross-plugin absolute does NOT prepend current_plugin.
        gw = _resource("WAN_GW", "routing.gateways")
        index = build_xref_index([gw])
        result = resolve_xref(
            "routing.gateways.WAN_GW",
            expected_type="firewall.aliases",
            index=index,
            current_plugin="acmeclient",  # ignored
        )
        assert result is gw

    def test_cross_plugin_absolute_ignores_expected_type(self) -> None:
        # When the path is fully qualified, ``expected_type`` is ignored.
        gw = _resource("WAN_GW", "routing.gateways")
        index = build_xref_index([gw])
        result = resolve_xref(
            "routing.gateways.WAN_GW",
            expected_type="firewall.aliases",  # ignored
            index=index,
        )
        assert result is gw


# ---------------------------------------------------------------------------
# resolve_xref — malformed input
# ---------------------------------------------------------------------------


class TestResolveXRefMalformed:
    def test_empty_value_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            resolve_xref("", "routing.gateways", {})

    def test_leading_dot_raises(self) -> None:
        with pytest.raises(ValueError, match="must not start or end with"):
            resolve_xref(".foo", "routing.gateways", {})

    def test_trailing_dot_raises(self) -> None:
        with pytest.raises(ValueError, match="must not start or end with"):
            resolve_xref("foo.", "routing.gateways", {})

    def test_consecutive_dots_raises(self) -> None:
        with pytest.raises(ValueError, match="consecutive dots"):
            resolve_xref("foo..bar", "routing.gateways", {})

    def test_lone_dot_raises(self) -> None:
        # ``.`` is both leading-dot and trailing-dot — first check
        # wins, but either error is acceptable.
        with pytest.raises(ValueError):
            resolve_xref(".", "routing.gateways", {})

    def test_consecutive_dots_in_middle_raises(self) -> None:
        with pytest.raises(ValueError, match="consecutive dots"):
            resolve_xref("a.b..c", "routing.gateways", {})


# ---------------------------------------------------------------------------
# Round-trip: build index, resolve each resource by its own type/name
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_resolve_each_resource_by_bare_name(self) -> None:
        resources = [
            _resource("WAN_GW", "routing.gateways"),
            _resource("admins", "firewall.aliases"),
            _resource("allow_admin", "firewall.rules"),
            _resource("vlan10", "kea.dhcp4.subnets"),
        ]
        index = build_xref_index(resources)
        for resource in resources:
            result = resolve_xref(resource.name, resource.type, index)
            assert result is resource

    def test_resolve_each_resource_by_cross_plugin_absolute(self) -> None:
        resources = [
            _resource("WAN_GW", "routing.gateways"),
            _resource("admins", "firewall.aliases"),
            _resource("vlan10", "kea.dhcp4.subnets"),
        ]
        index = build_xref_index(resources)
        for resource in resources:
            full_path = f"{resource.type}.{resource.name}"
            result = resolve_xref(full_path, resource.type, index)
            assert result is resource

    def test_resolve_each_resource_by_in_plugin_relative(self) -> None:
        # For an in-plugin relative ref the current_plugin is the
        # first dotted segment of the resource's type.
        resources = [
            _resource("WAN_GW", "routing.gateways"),
            _resource("admins", "firewall.aliases"),
        ]
        index = build_xref_index(resources)
        for resource in resources:
            plugin, _, sub = resource.type.partition(".")
            value = f"{sub}.{resource.name}"
            result = resolve_xref(
                value,
                expected_type=resource.type,
                index=index,
                current_plugin=plugin,
            )
            assert result is resource


# ---------------------------------------------------------------------------
# Type alias smoke test (mypy strict catches mis-shapes; a runtime
# assertion is included for parity with the runtime behaviour).
# ---------------------------------------------------------------------------


class TestTypeAlias:
    def test_xref_index_alias_is_dict_of_dicts(self) -> None:
        index: XRefIndex = build_xref_index([_resource("WAN_GW", "routing.gateways")])
        assert isinstance(index, dict)
        for type_bucket in index.values():
            assert isinstance(type_bucket, dict)
            for resource in type_bucket.values():
                assert isinstance(resource, ResourceConfig)
