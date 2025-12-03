"""Firewall rule validation for OPNsense."""

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class FirewallValidator:
    """Validates OPNsense firewall rule alias references."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize firewall validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(
        self,
        firewall_rules: list[ResourceConfig],
        alias_names: set[str],
        existing_aliases: dict[str, Any],
    ) -> None:
        """Validate firewall rules reference valid aliases.

        Args:
            firewall_rules: List of firewall rule resources
            alias_names: Set of alias names in the configuration
            existing_aliases: Existing aliases from API
        """
        for rule in firewall_rules:
            rule_config = rule.config or {}
            source_alias = rule_config.get("source", {}).get("alias")
            dest_alias = rule_config.get("destination", {}).get("alias")

            # Check source alias
            if source_alias:
                # Check if it's in our config or exists in OPNsense
                if source_alias not in alias_names and source_alias not in existing_aliases:
                    self.report.add_check(
                        check_name=f"firewall_rule_{rule.name}_source_alias",
                        passed=False,
                        message=(
                            f"Firewall rule '{rule.name}' references "
                            f"undefined source alias '{source_alias}'"
                        ),
                        level=ValidationLevel.ERROR,
                    )
                else:
                    self.report.add_check(
                        check_name=f"firewall_rule_{rule.name}_source_alias",
                        passed=True,
                        message=f"Source alias '{source_alias}' found for rule '{rule.name}'",
                        level=ValidationLevel.INFO,
                    )

            # Check destination alias
            if dest_alias:
                if dest_alias not in alias_names and dest_alias not in existing_aliases:
                    self.report.add_check(
                        check_name=f"firewall_rule_{rule.name}_dest_alias",
                        passed=False,
                        message=(
                            f"Firewall rule '{rule.name}' references "
                            f"undefined destination alias '{dest_alias}'"
                        ),
                        level=ValidationLevel.ERROR,
                    )
                else:
                    self.report.add_check(
                        check_name=f"firewall_rule_{rule.name}_dest_alias",
                        passed=True,
                        message=f"Destination alias '{dest_alias}' found for rule '{rule.name}'",
                        level=ValidationLevel.INFO,
                    )
