"""Restricted-delete behaviour of the list diff engines (#1256, ADR-0018).

Every engine takes ``managed_keys``: with a set, a live object missing from YAML
is deleted only when its key is in the set, and otherwise goes to ``Diff.unmanaged``.
``managed_keys=None`` keeps the legacy full reconcile.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from infrafoundry.providers.opnsense.services import (
    alias,
    gateway,
    interface_assignment,
    static_route,
    unbound_forward,
    unbound_host_alias,
    unbound_host_override,
    virtual_ip,
    vlan,
)

#: ``(id, compute_diff, managed key, other key)`` for each engine keyed by config alone.
ENGINES: list[tuple[str, Callable[..., Any], Any, Any]] = [
    ("vlan", vlan.compute_diff, ("igb0", 10), ("igb0", 20)),
    ("alias", alias.compute_diff, "web", "db"),
    ("gateway", gateway.compute_diff, "gw1", "gw2"),
    ("static_route", static_route.compute_diff, ("10.0.0.0/8", "gw1"), ("10.1.0.0/16", "gw1")),
    (
        "virtual_ip",
        virtual_ip.compute_diff,
        ("lan", "ipalias", "172.21.0.2", ""),
        ("lan", "ipalias", "172.21.0.3", ""),
    ),
    ("host_override", unbound_host_override.compute_diff, ("a", "x.lan", "A"), ("b", "x.lan", "A")),
    (
        "forward",
        unbound_forward.compute_diff,
        ("dot", "x.lan", "1.1.1.1", "853"),
        ("dot", "y.lan", "1.1.1.1", "853"),
    ),
    ("host_alias", unbound_host_alias.compute_diff, ("u1", "www"), ("u1", "api")),
    ("assignment", interface_assignment.compute_diff, "opt3", "opt4"),
]
IDS = [e[0] for e in ENGINES]


def _live(key: Any) -> Any:
    return SimpleNamespace(diff_key=key, is_managed=True, type="host", uuid=f"uuid-{key}")


def _want(key: Any, *, lock: bool = False) -> Any:
    return SimpleNamespace(diff_key=key, lock=lock)


@pytest.mark.parametrize(("name", "diff", "managed", "other"), ENGINES, ids=IDS)
class TestRestrictedDelete:
    def test_managed_key_not_desired_is_deleted(
        self, name: str, diff: Callable[..., Any], managed: Any, other: Any
    ) -> None:
        result = diff([], [_live(managed)], managed_keys={managed})
        assert [d.diff_key for d in result.deletes] == [managed]
        assert result.unmanaged == []

    def test_unmanaged_key_goes_to_unmanaged(
        self, name: str, diff: Callable[..., Any], managed: Any, other: Any
    ) -> None:
        result = diff([], [_live(managed), _live(other)], managed_keys={managed})
        assert [d.diff_key for d in result.deletes] == [managed]
        assert [u.diff_key for u in result.unmanaged] == [other]

    def test_empty_managed_set_deletes_nothing(
        self, name: str, diff: Callable[..., Any], managed: Any, other: Any
    ) -> None:
        result = diff([], [_live(other)], managed_keys=set())
        assert result.deletes == []
        assert [u.diff_key for u in result.unmanaged] == [other]

    def test_legacy_mode_deletes_everything_missing(
        self, name: str, diff: Callable[..., Any], managed: Any, other: Any
    ) -> None:
        result = diff([], [_live(managed), _live(other)])
        assert {d.diff_key for d in result.deletes} == {managed, other}
        assert result.unmanaged == []

    def test_add_only_suppresses_managed_deletes(
        self, name: str, diff: Callable[..., Any], managed: Any, other: Any
    ) -> None:
        result = diff([], [_live(managed)], add_only=True, managed_keys={managed})
        assert result.deletes == []
        assert result.unmanaged == []

    def test_locked_key_is_never_deleted(
        self, name: str, diff: Callable[..., Any], managed: Any, other: Any
    ) -> None:
        result = diff([_want(managed, lock=True)], [_live(managed)], managed_keys={managed})
        assert result.deletes == []
        assert result.unmanaged == []
        assert len(result.locked) == 1

    def test_desired_key_is_not_a_delete_even_when_managed(
        self, name: str, diff: Callable[..., Any], managed: Any, other: Any
    ) -> None:
        # A locked want short-circuits the update check, so it stands in for "still desired".
        result = diff(
            [_want(managed, lock=True)], [_live(managed), _live(other)], managed_keys={managed}
        )
        assert result.deletes == []
        assert [u.diff_key for u in result.unmanaged] == [other]

    def test_unmanaged_only_diff_is_empty(
        self, name: str, diff: Callable[..., Any], managed: Any, other: Any
    ) -> None:
        result = diff([], [_live(other)], managed_keys=set())
        assert result.is_empty is True


class TestAssignmentProtectedIdentifiers:
    def test_managed_lan_and_wan_are_never_deleted(self, caplog: pytest.LogCaptureFixture) -> None:
        live = [_live("lan"), _live("wan"), _live("opt3")]
        with caplog.at_level(logging.WARNING):
            result = interface_assignment.compute_diff(
                [], live, managed_keys={"lan", "wan", "opt3"}
            )
        assert [d.diff_key for d in result.deletes] == ["opt3"]
        assert {u.diff_key for u in result.unmanaged} == {"lan", "wan"}
        assert "'lan'" in caplog.text
        assert "'wan'" in caplog.text

    def test_legacy_mode_does_not_protect(self) -> None:
        result = interface_assignment.compute_diff([], [_live("lan"), _live("opt3")])
        assert {d.diff_key for d in result.deletes} == {"lan", "opt3"}

    def test_protected_keys_are_overridable(self) -> None:
        result = interface_assignment.compute_diff(
            [], [_live("lan")], managed_keys={"lan"}, protected_keys=frozenset()
        )
        assert [d.diff_key for d in result.deletes] == ["lan"]

    def test_protected_identifier_that_is_still_desired_is_untouched(self) -> None:
        result = interface_assignment.compute_diff(
            [_want("lan", lock=True)], [_live("lan")], managed_keys={"lan"}
        )
        assert result.deletes == []
        assert result.unmanaged == []


class TestServiceWrappers:
    def test_wrapper_forwards_managed_keys(self) -> None:
        service = vlan.VlanService.__new__(vlan.VlanService)
        result = service.compute_diff(
            [], [_live(("igb0", 10)), _live(("igb0", 20))], managed_keys={("igb0", 10)}
        )
        assert [d.diff_key for d in result.deletes] == [("igb0", 10)]
        assert [u.diff_key for u in result.unmanaged] == [("igb0", 20)]

    def test_assignment_wrapper_forwards_protected_keys(self) -> None:
        service = interface_assignment.InterfaceAssignmentService.__new__(
            interface_assignment.InterfaceAssignmentService
        )
        result = service.compute_diff([], [_live("lan")], managed_keys={"lan"})
        assert result.deletes == []
        assert [u.diff_key for u in result.unmanaged] == ["lan"]

    def test_host_alias_wrapper_forwards_managed_keys(self) -> None:
        service = unbound_host_alias.UnboundHostAliasService.__new__(
            unbound_host_alias.UnboundHostAliasService
        )
        result = service.compute_diff([], [_live(("u", "a"))], managed_keys=set())
        assert result.deletes == []
        assert len(result.unmanaged) == 1
