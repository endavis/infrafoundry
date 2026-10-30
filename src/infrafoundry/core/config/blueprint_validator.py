"""Blueprint template validator using Jinja2 static analysis.

Validates that all variables referenced in blueprint resource templates
are defined in the blueprint's defaults layers.  For multi-provider
blueprints, also warns about asymmetric variable usage across providers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
import jinja2.meta

from infrafoundry.core.config.filters import create_jinja2_env

logger = logging.getLogger(__name__)

_SCRIPT_ENV_VAR_RE = re.compile(r"INFRAFOUNDRY_VAR_([A-Za-z_][A-Za-z0-9_]*)")
_SCRIPT_JINJA_RE = re.compile(r"\{\{-?\s*([A-Za-z_][A-Za-z0-9_]*)")


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

        template_vars = self._collect_provider_vars(resources, self._blueprint_dir)
        defaults_keys = self._resolve_input_names(self._blueprint)

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
        global_input_names = self._resolve_input_names(self._blueprint)
        provider_results: list[ProviderValidationResult] = []

        # Collect vars per provider first for asymmetry detection
        provider_var_map: dict[str, frozenset[str]] = {}
        shared_event_vars = self._collect_event_vars(self._blueprint.get("events"))

        for provider_name, provider_block in providers_block.items():
            resources: list[str] = provider_block.get("resources", [])
            provider_input_names = self._resolve_input_names(provider_block)

            template_vars = self._collect_provider_vars(resources, self._blueprint_dir)
            all_defaults = global_input_names | provider_input_names

            errors = self._find_undefined_vars(template_vars, all_defaults)
            # Asymmetry counts a variable as used when templates, event
            # strings or event scripts reference it (#1201).
            provider_var_map[provider_name] = (
                template_vars
                | shared_event_vars
                | self._collect_event_vars(provider_block.get("events"))
                | self._collect_script_dir_vars(provider_name)
            )

            provider_results.append(
                ProviderValidationResult(
                    provider=provider_name,
                    template_vars=template_vars,
                    defaults=all_defaults,
                    errors=errors,
                )
            )

        # Detect asymmetric variable usage across providers
        self._detect_asymmetric_vars(provider_results, provider_var_map, global_input_names)

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

    def _collect_event_vars(self, events: Any) -> frozenset[str]:
        """Collect variables referenced by an events block and its scripts.

        Walks every string in ``events``, extracting Jinja variables, and
        scans each referenced ``script`` file for variable references.

        Args:
            events: An ``events`` mapping (or ``None``) from a blueprint or provider.

        Returns:
            Frozenset of variable names referenced.
        """
        found: set[str] = set()
        self._walk_event_value(events, found)
        return frozenset(found)

    def _walk_event_value(self, value: Any, found: set[str]) -> None:
        """Recursively gather variables from strings and script files in ``value``."""
        if isinstance(value, str):
            try:
                found |= jinja2.meta.find_undeclared_variables(self._env.parse(value))
            except jinja2.TemplateSyntaxError:
                found.update(_SCRIPT_JINJA_RE.findall(value))
        elif isinstance(value, dict):
            for key, item in value.items():
                if key == "script" and isinstance(item, str):
                    found |= self._scan_script(self._blueprint_dir / item)
                self._walk_event_value(item, found)
        elif isinstance(value, list):
            for item in value:
                self._walk_event_value(item, found)

    def _collect_script_dir_vars(self, provider_name: str) -> frozenset[str]:
        """Collect variables referenced by files under ``scripts/<provider>/``."""
        scripts_dir = self._blueprint_dir / "scripts" / provider_name
        found: set[str] = set()
        if scripts_dir.is_dir():
            for path in sorted(scripts_dir.rglob("*")):
                found |= self._scan_script(path)
        return frozenset(found)

    @staticmethod
    def _scan_script(path: Path) -> frozenset[str]:
        """Return variable names a script references.

        Matches ``INFRAFOUNDRY_VAR_<name>`` and ``{{ <name> }}`` occurrences.

        Args:
            path: Script file path; unreadable or missing files yield no names.
        """
        try:
            content = path.read_text()
        except (OSError, UnicodeDecodeError):
            return frozenset()
        return frozenset(_SCRIPT_ENV_VAR_RE.findall(content) + _SCRIPT_JINJA_RE.findall(content))

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
        return sorted(f"Undefined variable: '{var}' (not declared in inputs)" for var in undefined)

    @staticmethod
    def _resolve_input_names(block: dict[str, Any]) -> frozenset[str]:
        """Return the declared input names for a resolved block.

        Prefers the resolver-populated ``input_names`` frozenset; falls back
        to ``defaults.keys()`` for legacy / test fixtures that build blocks
        without going through the resolver.

        Args:
            block: Either the full resolved blueprint dict or a single
                provider block within ``providers``.

        Returns:
            Frozenset of variable names considered declared for this block.
        """
        names = block.get("input_names")
        if isinstance(names, frozenset):
            return names
        defaults = block.get("defaults") or {}
        return frozenset(defaults.keys())

    @staticmethod
    def _detect_asymmetric_vars(
        provider_results: list[ProviderValidationResult],
        provider_var_map: dict[str, frozenset[str]],
        global_input_names: frozenset[str],
    ) -> None:
        """Detect variables used by some providers but not all.

        Only considers variables that come from global inputs (shared across
        providers). Provider-specific variables are expected to differ.

        Modifies provider results in place by appending warnings.

        Args:
            provider_results: Per-provider results to append warnings to.
            provider_var_map: Mapping of provider name to template variables.
            global_input_names: The blueprint's top-level declared input names.
        """
        if len(provider_var_map) < 2:
            return

        global_keys = global_input_names
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
