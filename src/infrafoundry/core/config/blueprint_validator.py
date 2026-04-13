"""Blueprint template validator using Jinja2 static analysis.

Validates that all variables referenced in blueprint resource templates
are defined in the blueprint's defaults layers.  For multi-provider
blueprints, also warns about asymmetric variable usage across providers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
import jinja2.meta

from infrafoundry.core.config.filters import create_jinja2_env

logger = logging.getLogger(__name__)


@dataclass
class ProviderValidationResult:
    """Validation results for a single provider within a blueprint.

    Attributes:
        provider: Provider name (e.g. ``proxmox``, ``oci``).
        template_vars: All undeclared variables found across provider templates.
        defaults: Variable names available from defaults layers.
        errors: Variables referenced in templates but not in any defaults layer.
        warnings: Informational messages (e.g. asymmetric variable usage).
    """

    provider: str
    template_vars: frozenset[str] = field(default_factory=frozenset)
    defaults: frozenset[str] = field(default_factory=frozenset)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class BlueprintValidationResult:
    """Aggregate validation result for an entire blueprint.

    Attributes:
        blueprint_name: Name of the validated blueprint.
        is_multi_provider: Whether the blueprint uses the ``providers`` key.
        providers: Per-provider validation results.
    """

    blueprint_name: str
    is_multi_provider: bool
    providers: list[ProviderValidationResult] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Return ``True`` if any provider has validation errors."""
        return any(p.errors for p in self.providers)

    @property
    def has_warnings(self) -> bool:
        """Return ``True`` if any provider has validation warnings."""
        return any(p.warnings for p in self.providers)


class BlueprintValidator:
    """Validate blueprint templates against their declared defaults.

    Uses Jinja2 static analysis (``jinja2.meta.find_undeclared_variables``)
    to extract template variables without needing actual values.

    Args:
        resolved_blueprint: Output of ``BlueprintResolver.resolve()``.
    """

    def __init__(self, resolved_blueprint: dict[str, Any]) -> None:
        self._blueprint = resolved_blueprint
        self._blueprint_dir: Path = resolved_blueprint["blueprint_dir"]
        self._env = create_jinja2_env()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self) -> BlueprintValidationResult:
        """Validate all provider templates in the blueprint.

        Returns:
            Aggregated validation result with per-provider errors and warnings.
        """
        providers_block: dict[str, Any] | None = self._blueprint.get("providers")

        if providers_block is not None:
            return self._validate_multi_provider(providers_block)
        return self._validate_single_provider()

    # ------------------------------------------------------------------
    # Internal — single-provider
    # ------------------------------------------------------------------

    def _validate_single_provider(self) -> BlueprintValidationResult:
        """Validate a single-provider (flat) blueprint."""
        resources: list[str] = self._blueprint.get("resources", [])
        global_defaults = self._blueprint.get("defaults", {})

        template_vars = self._collect_provider_vars(resources, self._blueprint_dir)
        defaults_keys = frozenset(global_defaults.keys())

        errors = self._find_undefined_vars(template_vars, defaults_keys)

        provider_result = ProviderValidationResult(
            provider="default",
            template_vars=template_vars,
            defaults=defaults_keys,
            errors=errors,
        )

        return BlueprintValidationResult(
            blueprint_name=self._blueprint["name"],
            is_multi_provider=False,
            providers=[provider_result],
        )

    # ------------------------------------------------------------------
    # Internal — multi-provider
    # ------------------------------------------------------------------

    def _validate_multi_provider(
        self, providers_block: dict[str, Any]
    ) -> BlueprintValidationResult:
        """Validate a multi-provider blueprint."""
        global_defaults = self._blueprint.get("defaults", {})
        provider_results: list[ProviderValidationResult] = []

        # Collect vars per provider first for asymmetry detection
        provider_var_map: dict[str, frozenset[str]] = {}

        for provider_name, provider_block in providers_block.items():
            resources: list[str] = provider_block.get("resources", [])
            provider_defaults = provider_block.get("defaults", {})

            template_vars = self._collect_provider_vars(resources, self._blueprint_dir)
            all_defaults = frozenset(global_defaults.keys()) | frozenset(provider_defaults.keys())

            errors = self._find_undefined_vars(template_vars, all_defaults)
            provider_var_map[provider_name] = template_vars

            provider_results.append(
                ProviderValidationResult(
                    provider=provider_name,
                    template_vars=template_vars,
                    defaults=all_defaults,
                    errors=errors,
                )
            )

        # Detect asymmetric variable usage across providers
        self._detect_asymmetric_vars(provider_results, provider_var_map, global_defaults)

        return BlueprintValidationResult(
            blueprint_name=self._blueprint["name"],
            is_multi_provider=True,
            providers=provider_results,
        )

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    def _extract_template_vars(self, template_path: Path) -> frozenset[str]:
        """Extract undeclared variables from a Jinja2 template.

        Uses ``jinja2.meta.find_undeclared_variables()`` for static analysis.
        Loop-bound variables (e.g. ``for x in items``) are correctly excluded.

        Args:
            template_path: Absolute path to the template file.

        Returns:
            Set of variable names referenced but not defined within the template.
        """
        content = template_path.read_text()
        try:
            ast = self._env.parse(content)
        except jinja2.TemplateSyntaxError as e:
            logger.warning("Template syntax error in %s: %s", template_path, e)
            return frozenset()

        return frozenset(jinja2.meta.find_undeclared_variables(ast))

    def _collect_provider_vars(self, resources: list[str], base_dir: Path) -> frozenset[str]:
        """Collect all undeclared variables from a provider's resource templates.

        Args:
            resources: List of relative template file paths.
            base_dir: Base directory for resolving template paths.

        Returns:
            Union of all undeclared variables across all templates.
        """
        all_vars: set[str] = set()
        for resource_file in resources:
            template_path = base_dir / resource_file
            if template_path.exists():
                all_vars |= self._extract_template_vars(template_path)
            else:
                logger.warning("Resource template not found: %s", template_path)
        return frozenset(all_vars)

    @staticmethod
    def _find_undefined_vars(
        template_vars: frozenset[str], defaults_keys: frozenset[str]
    ) -> list[str]:
        """Find variables referenced in templates but not defined in defaults.

        Args:
            template_vars: Variables found in templates.
            defaults_keys: Variable names available from defaults layers.

        Returns:
            Sorted list of error messages for undefined variables.
        """
        undefined = template_vars - defaults_keys
        return sorted(
            f"Undefined variable: '{var}' (not in any defaults layer)" for var in undefined
        )

    @staticmethod
    def _detect_asymmetric_vars(
        provider_results: list[ProviderValidationResult],
        provider_var_map: dict[str, frozenset[str]],
        global_defaults: dict[str, Any],
    ) -> None:
        """Detect variables used by some providers but not all.

        Only considers variables that come from global defaults (shared across
        providers). Provider-specific variables are expected to differ.

        Modifies provider results in place by appending warnings.

        Args:
            provider_results: Per-provider results to append warnings to.
            provider_var_map: Mapping of provider name to template variables.
            global_defaults: The blueprint's top-level defaults dict.
        """
        if len(provider_var_map) < 2:
            return

        global_keys = frozenset(global_defaults.keys())
        all_provider_names = list(provider_var_map.keys())

        # For each global default, check if it's used asymmetrically
        for var in sorted(global_keys):
            users = [p for p in all_provider_names if var in provider_var_map[p]]
            non_users = [p for p in all_provider_names if var not in provider_var_map[p]]

            if users and non_users:
                for result in provider_results:
                    if result.provider in non_users:
                        result.warnings.append(
                            f"Asymmetric variable: '{var}' is in global defaults "
                            f"and used by {', '.join(users)} but not {result.provider}"
                        )
