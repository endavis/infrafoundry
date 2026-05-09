"""Virtual-IP validation for OPNsense (ADR-0014, #723).

Plan-time validation for the ``virtual_ips`` resource type. The
validator is deliberately split from the service-side parser
(``virtual_ip_configs_from_resources``): the parser raises on hard
schema violations (missing required fields, bad ``mode`` value, non-
bool booleans), while the validator surfaces softer cross-resource
reference issues (unknown interface, unknown gateway) and field-shape
problems (malformed IP, out-of-range CIDR mask) as
``ValidationReport`` entries.

Discriminator pattern (mirrors ``nat_rule_validator``): ``_validate_one``
calls ``_validate_mode`` then branches on the result for CARP-required
fields (``password``, ``vhid``), ipalias-only fields (``gateway``,
``noexpand``, ``nobind``), and proxyarp (no extra fields).

Secret URIs:

- ``password`` accepts a ``secret://...`` URI as a valid value at plan
  time without resolving — secret resolution is an apply-time concern
  handled by the component manager. The validator only rejects empty /
  missing passwords for CARP mode and surfaces plaintext passwords
  with a soft warning so operators don't accidentally commit secrets
  to YAML.

Identity uniqueness:

- The natural-key tuple ``(interface, mode, address, vhid)`` must be
  unique across YAML entries. Two CARP VIPs at the same
  interface+address are valid only if they carry different vhids.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.opnsense.validators._xref import XRefIndex, resolve_xref

# Cross-reference target type for the virtual-IP `interface` field.
_MANAGED_INTERFACE_TYPE = "interfaces.assignments"

# Allowed values for the ``mode`` discriminator. The issue body's draft
# was wrong; the live probe is authoritative.
_ALLOWED_MODES: tuple[str, ...] = ("ipalias", "carp", "proxyarp")

# vhid range per RFC 5798 — VRRP, which CARP shadows on the wire.
_VHID_MIN = 1
_VHID_MAX = 255

# Match a `secret://...` URI. The validator does NOT resolve at plan
# time; it only confirms the shape so a plaintext password isn't
# silently accepted as a "secret reference".
_SECRET_URI = re.compile(r"^secret://[^/]+/.+$")


class VirtualIPValidator:
    """Validates OPNsense virtual-IP resources against managed + live state."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(
        self,
        virtual_ips: list[ResourceConfig],
        managed_interface_names: set[str],
        existing_interfaces: dict[str, Any],
        index: XRefIndex | None = None,
    ) -> None:
        """Validate virtual-IP resources.

        Args:
            virtual_ips: ``virtual_ips`` ``ResourceConfig`` entries.
            managed_interface_names: Set of managed
                ``interface_assignments`` resource names declared in
                YAML.
            existing_interfaces: Live interface map from
                ``OPNsenseValidator._get_existing_interfaces``.
            index: Optional dotted-type cross-reference index (#793).
                When provided, the ``interface`` field accepts dotted-
                path forms in addition to bare names. ``None`` falls
                back to bare-name lookup only.
        """
        seen_keys: dict[tuple[str, str, str, str], str] = {}
        for vip in virtual_ips:
            self._validate_one(
                vip,
                managed_interface_names=managed_interface_names,
                existing_interfaces=existing_interfaces,
                seen_keys=seen_keys,
                index=index,
            )

    def _validate_one(
        self,
        vip: ResourceConfig,
        *,
        managed_interface_names: set[str],
        existing_interfaces: dict[str, Any],
        seen_keys: dict[tuple[str, str, str, str], str],
        index: XRefIndex | None,
    ) -> None:
        """Run all checks for a single virtual-IP entry."""
        mode = self._validate_mode(vip)
        interface = self._validate_interface(
            vip,
            managed_interface_names=managed_interface_names,
            existing_interfaces=existing_interfaces,
            index=index,
        )
        address = self._validate_address(vip)
        self._validate_network(vip, address)
        self._validate_description(vip)
        self._validate_bool(vip, "enabled")
        self._validate_bool(vip, "lock")

        vhid = ""
        if mode == "carp":
            vhid = self._validate_vhid(vip) or ""
            self._validate_password(vip)
            self._validate_string(vip, "advbase")
            self._validate_string(vip, "advskew")
            self._validate_optional_ip(vip, "peer", expected_family=4)
            self._validate_optional_ip(vip, "peer6", expected_family=6)
            self._validate_bool(vip, "nosync")
            self._reject_ipalias_only_fields(vip)
        elif mode == "ipalias":
            self._validate_string(vip, "gateway")
            self._validate_bool(vip, "noexpand")
            self._validate_bool(vip, "nobind")
            self._reject_carp_only_fields(vip)
        elif mode == "proxyarp":
            self._reject_carp_only_fields(vip)
            self._reject_ipalias_only_fields(vip)

        if mode is not None and interface is not None and address is not None:
            self._validate_uniqueness(vip, mode, interface, address, vhid, seen_keys)

    # ------------------------------------------------------------------
    # mode (discriminator)
    # ------------------------------------------------------------------

    def _validate_mode(self, vip: ResourceConfig) -> str | None:
        """Validate the ``mode`` discriminator. Returns the mode or None."""
        mode = vip.config.get("mode", "ipalias")
        if not isinstance(mode, str) or mode not in _ALLOWED_MODES:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_mode",
                passed=False,
                message=(f"virtual_ip '{vip.name}' mode {mode!r} must be one of {_ALLOWED_MODES}"),
                level=ValidationLevel.ERROR,
            )
            return None
        return mode

    # ------------------------------------------------------------------
    # interface (cross-ref into managed + live)
    # ------------------------------------------------------------------

    def _validate_interface(
        self,
        vip: ResourceConfig,
        *,
        managed_interface_names: set[str],
        existing_interfaces: dict[str, Any],
        index: XRefIndex | None,
    ) -> str | None:
        """Validate the ``interface`` cross-reference. Returns the value or None."""
        interface = vip.config.get("interface")
        if interface is None:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_interface",
                passed=False,
                message=f"virtual_ip '{vip.name}' missing required field 'interface'",
                level=ValidationLevel.ERROR,
            )
            return None
        if not isinstance(interface, str) or not interface:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_interface",
                passed=False,
                message=f"virtual_ip '{vip.name}' interface must be a non-empty string",
                level=ValidationLevel.ERROR,
            )
            return None

        # Dotted-form resolution (#793). The xref index always wins
        # when its lookup matches; otherwise fall through to bare-name
        # checks for backward compatibility with the flat schema.
        # ``current_plugin`` is the first segment of the referencing
        # vip's type (e.g. ``interfaces`` for ``interfaces.virtual_ips``).
        if index is not None and "." in interface:
            current_plugin = vip.type.split(".", 1)[0] if "." in vip.type else None
            resolved = resolve_xref(
                interface,
                expected_type=_MANAGED_INTERFACE_TYPE,
                index=index,
                current_plugin=current_plugin,
            )
            if resolved is not None:
                self.report.add_check(
                    check_name=f"virtual_ip_{vip.name}_interface",
                    passed=True,
                    message=(
                        f"Interface '{interface}' resolved (via dotted-path) to "
                        f"'{resolved.name}' for virtual_ip '{vip.name}'"
                    ),
                    level=ValidationLevel.INFO,
                )
                return resolved.name

        if interface in managed_interface_names or interface in existing_interfaces:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_interface",
                passed=True,
                message=f"Interface '{interface}' resolved for virtual_ip '{vip.name}'",
                level=ValidationLevel.INFO,
            )
            return interface
        self.report.add_check(
            check_name=f"virtual_ip_{vip.name}_interface",
            passed=False,
            message=(
                f"virtual_ip '{vip.name}' references unknown interface '{interface}'; "
                f"expected a managed interface_assignment name or a live OPNsense interface"
            ),
            level=ValidationLevel.ERROR,
        )
        return None

    # ------------------------------------------------------------------
    # address + network
    # ------------------------------------------------------------------

    def _validate_address(self, vip: ResourceConfig) -> str | None:
        """Validate the ``address`` field. Returns the parsed value or None."""
        address = vip.config.get("address")
        if address is None:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_address",
                passed=False,
                message=f"virtual_ip '{vip.name}' missing required field 'address'",
                level=ValidationLevel.ERROR,
            )
            return None
        if not isinstance(address, str) or not address:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_address",
                passed=False,
                message=f"virtual_ip '{vip.name}' address must be a non-empty string",
                level=ValidationLevel.ERROR,
            )
            return None
        try:
            ipaddress.ip_address(address)
        except ValueError as exc:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_address",
                passed=False,
                message=(f"virtual_ip '{vip.name}' address {address!r} is not a valid IP: {exc}"),
                level=ValidationLevel.ERROR,
            )
            return None
        return address

    def _validate_network(self, vip: ResourceConfig, address: str | None) -> None:
        """Validate the ``network`` (CIDR mask) field.

        Range depends on the address family: IPv4 → 1-32, IPv6 → 1-128.
        If ``address`` was rejected upstream we still validate the
        network's shape so the operator sees both errors.
        """
        network = vip.config.get("network")
        if network is None:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_network",
                passed=False,
                message=f"virtual_ip '{vip.name}' missing required field 'network'",
                level=ValidationLevel.ERROR,
            )
            return

        # Coerce — we accept str or int; the parser does the same.
        if isinstance(network, bool) or not isinstance(network, (str, int)):
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_network",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' network must be a string or integer, "
                    f"got {type(network).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        network_str = str(network)
        if not network_str:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_network",
                passed=False,
                message=f"virtual_ip '{vip.name}' network must be a non-empty CIDR mask",
                level=ValidationLevel.ERROR,
            )
            return

        try:
            mask = int(network_str)
        except ValueError:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_network",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' network {network_str!r} must be an integer "
                    f"CIDR mask (e.g. '24', '64')"
                ),
                level=ValidationLevel.ERROR,
            )
            return

        # If we have an address we know the family; otherwise accept
        # anything in 1..128 (the IPv6 ceiling).
        max_mask = 128
        if address is not None:
            try:
                family = ipaddress.ip_address(address).version
                max_mask = 32 if family == 4 else 128
            except ValueError:
                # Already reported on the address field; defensive only.
                pass

        if mask < 1 or mask > max_mask:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_network",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' network mask {mask} out of range "
                    f"(expected 1-{max_mask} for the address family)"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # CARP-only validators
    # ------------------------------------------------------------------

    def _validate_vhid(self, vip: ResourceConfig) -> str | None:
        """Validate CARP ``vhid`` (required, 1-255). Returns the value or None."""
        vhid_raw = vip.config.get("vhid")
        if vhid_raw is None or vhid_raw == "":
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_vhid",
                passed=False,
                message=f"virtual_ip '{vip.name}' (carp) requires 'vhid'",
                level=ValidationLevel.ERROR,
            )
            return None
        if isinstance(vhid_raw, bool) or not isinstance(vhid_raw, (str, int)):
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_vhid",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' vhid must be a string or integer, "
                    f"got {type(vhid_raw).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        vhid_str = str(vhid_raw)
        try:
            vhid_int = int(vhid_str)
        except ValueError:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_vhid",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' vhid {vhid_str!r} must be an integer "
                    f"({_VHID_MIN}-{_VHID_MAX})"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        if vhid_int < _VHID_MIN or vhid_int > _VHID_MAX:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_vhid",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' vhid {vhid_int} out of range "
                    f"({_VHID_MIN}-{_VHID_MAX})"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        return vhid_str

    def _validate_password(self, vip: ResourceConfig) -> None:
        """Validate CARP ``password``.

        Required and non-empty for CARP. ``secret://...`` URIs are
        accepted as a valid placeholder (resolution is an apply-time
        concern). Plaintext non-empty values are accepted but warned —
        operators should not commit secrets to YAML.
        """
        password = vip.config.get("password")
        if password is None or password == "":  # nosec B105
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_password",
                passed=False,
                message=f"virtual_ip '{vip.name}' (carp) requires non-empty 'password'",
                level=ValidationLevel.ERROR,
            )
            return
        if not isinstance(password, str):
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_password",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' password must be a string, "
                    f"got {type(password).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if _SECRET_URI.match(password):
            # Accepted; resolution happens at apply time in the manager.
            return
        # Plaintext password — accepted, but warn the operator.
        self.report.add_check(
            check_name=f"virtual_ip_{vip.name}_password",
            passed=False,
            message=(
                f"virtual_ip '{vip.name}' password is a plaintext string; consider using "
                f"a 'secret://env_secrets/<path>' URI instead so the secret is sourced "
                f"from the encrypted env secrets file"
            ),
            level=ValidationLevel.WARNING,
        )

    def _validate_optional_ip(
        self, vip: ResourceConfig, field_name: str, *, expected_family: int
    ) -> None:
        """Validate optional CARP unicast-peer IP.

        Empty / missing is accepted (default multicast). Non-empty values
        must parse as the expected IP family.
        """
        if field_name not in vip.config:
            return
        value = vip.config[field_name]
        if value == "":
            return
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_{field_name}",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' {field_name} must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError as exc:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_{field_name}",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' {field_name} {value!r} is not a valid IP: {exc}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        if parsed.version != expected_family:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_{field_name}",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' {field_name} {value!r} family does not match "
                    f"expected IPv{expected_family}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # Mode-mismatch field rejection
    # ------------------------------------------------------------------

    _CARP_ONLY_FIELDS = (
        "password",
        "vhid",
        "advbase",
        "advskew",
        "peer",
        "peer6",
        "nosync",
    )
    _IPALIAS_ONLY_FIELDS = ("gateway", "noexpand", "nobind")

    def _reject_carp_only_fields(self, vip: ResourceConfig) -> None:
        """Warn on CARP-only fields set when ``mode`` is not CARP.

        These fields are silently ignored on the wire by OPNsense for
        non-CARP modes; surfacing a warning helps operators catch the
        mistake at plan time.
        """
        for field_name in self._CARP_ONLY_FIELDS:
            if field_name not in vip.config:
                continue
            value = vip.config[field_name]
            if value in ("", False, None):
                continue
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_{field_name}_mode_mismatch",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' field '{field_name}' is only applicable to "
                    f"mode=carp; will be ignored at apply time"
                ),
                level=ValidationLevel.WARNING,
            )

    def _reject_ipalias_only_fields(self, vip: ResourceConfig) -> None:
        """Warn on ipalias-only fields set when ``mode`` is not ipalias."""
        for field_name in self._IPALIAS_ONLY_FIELDS:
            if field_name not in vip.config:
                continue
            value = vip.config[field_name]
            if value in ("", False, None):
                continue
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_{field_name}_mode_mismatch",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' field '{field_name}' is only applicable to "
                    f"mode=ipalias; will be ignored at apply time"
                ),
                level=ValidationLevel.WARNING,
            )

    # ------------------------------------------------------------------
    # Field type checks
    # ------------------------------------------------------------------

    def _validate_string(self, vip: ResourceConfig, field_name: str) -> None:
        if field_name not in vip.config:
            return
        value = vip.config[field_name]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_{field_name}",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' {field_name} must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_bool(self, vip: ResourceConfig, field_name: str) -> None:
        if field_name not in vip.config:
            return
        value = vip.config[field_name]
        if not isinstance(value, bool):
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_{field_name}",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' {field_name} must be a boolean (true/false), "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    def _validate_description(self, vip: ResourceConfig) -> None:
        if "description" not in vip.config:
            return
        value = vip.config["description"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_description",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' description must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # Uniqueness
    # ------------------------------------------------------------------

    def _validate_uniqueness(
        self,
        vip: ResourceConfig,
        mode: str,
        interface: str,
        address: str,
        vhid: str,
        seen_keys: dict[tuple[str, str, str, str], str],
    ) -> None:
        """Reject duplicates of the natural-key tuple within a single YAML batch."""
        key = (interface, mode, address, vhid)
        existing = seen_keys.get(key)
        if existing is not None:
            self.report.add_check(
                check_name=f"virtual_ip_{vip.name}_uniqueness",
                passed=False,
                message=(
                    f"virtual_ip '{vip.name}' duplicates the (interface, mode, address, vhid) "
                    f"tuple of '{existing}': ({interface}, {mode}, {address}, {vhid!r})"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        seen_keys[key] = vip.name
