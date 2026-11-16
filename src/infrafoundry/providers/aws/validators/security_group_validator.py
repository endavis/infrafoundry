"""Security group validation for the AWS provider."""

from __future__ import annotations

from typing import Any, override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationReport

from ._common import RULE_NAME_RE, fail, parse_cidr
from .context import AWSConfigContext

_NAMED_PROTOCOLS = frozenset({"tcp", "udp", "icmp", "icmpv6", "-1"})
_PORT_PROTOCOLS = frozenset({"tcp", "udp"})
_ICMP_PROTOCOLS = frozenset({"icmp", "icmpv6"})


def _valid_protocol(value: Any) -> bool:
    """Return True for a protocol name or a number 0-255."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 <= value <= 255
    if not isinstance(value, str):
        return False
    return value in _NAMED_PROTOCOLS or (value.isdigit() and int(value) <= 255)


def _valid_port(value: Any, protocol: str) -> bool:
    """Return True for an integer 0-65535, or -1 (any type or code) for ICMP."""
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return 0 <= value <= 65535 or (value == -1 and protocol in _ICMP_PROTOCOLS)


class SecurityGroupValidator(SpecializedValidator[AWSConfigContext]):
    """Checks ``security_group`` resources and their rules."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: AWSConfigContext) -> None:
        """Check every ``security_group`` resource.

        Args:
            context: Resources to check.
        """
        for resource in context.resources:
            if resource.type != "security_group":
                continue
            config = resource.config
            if not config.get("vpc_id"):
                fail(
                    self.report,
                    f"aws_sg_{resource.name}_vpc_id",
                    f"security_group '{resource.name}': vpc_id is required",
                )
            for direction in ("ingress", "egress"):
                rules = config.get(direction)
                if rules is None:
                    continue
                if not isinstance(rules, list):
                    fail(
                        self.report,
                        f"aws_sg_{resource.name}_{direction}",
                        f"security_group '{resource.name}': {direction} must be a list",
                    )
                    continue
                self._check_rules(resource.name, direction, rules)

    def _check_rules(self, group: str, direction: str, rules: list[Any]) -> None:
        """Validate the rules of one direction of one group."""
        seen: set[str] = set()
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                fail(
                    self.report,
                    f"aws_sg_{group}_{direction}_{index}",
                    f"security_group '{group}': each {direction} rule must be a mapping",
                )
                continue
            label = str(rule.get("name", index))
            check = f"aws_sg_{group}_{direction}_{label}"
            name = rule.get("name")
            if not isinstance(name, str) or not RULE_NAME_RE.match(name):
                fail(
                    self.report,
                    check,
                    f"security_group '{group}': {direction} rule {index} needs a 'name' "
                    "of letters, digits, '_' and '-'",
                )
            elif name in seen:
                fail(
                    self.report,
                    check,
                    f"security_group '{group}': duplicate {direction} rule name '{name}'",
                )
            else:
                seen.add(name)
            self._check_cidr(check, group, rule)
            self._check_protocol_and_ports(check, group, rule)

    def _check_cidr(self, check: str, group: str, rule: dict[str, Any]) -> None:
        """Require exactly one valid CIDR of the matching family."""
        v4 = rule.get("cidr_ipv4")
        v6 = rule.get("cidr_ipv6")
        if (v4 is None) == (v6 is None):
            fail(
                self.report,
                f"{check}_cidr",
                f"security_group '{group}': a rule needs exactly one of cidr_ipv4 or cidr_ipv6",
            )
            return
        error = parse_cidr(v4, 4) if v4 is not None else parse_cidr(v6, 6)
        if error:
            key = "cidr_ipv4" if v4 is not None else "cidr_ipv6"
            fail(self.report, f"{check}_cidr", f"security_group '{group}': {key} {error}")

    def _check_protocol_and_ports(self, check: str, group: str, rule: dict[str, Any]) -> None:
        """Validate ip_protocol, from_port and to_port."""
        protocol = rule.get("ip_protocol")
        if not _valid_protocol(protocol):
            fail(
                self.report,
                f"{check}_protocol",
                f"security_group '{group}': ip_protocol must be tcp, udp, icmp, icmpv6, -1 "
                f"or a protocol number, got {protocol!r}",
            )
            return
        from_port = rule.get("from_port")
        to_port = rule.get("to_port")
        if str(protocol) in _PORT_PROTOCOLS and (from_port is None or to_port is None):
            fail(
                self.report,
                f"{check}_ports",
                f"security_group '{group}': from_port and to_port are required for {protocol}",
            )
            return
        for key, value in (("from_port", from_port), ("to_port", to_port)):
            if value is not None and not _valid_port(value, str(protocol)):
                fail(
                    self.report,
                    f"{check}_ports",
                    f"security_group '{group}': {key} must be an integer 0-65535 "
                    f"(-1 for ICMP), got {value!r}",
                )
                return
        if from_port is not None and to_port is not None and from_port > to_port:
            fail(
                self.report,
                f"{check}_ports",
                f"security_group '{group}': from_port {from_port} is greater than to_port "
                f"{to_port}",
            )
