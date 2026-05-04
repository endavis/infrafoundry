"""Unbound forward validation for OPNsense (ADR-0014, #724).

Plan-time validation for the ``unbound_forward`` resource type. The
validator is deliberately split from the service-side
``unbound_forward_configs_from_resources`` parser: the parser raises on
hard schema violations (missing required fields, non-bool booleans,
invalid ``type``), while the validator surfaces softer field-shape
issues (malformed IP, out-of-range port) and uniqueness issues
(duplicate ``(type, domain, server, port)`` tuples within YAML) as
``ValidationReport`` entries.

Field rules:

- ``type``: ``forward`` (default) or ``dot``. The parser already rejects
  invalid values; the validator double-checks defensively for cases
  where the parser was bypassed.
- ``domain``: optional. Empty = global forwarder.
- ``server``: required, must parse as IPv4 or IPv6.
- ``port``: optional, must be in range 1-65535. Default 53.
- ``verify``: optional string (informational; only meaningful when
  ``type=dot``).
- ``forward_tcp_upstream``, ``forward_first``, ``enabled``, ``lock``:
  must be booleans.
- ``description``: optional string.
"""

from __future__ import annotations

import ipaddress

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

# Allowed values for the ``type`` discriminator (defensive; the parser
# already gates this).
_ALLOWED_TYPES: tuple[str, ...] = ("forward", "dot")


class UnboundForwardValidator:
    """Validates OPNsense Unbound forward resources."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def validate(self, forwards: list[ResourceConfig]) -> None:
        """Validate Unbound forward resources.

        Args:
            forwards: ``unbound_forward`` ``ResourceConfig`` entries.
        """
        seen_keys: dict[tuple[str, str, str, str], str] = {}
        for forward in forwards:
            self._validate_one(forward, seen_keys=seen_keys)

    def _validate_one(
        self,
        forward: ResourceConfig,
        *,
        seen_keys: dict[tuple[str, str, str, str], str],
    ) -> None:
        """Run all checks for a single forward entry."""
        forward_type = self._validate_type(forward)
        domain = self._validate_domain(forward)
        server = self._validate_server(forward)
        port = self._validate_port(forward)
        self._validate_verify(forward)
        self._validate_bool(forward, "forward_tcp_upstream")
        self._validate_bool(forward, "forward_first")
        self._validate_bool(forward, "enabled")
        self._validate_bool(forward, "lock")
        self._validate_description(forward)

        if (
            forward_type is not None
            and domain is not None
            and server is not None
            and port is not None
        ):
            self._validate_uniqueness(forward, forward_type, domain, server, port, seen_keys)

    # ------------------------------------------------------------------
    # type
    # ------------------------------------------------------------------

    def _validate_type(self, forward: ResourceConfig) -> str | None:
        """Validate the ``type`` field. Returns the value or default ``forward``."""
        if "type" not in forward.config:
            return "forward"
        value = forward.config["type"]
        if not isinstance(value, str) or value not in _ALLOWED_TYPES:
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_type",
                passed=False,
                message=(
                    f"unbound_forward '{forward.name}' type {value!r} must be one of "
                    f"{_ALLOWED_TYPES}"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        return value

    # ------------------------------------------------------------------
    # domain (optional)
    # ------------------------------------------------------------------

    def _validate_domain(self, forward: ResourceConfig) -> str | None:
        """Validate the ``domain`` field. Empty allowed (global forwarder)."""
        if "domain" not in forward.config:
            return ""
        value = forward.config["domain"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_domain",
                passed=False,
                message=(
                    f"unbound_forward '{forward.name}' domain must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        return value

    # ------------------------------------------------------------------
    # server (required, IP)
    # ------------------------------------------------------------------

    def _validate_server(self, forward: ResourceConfig) -> str | None:
        """Validate the ``server`` field is a valid IP. Returns the value or None."""
        server = forward.config.get("server")
        if server is None:
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_server",
                passed=False,
                message=(f"unbound_forward '{forward.name}' missing required field 'server'"),
                level=ValidationLevel.ERROR,
            )
            return None
        if not isinstance(server, str) or not server:
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_server",
                passed=False,
                message=(f"unbound_forward '{forward.name}' server must be a non-empty string"),
                level=ValidationLevel.ERROR,
            )
            return None
        try:
            ipaddress.ip_address(server)
        except ValueError:
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_server",
                passed=False,
                message=(
                    f"unbound_forward '{forward.name}' server {server!r} is not a "
                    f"valid IPv4 or IPv6 address"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        return server

    # ------------------------------------------------------------------
    # port (optional, 1-65535)
    # ------------------------------------------------------------------

    def _validate_port(self, forward: ResourceConfig) -> str | None:
        """Validate the ``port`` field. Default 53 when absent."""
        if "port" not in forward.config:
            return "53"
        value = forward.config["port"]
        # Accept int or string-of-digits; always normalize to string.
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_port",
                passed=False,
                message=(
                    f"unbound_forward '{forward.name}' port must be an integer or string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        try:
            port_int = int(value)
        except (TypeError, ValueError):
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_port",
                passed=False,
                message=(f"unbound_forward '{forward.name}' port {value!r} is not a valid integer"),
                level=ValidationLevel.ERROR,
            )
            return None
        if not 1 <= port_int <= 65535:
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_port",
                passed=False,
                message=(
                    f"unbound_forward '{forward.name}' port {port_int} is out of range 1-65535"
                ),
                level=ValidationLevel.ERROR,
            )
            return None
        return str(port_int)

    # ------------------------------------------------------------------
    # verify (optional)
    # ------------------------------------------------------------------

    def _validate_verify(self, forward: ResourceConfig) -> None:
        if "verify" not in forward.config:
            return
        value = forward.config["verify"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_verify",
                passed=False,
                message=(
                    f"unbound_forward '{forward.name}' verify must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # uniqueness
    # ------------------------------------------------------------------

    def _validate_uniqueness(
        self,
        forward: ResourceConfig,
        forward_type: str,
        domain: str,
        server: str,
        port: str,
        seen_keys: dict[tuple[str, str, str, str], str],
    ) -> None:
        """Reject two YAML entries with the same ``(type, domain, server, port)`` tuple."""
        key = (forward_type, domain, server, port)
        prior = seen_keys.get(key)
        if prior is not None:
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_uniqueness",
                passed=False,
                message=(
                    f"unbound_forward '{forward.name}' duplicates the "
                    f"(type, domain, server, port) tuple of '{prior}': {key}"
                ),
                level=ValidationLevel.ERROR,
            )
            return
        seen_keys[key] = forward.name

    # ------------------------------------------------------------------
    # bool fields
    # ------------------------------------------------------------------

    def _validate_bool(self, forward: ResourceConfig, field_name: str) -> None:
        if field_name not in forward.config:
            return
        value = forward.config[field_name]
        if not isinstance(value, bool):
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_{field_name}",
                passed=False,
                message=(
                    f"unbound_forward '{forward.name}' {field_name} must be a "
                    f"boolean (true/false), got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )

    # ------------------------------------------------------------------
    # description
    # ------------------------------------------------------------------

    def _validate_description(self, forward: ResourceConfig) -> None:
        if "description" not in forward.config:
            return
        value = forward.config["description"]
        if not isinstance(value, str):
            self.report.add_check(
                check_name=f"unbound_forward_{forward.name}_description",
                passed=False,
                message=(
                    f"unbound_forward '{forward.name}' description must be a string, "
                    f"got {type(value).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
