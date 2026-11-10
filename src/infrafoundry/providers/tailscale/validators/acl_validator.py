"""ACL resource validation."""

from __future__ import annotations

import json
from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationReport

from ._common import fail
from .context import TailscaleConfigContext


class AclValidator(SpecializedValidator[TailscaleConfigContext]):
    """Checks ``acl`` resources have exactly one of ``policy`` or ``hujson``."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    @override
    def validate(self, context: TailscaleConfigContext) -> None:
        """Check each ``acl`` resource.

        Args:
            context: Context whose resources are checked.
        """
        for resource in context.resources:
            if resource.type != "acl":
                continue
            config = resource.config
            check = f"tailscale_acl_{resource.name}"
            has_policy = "policy" in config
            has_hujson = "hujson" in config
            if has_policy == has_hujson:
                fail(
                    self.report,
                    check,
                    f"acl '{resource.name}' needs exactly one of 'policy' (mapping) "
                    "or 'hujson' (string)",
                )
            elif has_policy:
                policy = config["policy"]
                if not isinstance(policy, dict):
                    fail(self.report, check, f"acl '{resource.name}': policy must be a mapping")
                else:
                    try:
                        json.dumps(policy)
                    except (TypeError, ValueError) as exc:
                        fail(
                            self.report,
                            check,
                            f"acl '{resource.name}': policy is not JSON-serialisable: {exc}",
                        )
            else:
                hujson = config["hujson"]
                if not isinstance(hujson, str) or not hujson.strip():
                    fail(
                        self.report,
                        check,
                        f"acl '{resource.name}': hujson must be a non-empty string",
                    )
            for flag in ("overwrite_existing_content", "reset_acl_on_destroy"):
                if flag in config and not isinstance(config[flag], bool):
                    fail(
                        self.report,
                        f"tailscale_acl_{flag}_{resource.name}",
                        f"acl '{resource.name}': {flag} must be true or false",
                    )
