"""Unit tests for OCI compartment reference helpers."""

from __future__ import annotations

import pytest

from infrafoundry.core.exceptions import ConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.oci.compartments import (
    compartment_id_expr,
    find_parent_cycles,
    is_ocid,
    parent_id_expr,
)

OCID = "ocid1.compartment.oc1..aaaaaaaexample"


def _comp(name: str, parent: str | None = None) -> ResourceConfig:
    config: dict[str, str] = {"description": "d"}
    if parent is not None:
        config["parent"] = parent
    return ResourceConfig(name=name, type="compartment", provider="oci", config=config)


def test_is_ocid() -> None:
    """Only strings starting with ``ocid1.`` are OCIDs."""
    assert is_ocid(OCID)
    assert not is_ocid("workload-comp")
    assert not is_ocid("")


class TestCompartmentIdExpr:
    """Tests for compartment_id_expr."""

    @pytest.mark.parametrize("ref", [None, ""])
    def test_default(self, ref: str | None) -> None:
        """No reference falls back to the provider setting variable."""
        assert compartment_id_expr(ref, {"workload-comp"}) == "var.oci_compartment_ocid"

    def test_ocid_is_quoted_literal(self) -> None:
        """An OCID renders as a quoted literal."""
        assert compartment_id_expr(OCID, set()) == f'"{OCID}"'

    def test_name_is_resource_reference(self) -> None:
        """A known name renders as a resource reference with hyphens replaced."""
        expr = compartment_id_expr("workload-comp", {"workload-comp"})
        assert expr == "oci_identity_compartment.workload_comp.id"

    def test_unknown_name_raises(self) -> None:
        """An unknown name raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="missing-comp"):
            compartment_id_expr("missing-comp", {"workload-comp"})


class TestParentIdExpr:
    """Tests for parent_id_expr."""

    def test_default_is_tenancy(self) -> None:
        """No parent falls back to the tenancy."""
        assert parent_id_expr(None, set()) == "var.oci_tenancy_ocid"

    def test_ocid(self) -> None:
        """An OCID parent is a quoted literal."""
        assert parent_id_expr(OCID, set()) == f'"{OCID}"'

    def test_name(self) -> None:
        """A known parent name is a resource reference."""
        assert parent_id_expr("a-b", {"a-b"}) == "oci_identity_compartment.a_b.id"

    def test_unknown_name_raises(self) -> None:
        """An unknown parent name raises."""
        with pytest.raises(ConfigurationError, match="parent"):
            parent_id_expr("nope", set())


class TestFindParentCycles:
    """Tests for find_parent_cycles."""

    def test_none(self) -> None:
        """A plain chain has no cycle."""
        assert find_parent_cycles([_comp("a"), _comp("b", "a")]) == set()

    def test_self_parent(self) -> None:
        """A compartment that is its own parent is a cycle."""
        assert find_parent_cycles([_comp("a", "a")]) == {"a"}

    def test_two_node_cycle(self) -> None:
        """A two-node cycle reports both nodes."""
        assert find_parent_cycles([_comp("a", "b"), _comp("b", "a")]) == {"a", "b"}

    def test_three_node_cycle_with_tail(self) -> None:
        """A tail leading into a cycle is not itself on the cycle."""
        comps = [_comp("a", "b"), _comp("b", "c"), _comp("c", "a"), _comp("d", "a")]
        assert find_parent_cycles(comps) == {"a", "b", "c"}

    def test_chain_ending_in_ocid(self) -> None:
        """A chain ending in an OCID is not a cycle."""
        assert find_parent_cycles([_comp("a", OCID), _comp("b", "a")]) == set()

    def test_unknown_parent(self) -> None:
        """An unknown parent ends the chain."""
        assert find_parent_cycles([_comp("a", "ghost")]) == set()
