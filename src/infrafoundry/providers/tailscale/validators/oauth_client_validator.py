"""OAuth client resource validation."""

from __future__ import annotations

from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationReport

from ._common import check_tags, fail
from .context import TailscaleConfigContext


class OAuthClientValidator(SpecializedValidator[TailscaleConfigContext]):
    """Checks ``oauth_client`` scopes, description and tags."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: TailscaleConfigContext) -> None:
        """Check each ``oauth_client`` resource.

        Args:
            context: Context whose resources are checked.
        """
        for resource in context.resources:
            if resource.type != "oauth_client":
                continue
            config = resource.config
            name = resource.name
            scopes = config.get("scopes")
            if (
                not isinstance(scopes, list)
                or not scopes
                or not all(isinstance(s, str) and s for s in scopes)
            ):
                fail(
                    self.report,
                    f"tailscale_oauth_client_scopes_{name}",
                    f"oauth_client '{name}': scopes must be a non-empty list of strings",
                )
            if "description" in config and not isinstance(config["description"], str):
                fail(
                    self.report,
                    f"tailscale_oauth_client_description_{name}",
                    f"oauth_client '{name}': description must be a string",
                )
            tags = config.get("tags")
            if tags:
                check_tags(self.report, name, tags, context.acl_policy)
