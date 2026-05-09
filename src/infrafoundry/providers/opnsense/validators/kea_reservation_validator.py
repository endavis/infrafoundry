"""Kea reservation validation for OPNsense (#802).

Plan-time validation for the ``kea.dhcp4.reservations`` and
``kea.dhcp6.reservations`` resource types — specifically their
``subnet_ref`` / ``subnet`` cross-reference fields. The validator is
deliberately split from the component-side ``_resolve_subnet_uuid``
resolution: the component layer translates a CIDR to a live OPNsense
UUID at apply time (the canonical single source of truth), while this
validator surfaces softer cross-resource reference issues at plan time
so operators get clean errors before any API call.

Field acceptance precedence (matches the component layer for v4 and v6):

1. ``subnet_ref`` present → resolve via the cross-reference index
   against ``kea.dhcp4.subnets`` (for v4) or ``kea.dhcp6.subnets``
   (for v6); error if no managed subnet matches.
2. Only ``subnet`` present → must be a literal CIDR of the right
   IP family; this is the legacy form (DHCPv6 fixtures still use it).
3. Both present and agree (resolved subnet's CIDR matches the literal
   ``subnet``) → pass.
4. Both present and disagree → error.
5. Neither present → error.

Cross-reference syntax (per ADR-0016 / shared resolver in
``_xref.resolve_xref``):

- bare name (e.g., ``lan-dhcp``) — looked up in
  ``kea.dhcp4.subnets`` / ``kea.dhcp6.subnets`` according to the
  reservation's wire family.
- in-plugin relative (e.g., ``dhcp4.subnets.lan-dhcp`` for a
  reservation declared under the ``kea`` plugin) — resolved with
  ``current_plugin="kea"``.
- cross-plugin absolute (e.g.,
  ``kea.dhcp4.subnets.lan-dhcp``) — resolved directly.

Error categories surfaced (one ``ValidationLevel.ERROR`` ``add_check``
entry per category, keyed by check name):

- ``kea_reservation_<name>_subnet`` — missing both fields, both-and-
  disagree, unknown ``subnet_ref``, wrong-version cross (v4 reservation
  pointing at a v6 subnet or v6 reservation pointing at a v4 subnet),
  malformed literal ``subnet`` CIDR, wrong family for the literal
  ``subnet``.
"""

from __future__ import annotations

import ipaddress

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators._xref import XRefIndex, resolve_xref

# Dotted target types for the v4/v6 subnet xref lookups. Pulled out as
# constants so the resolver call and the wrong-version detection logic
# agree on the canonical type strings.
_MANAGED_DHCP4_SUBNET_TYPE = "kea.dhcp4.subnets"
_MANAGED_DHCP6_SUBNET_TYPE = "kea.dhcp6.subnets"


class KeaReservationValidator:
    """Validates OPNsense Kea reservation ``subnet_ref`` / ``subnet`` fields.

    Covers both ``kea.dhcp4.reservations`` and ``kea.dhcp6.reservations``
    in a single ``validate(...)`` call so the v4/v6 wrong-version cross
    detection has both subnet name sets at hand without the caller
    having to invoke the validator twice.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(
        self,
        dhcp4_reservations: list[ResourceConfig],
        dhcp6_reservations: list[ResourceConfig],
        dhcp4_subnet_names: set[str],
        dhcp6_subnet_names: set[str],
        index: XRefIndex | None = None,
    ) -> None:
        """Validate Kea reservation resources for both v4 and v6.

        Args:
            dhcp4_reservations: ``kea.dhcp4.reservations`` ``ResourceConfig`` entries.
            dhcp6_reservations: ``kea.dhcp6.reservations`` ``ResourceConfig`` entries.
            dhcp4_subnet_names: Set of managed v4 subnet names declared in YAML.
            dhcp6_subnet_names: Set of managed v6 subnet names declared in YAML.
            index: Dotted-type cross-reference index (#793). Required for
                ``subnet_ref`` resolution; ``None`` causes ``subnet_ref``
                lookups to fall back to bare-name set lookups against
                ``dhcp4_subnet_names`` / ``dhcp6_subnet_names``.
        """
        for reservation in dhcp4_reservations:
            self._validate_one(
                reservation,
                wire_family="v4",
                managed_subnet_names=dhcp4_subnet_names,
                wrong_version_subnet_names=dhcp6_subnet_names,
                expected_subnet_type=_MANAGED_DHCP4_SUBNET_TYPE,
                wrong_version_subnet_type=_MANAGED_DHCP6_SUBNET_TYPE,
                index=index,
            )
        for reservation in dhcp6_reservations:
            self._validate_one(
                reservation,
                wire_family="v6",
                managed_subnet_names=dhcp6_subnet_names,
                wrong_version_subnet_names=dhcp4_subnet_names,
                expected_subnet_type=_MANAGED_DHCP6_SUBNET_TYPE,
                wrong_version_subnet_type=_MANAGED_DHCP4_SUBNET_TYPE,
                index=index,
            )

    # ------------------------------------------------------------------
    # Per-reservation
    # ------------------------------------------------------------------

    def _validate_one(
        self,
        reservation: ResourceConfig,
        *,
        wire_family: str,
        managed_subnet_names: set[str],
        wrong_version_subnet_names: set[str],
        expected_subnet_type: str,
        wrong_version_subnet_type: str,
        index: XRefIndex | None,
    ) -> None:
        """Run all checks for a single reservation.

        Args:
            reservation: The ``kea.dhcp{4,6}.reservations`` resource.
            wire_family: ``"v4"`` or ``"v6"``; used in error messages.
            managed_subnet_names: Managed subnet names of the matching
                wire family (the *expected* targets).
            wrong_version_subnet_names: Managed subnet names of the
                opposite family (used to detect wrong-version cross
                refs and emit a clearer error than "unknown subnet").
            expected_subnet_type: Dotted type string for the matching
                wire family (e.g., ``kea.dhcp4.subnets``). Passed to
                ``resolve_xref``.
            wrong_version_subnet_type: Dotted type string for the
                opposite wire family. Used to detect when an operator
                wrote a fully-qualified path pointing at the wrong
                family.
            index: Dotted-type cross-reference index (#793).
        """
        check_name = f"kea_reservation_{reservation.name}_subnet"
        config = reservation.config
        subnet_ref = config.get("subnet_ref")
        subnet_literal = config.get("subnet")

        # 1. Neither field present.
        if subnet_ref is None and subnet_literal is None:
            self.report.add_check(
                check_name=check_name,
                passed=False,
                message=(
                    f"kea_{wire_family}_reservation '{reservation.name}' "
                    f"missing required field; expected one of "
                    f"'subnet_ref' (preferred) or 'subnet' (legacy CIDR)"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        # 2. subnet_ref provided — try to resolve it.
        resolved_cidr: str | None = None
        if subnet_ref is not None:
            resolved_cidr = self._resolve_subnet_ref(
                reservation,
                subnet_ref=subnet_ref,
                wire_family=wire_family,
                managed_subnet_names=managed_subnet_names,
                wrong_version_subnet_names=wrong_version_subnet_names,
                expected_subnet_type=expected_subnet_type,
                wrong_version_subnet_type=wrong_version_subnet_type,
                index=index,
                check_name=check_name,
            )
            if resolved_cidr is None:
                # An ERROR was already added by ``_resolve_subnet_ref``.
                return

        # 3. subnet literal provided — validate as CIDR of the right family.
        literal_cidr: str | None = None
        if subnet_literal is not None:
            literal_cidr = self._validate_literal_subnet(
                reservation,
                subnet_literal=subnet_literal,
                wire_family=wire_family,
                check_name=check_name,
            )
            if literal_cidr is None:
                # An ERROR was already added by ``_validate_literal_subnet``.
                return

        # 4. Both fields present — must agree on the CIDR.
        if resolved_cidr is not None and literal_cidr is not None and resolved_cidr != literal_cidr:
            self.report.add_check(
                check_name=check_name,
                passed=False,
                message=(
                    f"kea_{wire_family}_reservation '{reservation.name}' "
                    f"has conflicting subnet fields: subnet_ref={subnet_ref!r} "
                    f"resolves to {resolved_cidr!r}, but subnet={literal_cidr!r}"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        # 5. All checks passed — record a single passing entry so the
        # report shows positive coverage of this field group.
        target = resolved_cidr if resolved_cidr is not None else literal_cidr
        self.report.add_check(
            check_name=check_name,
            passed=True,
            message=(
                f"Subnet reference resolved to {target!r} for "
                f"kea_{wire_family}_reservation '{reservation.name}'"
            ),
            level=ValidationLevel.INFO,
        )

    # ------------------------------------------------------------------
    # subnet_ref (cross-ref)
    # ------------------------------------------------------------------

    def _resolve_subnet_ref(
        self,
        reservation: ResourceConfig,
        *,
        subnet_ref: object,
        wire_family: str,
        managed_subnet_names: set[str],
        wrong_version_subnet_names: set[str],
        expected_subnet_type: str,
        wrong_version_subnet_type: str,
        index: XRefIndex | None,
        check_name: str,
    ) -> str | None:
        """Resolve a ``subnet_ref`` value to a managed subnet's CIDR.

        Returns the resolved CIDR string on success, or ``None`` (after
        adding an ERROR check) on any failure path. The caller propagates
        ``None`` to the parent ``_validate_one`` so it skips the both-
        agree and pass-through branches.
        """
        if not isinstance(subnet_ref, str) or not subnet_ref:
            self.report.add_check(
                check_name=check_name,
                passed=False,
                message=(
                    f"kea_{wire_family}_reservation '{reservation.name}' "
                    f"subnet_ref must be a non-empty string"
                ),
                level=ValidationLevel.ERROR,
            )
            return None

        # Dotted-form resolution (#793). When the index is supplied we
        # try the resolver first; if it hits we read the resolved
        # resource's CIDR directly. We also detect the wrong-version
        # cross case (e.g., a v4 reservation referencing a v6 subnet)
        # by looking at the resolved resource's type before deciding
        # the lookup is a "miss".
        resolved_resource = None
        if index is not None and "." in subnet_ref:
            current_plugin = reservation.type.split(".", 1)[0] if "." in reservation.type else None
            resolved_resource = resolve_xref(
                subnet_ref,
                expected_type=expected_subnet_type,
                index=index,
                current_plugin=current_plugin,
            )
            # Wrong-version cross — the operator wrote a fully-qualified
            # path that resolves into the *opposite* family.
            if resolved_resource is None:
                wrong_version_resolved = resolve_xref(
                    subnet_ref,
                    expected_type=wrong_version_subnet_type,
                    index=index,
                    current_plugin=current_plugin,
                )
                if wrong_version_resolved is not None:
                    self.report.add_check(
                        check_name=check_name,
                        passed=False,
                        message=(
                            f"kea_{wire_family}_reservation '{reservation.name}' "
                            f"subnet_ref {subnet_ref!r} points at a "
                            f"{wrong_version_resolved.type!r} subnet; "
                            f"expected a {expected_subnet_type!r} subnet"
                        ),
                        level=ValidationLevel.ERROR,
                    )
                    return None
        elif index is not None:
            # Bare name + index supplied — also use the resolver so we
            # can detect wrong-version cross when the bare name happens
            # to exist only in the opposite family.
            resolved_resource = resolve_xref(
                subnet_ref,
                expected_type=expected_subnet_type,
                index=index,
                current_plugin=None,
            )
            if resolved_resource is None and subnet_ref in wrong_version_subnet_names:
                self.report.add_check(
                    check_name=check_name,
                    passed=False,
                    message=(
                        f"kea_{wire_family}_reservation '{reservation.name}' "
                        f"subnet_ref {subnet_ref!r} points at a "
                        f"{wrong_version_subnet_type!r} subnet; "
                        f"expected a {expected_subnet_type!r} subnet"
                    ),
                    level=ValidationLevel.ERROR,
                )
                return None

        if resolved_resource is not None:
            cidr = resolved_resource.config.get("subnet")
            if not isinstance(cidr, str) or not cidr:
                # The managed subnet itself is missing/malformed; that
                # is an error in the *subnet* resource, not the
                # reservation. Surface it here too so the operator sees
                # the chain that broke.
                self.report.add_check(
                    check_name=check_name,
                    passed=False,
                    message=(
                        f"kea_{wire_family}_reservation '{reservation.name}' "
                        f"subnet_ref {subnet_ref!r} resolved to managed "
                        f"subnet {resolved_resource.name!r}, but that "
                        f"subnet is missing a 'subnet' CIDR field"
                    ),
                    level=ValidationLevel.ERROR,
                )
                return None
            return cidr

        # Fall back to bare-name set lookup (the pre-#793 path). When
        # the lookup hits we don't have the resolved CIDR — only the
        # name — which is sufficient to *clear* the unknown-ref check
        # but not enough to cross-validate against a literal ``subnet``
        # field. In that case we return the empty string sentinel and
        # the caller treats the both-agree check as pass-through.
        if subnet_ref in managed_subnet_names:
            return ""

        # Wrong-version cross (bare name without index supplied).
        if subnet_ref in wrong_version_subnet_names:
            self.report.add_check(
                check_name=check_name,
                passed=False,
                message=(
                    f"kea_{wire_family}_reservation '{reservation.name}' "
                    f"subnet_ref {subnet_ref!r} points at a "
                    f"{wrong_version_subnet_type!r} subnet; "
                    f"expected a {expected_subnet_type!r} subnet"
                ),
                level=ValidationLevel.ERROR,
            )
            return None

        # Unknown reference.
        self.report.add_check(
            check_name=check_name,
            passed=False,
            message=(
                f"kea_{wire_family}_reservation '{reservation.name}' "
                f"references unknown subnet_ref {subnet_ref!r}; "
                f"expected a managed {expected_subnet_type!r} resource name"
            ),
            level=ValidationLevel.ERROR,
        )
        return None

    # ------------------------------------------------------------------
    # subnet (literal CIDR)
    # ------------------------------------------------------------------

    def _validate_literal_subnet(
        self,
        reservation: ResourceConfig,
        *,
        subnet_literal: object,
        wire_family: str,
        check_name: str,
    ) -> str | None:
        """Validate a literal ``subnet`` CIDR is parseable and the right family.

        Returns the literal as a string on success (so the caller can do
        the both-agree comparison), or ``None`` (after adding an ERROR
        check) on any failure.
        """
        if not isinstance(subnet_literal, str) or not subnet_literal:
            self.report.add_check(
                check_name=check_name,
                passed=False,
                message=(
                    f"kea_{wire_family}_reservation '{reservation.name}' "
                    f"subnet must be a non-empty string"
                ),
                level=ValidationLevel.ERROR,
            )
            return None

        try:
            # ``strict=False`` because reservations conventionally write
            # the network's CIDR (host bits zero) but a tolerant parse
            # keeps us aligned with the component-side string compare.
            network = ipaddress.ip_network(subnet_literal, strict=False)
        except ValueError as exc:
            self.report.add_check(
                check_name=check_name,
                passed=False,
                message=(
                    f"kea_{wire_family}_reservation '{reservation.name}' "
                    f"subnet {subnet_literal!r} is not a valid CIDR: {exc}"
                ),
                level=ValidationLevel.ERROR,
            )
            return None

        is_v4 = isinstance(network, ipaddress.IPv4Network)
        wants_v4 = wire_family == "v4"
        if is_v4 != wants_v4:
            actual = "IPv4" if is_v4 else "IPv6"
            expected = "IPv4" if wants_v4 else "IPv6"
            self.report.add_check(
                check_name=check_name,
                passed=False,
                message=(
                    f"kea_{wire_family}_reservation '{reservation.name}' "
                    f"subnet {subnet_literal!r} is {actual}, but the "
                    f"reservation's wire family expects {expected}"
                ),
                level=ValidationLevel.ERROR,
            )
            return None

        return subnet_literal
