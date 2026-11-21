"""Validation helper for resource ``terraform_secrets`` references.

Verifies that each resource's optional ``terraform_secrets`` list:

1. Has the right shape (list of strings).
2. References ``secret://<backend>/<key>`` URIs for a backend configured on the environment
   (checked offline: a vault is queried at apply time, never here), dotted paths that resolve
   in the env's decrypted secrets dict, or, for ``package.<key>`` refs, in the owning
   package's ``secrets.yaml`` variables (#1565).

The framework's secrets→TF_VAR bridge requires both invariants to hold,
otherwise apply-time terraform invocation will either crash or silently
inject empty values for sensitive variables.
"""

from __future__ import annotations

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.package_secret_refs import is_package_ref, package_ref_problem
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_mixins import is_output_ref
from infrafoundry.core.secrets.secret_manager import SecretManager
from infrafoundry.core.terraform_outputs import parse_output_ref
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.secrets.environment import SecretRefLookup
from infrafoundry.secrets.resolver import is_secret_uri


def validate_terraform_secrets_references(
    provider_name: str,
    resources: list[ResourceConfig],
    env_config: EnvironmentConfig,
    report: ValidationReport,
    *,
    allow_output_refs: bool = False,
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
        allow_output_refs: Accept ``outputs.<provider>.<output>`` references to another
            provider's Terraform outputs (#1536). When False they are reported as errors.
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

        uri_problems = [
            f"'{ref}': {problem}"
            for ref in refs
            if is_secret_uri(ref)
            and (problem := SecretRefLookup(env_config).problem(ref)) is not None
        ]
        if uri_problems:
            report.add_check(
                check_name=check_name,
                passed=False,
                message=f"Resource '{resource.name}' terraform_secrets: " + "; ".join(uri_problems),
                level=ValidationLevel.ERROR,
            )
            continue

        output_problems = _output_ref_problems(
            provider_name, [r for r in refs if is_output_ref(r)], allow_output_refs
        )
        if output_problems:
            report.add_check(
                check_name=check_name,
                passed=False,
                message=f"Resource '{resource.name}' terraform_secrets: "
                + "; ".join(output_problems),
                level=ValidationLevel.ERROR,
            )
            continue

        package_problems = [
            problem
            for ref in refs
            if is_package_ref(ref) and (problem := package_ref_problem(resource, ref)) is not None
        ]
        if package_problems:
            for problem in package_problems:
                report.add_check(
                    check_name=check_name,
                    passed=False,
                    message=problem,
                    level=ValidationLevel.ERROR,
                )
            continue

        missing = [
            ref
            for ref in refs
            if not is_secret_uri(ref)
            and not is_output_ref(ref)
            and not is_package_ref(ref)
            and ref not in flat_secrets
        ]
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


def output_ref_problem(provider_name: str, ref: str, allowed: bool) -> str | None:
    """Return why an ``outputs.*`` reference is unusable, or None when it is usable.

    Args:
        provider_name: Provider that carries the reference.
        ref: A reference starting with ``outputs.``.
        allowed: Whether the provider accepts ``outputs.*`` references at all.

    Returns:
        A message naming the ref (never a value), or None.
    """
    if not allowed:
        return f"'{ref}': outputs.* references are supported by the kubernetes provider only"
    try:
        parsed = parse_output_ref(ref)
    except InvalidConfigurationError as exc:
        return str(exc)
    if parsed.provider == provider_name:
        return f"'{ref}' names the provider's own outputs; use another provider"
    return None


def _output_ref_problems(provider_name: str, refs: list[str], allowed: bool) -> list[str]:
    """Return one message per unusable ``outputs.*`` reference."""
    return [p for ref in refs if (p := output_ref_problem(provider_name, ref, allowed)) is not None]
