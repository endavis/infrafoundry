"""Validation helper for resource ``terraform_secrets`` references.

Verifies that each resource's optional ``terraform_secrets`` list:

1. Has the right shape (list of strings).
2. References dotted paths that resolve in the env's decrypted secrets dict.

The framework's secrets→TF_VAR bridge requires both invariants to hold,
otherwise apply-time terraform invocation will either crash or silently
inject empty values for sensitive variables.
"""

from __future__ import annotations

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.secrets.secret_manager import SecretManager
from infrafoundry.core.validation import ValidationLevel, ValidationReport


def validate_terraform_secrets_references(
    provider_name: str,
    resources: list[ResourceConfig],
    env_config: EnvironmentConfig,
    report: ValidationReport,
) -> None:
    """Validate ``terraform_secrets`` references on each resource.

    Adds one ``ValidationReport`` entry per resource that declares any
    ``terraform_secrets``. Resources without the field are silently
    skipped (the field is optional).

    Args:
        provider_name: Provider name (used to namespace check names).
        resources: Resources to validate.
        env_config: The loaded ``EnvironmentConfig`` (or anything with a
            ``secrets`` attribute). Typed as ``Any`` to avoid a circular
            import with ``infrafoundry.core.config.models``.
        report: ValidationReport to mutate.
    """
    flat_secrets: dict[str, str] | None = None

    for resource in resources:
        config = resource.config or {}
        refs = config.get("terraform_secrets")
        if refs is None:
            continue

        check_name = f"{provider_name}_terraform_secrets_{resource.name}"

        if not isinstance(refs, list):
            report.add_check(
                check_name=check_name,
                passed=False,
                message=(
                    f"Resource '{resource.name}' has a non-list "
                    f"terraform_secrets value: {type(refs).__name__}"
                ),
                level=ValidationLevel.ERROR,
            )
            continue

        invalid_entries = [r for r in refs if not isinstance(r, str)]
        if invalid_entries:
            report.add_check(
                check_name=check_name,
                passed=False,
                message=(
                    f"Resource '{resource.name}' terraform_secrets contains "
                    f"non-string entries: {invalid_entries!r}"
                ),
                level=ValidationLevel.ERROR,
            )
            continue

        # Lazy-flatten: only do the work if at least one resource declares secrets.
        if flat_secrets is None:
            secrets_dict = getattr(env_config, "secrets", None)
            flat_secrets = SecretManager.flatten_dict(secrets_dict)

        missing = [ref for ref in refs if ref not in flat_secrets]
        if missing:
            report.add_check(
                check_name=check_name,
                passed=False,
                message=(
                    f"Resource '{resource.name}' terraform_secrets references "
                    f"unknown secret keys: {missing}. "
                    f"Ensure each dotted path exists in the env's secrets file."
                ),
                level=ValidationLevel.ERROR,
            )
            continue

        report.add_check(
            check_name=check_name,
            passed=True,
            message=(
                f"Resource '{resource.name}' terraform_secrets references "
                f"resolve in env secrets ({len(refs)} keys)."
            ),
        )
