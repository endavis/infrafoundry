"""Cross-provider Terraform output references (#1536).

A consumer provider names a producer's Terraform output as
``outputs.<provider>.<output>`` inside ``terraform_secrets`` (and the fields that fold into it).
The framework reads the value with ``terraform output -json`` in the producer's directory and
hands it to the consumer as a ``TF_VAR_*`` variable, through the same bridge SOPS secrets use.

Output values are secrets. They live only in memory and in the environment of one Terraform
call; they are never logged, printed or written to disk. Messages name the reference, the
provider, the output and the value type, never the value.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess  # nosec B404  # required for running terraform output
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infrafoundry.core.exceptions import InvalidConfigurationError, OutputReferenceError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_mixins import (
    OUTPUT_REF_PREFIX,
    is_output_ref,
    sanitize_secret_ref_to_tf_var,
)

logger = logging.getLogger(__name__)

#: Value used for an unresolved output in plan, destroy and validate; never reaches an apply.
PLACEHOLDER = "__infrafoundry_unresolved_output__"

_PART_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class OutputRef:
    """A parsed ``outputs.<provider>.<output>`` reference."""

    provider: str
    output: str

    def __str__(self) -> str:
        """Return the dotted form."""
        return f"{OUTPUT_REF_PREFIX}{self.provider}.{self.output}"


def output_refs(refs: list[str]) -> list[str]:
    """Return the entries of ``refs`` that are output references, in order.

    Args:
        refs: ``terraform_secrets`` entries.
    """
    return [r for r in refs if is_output_ref(r)]


def parse_output_ref(ref: str) -> OutputRef:
    """Parse ``outputs.<provider>.<output>``.

    Args:
        ref: The reference.

    Returns:
        The parsed reference.

    Raises:
        InvalidConfigurationError: If it is not exactly three dotted parts, each
            matching ``^[a-z][a-z0-9_]*$``.
    """
    parts = ref.split(".")
    if len(parts) != 3 or parts[0] != "outputs" or not all(_PART_RE.match(p) for p in parts):
        raise InvalidConfigurationError(
            f"Output reference '{ref}' must look like outputs.<provider>.<output>, "
            "with lowercase letters, digits and underscores in each part"
        )
    return OutputRef(provider=parts[1], output=parts[2])


def output_ref_dependencies(
    providers: Mapping[str, Any],
    resources_by_provider: Mapping[str, list[ResourceConfig]] | None,
) -> dict[str, set[str]]:
    """Map each consumer provider to the producer providers its output refs name.

    Malformed references are skipped here; validation reports them.

    Args:
        providers: Provider name to provider instance.
        resources_by_provider: The run's resources per provider; ``None`` uses each
            provider's last generation.

    Returns:
        Consumer to producers. Self references are left out.
    """
    deps: dict[str, set[str]] = {}
    for name, provider in providers.items():
        resources = resources_by_provider.get(name) if resources_by_provider is not None else None
        if resources_by_provider is not None and not resources:
            continue
        hook = getattr(provider, "get_terraform_output_refs", None)
        refs = hook(resources) if callable(hook) else None
        if not isinstance(refs, list):
            continue
        producers: set[str] = set()
        for ref in refs:
            try:
                parsed = parse_output_ref(ref)
            except InvalidConfigurationError:
                continue
            if parsed.provider != name:
                producers.add(parsed.provider)
        if producers:
            deps[name] = producers
    return deps


def _read_outputs(
    producer: str, tool_path: str, terraform_root: Path, strict: bool
) -> dict[str, Any] | None:
    """Return the producer's outputs, or ``None`` when lenient and unavailable."""
    producer_dir = terraform_root / producer
    hint = f"run `infra apply --env <env> -P {producer}` first"
    problem: str | None = None
    outputs: dict[str, Any] = {}
    if not (producer_dir / ".terraform").is_dir():
        problem = f"the {producer} Terraform directory is missing or not initialised"
    else:
        result = subprocess.run(  # tool_path binary, runner-built list argv, no shell
            [tool_path, "output", "-json"],
            cwd=producer_dir,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            problem = f"reading the {producer} outputs failed (exit {result.returncode})"
        else:
            try:
                parsed = json.loads(result.stdout)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                outputs = parsed
            else:
                problem = f"the {producer} outputs are not readable JSON"
    if problem is None:
        return outputs
    if strict:
        raise OutputReferenceError(f"Cannot resolve outputs.{producer}.*: {problem}; {hint}.")
    return None


def resolve_output_refs(
    refs: list[str], *, tool_path: str, terraform_root: Path, strict: bool
) -> dict[str, str]:
    """Resolve output references into ``TF_VAR_*`` environment entries.

    Runs ``terraform output -json`` once per producer, in
    ``terraform_root / <producer>``.

    Args:
        refs: ``outputs.<provider>.<output>`` references.
        tool_path: Path to the terraform or tofu binary.
        terraform_root: Directory holding one Terraform directory per provider.
        strict: When True an unresolved reference raises; when False it gets
            :data:`PLACEHOLDER` and a warning (plan, destroy and validate).

    Returns:
        ``TF_VAR_<sanitized ref>`` to value.

    Raises:
        OutputReferenceError: In strict mode, if a producer's outputs cannot be read, an
            output is missing, or its value is not a string.
        InvalidConfigurationError: If a reference is malformed.
    """
    parsed_refs = [(ref, parse_output_ref(ref)) for ref in dict.fromkeys(refs)]
    cache: dict[str, dict[str, Any] | None] = {}
    env: dict[str, str] = {}
    for ref, parsed in parsed_refs:
        if parsed.provider not in cache:
            cache[parsed.provider] = _read_outputs(
                parsed.provider, tool_path, terraform_root, strict
            )
        outputs = cache[parsed.provider]
        value: str | None = None
        if outputs is not None:
            entry = outputs.get(parsed.output)
            if not isinstance(entry, dict) or "value" not in entry:
                reason = f"{parsed.provider} has no output '{parsed.output}'"
            elif not isinstance(entry["value"], str):
                reason = (
                    f"output '{parsed.output}' of {parsed.provider} is a "
                    f"{type(entry['value']).__name__}, not a string"
                )
            else:
                reason = ""
                value = entry["value"]
            if value is None and strict:
                raise OutputReferenceError(
                    f"Cannot resolve '{ref}': {reason}; run "
                    f"`infra apply --env <env> -P {parsed.provider}` first."
                )
        if value is None:
            logger.warning(
                "'%s' is known after %s is applied; using a placeholder for this command",
                ref,
                parsed.provider,
            )
            value = PLACEHOLDER
        env[f"TF_VAR_{sanitize_secret_ref_to_tf_var(ref)}"] = value
    return env


__all__ = [
    "OUTPUT_REF_PREFIX",
    "PLACEHOLDER",
    "OutputRef",
    "is_output_ref",
    "output_ref_dependencies",
    "output_refs",
    "parse_output_ref",
    "resolve_output_refs",
]
