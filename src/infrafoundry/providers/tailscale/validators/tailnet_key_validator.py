"""Tailnet key resource validation."""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationReport

from ._common import check_tags, fail
from .context import TailscaleConfigContext

_BOOL_FIELDS = ("ephemeral", "preauthorized", "reusable")


class TailnetKeyValidator(SpecializedValidator[TailscaleConfigContext]):
    """Checks ``tailnet_key`` field types, tags and the OAuth tag requirement."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: TailscaleConfigContext) -> None:
        """Check each ``tailnet_key`` resource.

        Args:
            context: Context whose resources are checked.
        """
        for resource in context.resources:
            if resource.type != "tailnet_key":
                continue
            config = resource.config
            name = resource.name
            for flag in _BOOL_FIELDS:
                if flag in config and not isinstance(config[flag], bool):
                    fail(
                        self.report,
                        f"tailscale_key_{flag}_{name}",
                        f"tailnet_key '{name}': {flag} must be true or false",
                    )
            expiry = config.get("expiry")
            if "expiry" in config and (
                isinstance(expiry, bool) or not isinstance(expiry, int) or expiry <= 0
            ):
                fail(
                    self.report,
                    f"tailscale_key_expiry_{name}",
                    f"tailnet_key '{name}': expiry must be a positive integer of seconds",
                )
            recreate = config.get("recreate_if_invalid")
            if "recreate_if_invalid" in config and recreate not in ("always", "never"):
                fail(
                    self.report,
                    f"tailscale_key_recreate_{name}",
                    f"tailnet_key '{name}': recreate_if_invalid must be 'always' or 'never'",
                )
            if "description" in config and not isinstance(config["description"], str):
                fail(
                    self.report,
                    f"tailscale_key_description_{name}",
                    f"tailnet_key '{name}': description must be a string",
                )
            tags = config.get("tags")
            if tags:
                check_tags(self.report, name, tags, context.acl_policy)
            elif context.auth_mode == "oauth":
                fail(
                    self.report,
                    f"tailscale_key_tags_{name}",
                    f"tailnet_key '{name}': OAuth credentials can only create keys with tags; "
                    "set 'tags'",
                )
