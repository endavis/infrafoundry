"""Blueprint requirement declarations and check results.

A blueprint's ``requirements:`` block names the Python distributions and Ansible
collections its event handlers and playbooks need (#1046)::

    requirements:
      python:
        - spec: "netapp-lib>=2021.6.25"
          import: netapp_lib
      ansible_collections: requirements.yml

``python`` entries are PEP 508 specs, written either as a string or as a mapping
with ``spec`` and an optional ``import`` name for distributions whose import name
differs. ``ansible_collections`` is a path, relative to the blueprint directory, to
an ``ansible-galaxy`` requirements file.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet

from infrafoundry.core.exceptions import InvalidConfigurationError

_REQUIREMENTS_KEYS = frozenset({"python", "ansible_collections"})
_PYTHON_ENTRY_KEYS = frozenset({"spec", "import"})


class RequirementKind(StrEnum):
    """What kind of dependency a requirement names."""

    PYTHON = "python"
    ANSIBLE_COLLECTION = "ansible_collection"


@dataclass(frozen=True)
class PythonRequirement:
    """A Python distribution a blueprint needs.

    Attributes:
        spec: PEP 508 requirement string, e.g. ``netapp-lib>=2021.6.25``
        import_name: Module to import-check, when it differs from the distribution
    """

    spec: str
    import_name: str | None = None

    @property
    def requirement(self) -> Requirement:
        """The parsed PEP 508 requirement."""
        return Requirement(self.spec)


@dataclass(frozen=True)
class CollectionRequirement:
    """An Ansible collection a blueprint needs.

    Attributes:
        name: Fully qualified collection name, e.g. ``netapp.ontap``
        version: Specifier the installed version must satisfy; ``None`` accepts any
    """

    name: str
    version: str | None = None

    @property
    def specifier(self) -> SpecifierSet:
        """The version constraint as a specifier set (empty when unconstrained)."""
        return SpecifierSet(self.version or "")


@dataclass(frozen=True)
class BlueprintRequirements:
    """Everything one blueprint declares under ``requirements:``.

    Attributes:
        python: Python distributions to check
        collections: Ansible collections to check
        collections_file: The requirements file the collections came from
    """

    python: tuple[PythonRequirement, ...] = ()
    collections: tuple[CollectionRequirement, ...] = ()
    collections_file: Path | None = None

    @classmethod
    def parse(cls, raw: Any, blueprint_dir: Path, blueprint_name: str) -> BlueprintRequirements:
        """Parse and validate a blueprint's ``requirements:`` block.

        Args:
            raw: The value of ``requirements:``; ``None`` when the block is absent
            blueprint_dir: Directory holding the blueprint's ``blueprint.yaml``
            blueprint_name: Blueprint name, for error messages

        Returns:
            The declared requirements; empty when ``raw`` is ``None``

        Raises:
            InvalidConfigurationError: If the block, a spec or the collections
                file is invalid
        """
        if raw is None:
            return cls()
        where = f"blueprint '{blueprint_name}' requirements"
        if not isinstance(raw, dict):
            raise InvalidConfigurationError(f"{where}: must be a mapping")
        unknown = sorted(set(raw) - _REQUIREMENTS_KEYS)
        if unknown:
            raise InvalidConfigurationError(
                f"{where}: unknown key(s) {', '.join(unknown)}; "
                f"allowed: {', '.join(sorted(_REQUIREMENTS_KEYS))}"
            )

        python = tuple(
            _parse_python_entry(entry, f"{where}.python[{idx}]")
            for idx, entry in enumerate(_as_list(raw.get("python"), f"{where}.python"))
        )

        collections_file: Path | None = None
        collections: tuple[CollectionRequirement, ...] = ()
        if raw.get("ansible_collections") is not None:
            collections_file = _resolve_collections_file(
                raw["ansible_collections"], blueprint_dir, f"{where}.ansible_collections"
            )
            collections = _parse_collections_file(collections_file, blueprint_name)

        return cls(python=python, collections=collections, collections_file=collections_file)


@dataclass(frozen=True)
class RequirementStatus:
    """Whether one requirement is met by the current environment.

    Attributes:
        kind: Python distribution or Ansible collection
        name: Distribution or collection name
        wanted: The constraint, e.g. ``>=2021.6.25``; empty when unconstrained
        installed: Installed version, or ``None`` when not installed
        satisfied: Whether the installed version meets the constraint
        blueprints: Blueprints that declare the requirement
        problem: Why it is not satisfied; empty when it is
        fix: Command that installs or upgrades it
        install_args: What ``foundry deps sync`` installs for it: the PEP 508
            spec of a Python requirement, or the requirements file(s) (else
            ``name<spec>``) of a collection
    """

    kind: RequirementKind
    name: str
    wanted: str
    installed: str | None
    satisfied: bool
    blueprints: tuple[str, ...]
    problem: str = ""
    fix: str = ""
    install_args: tuple[str, ...] = ()


def _as_list(value: Any, where: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidConfigurationError(f"{where}: must be a list")
    return value


def _parse_python_entry(entry: Any, where: str) -> PythonRequirement:
    spec: Any
    import_name: str | None = None
    if isinstance(entry, str):
        spec = entry
    elif isinstance(entry, dict):
        unknown = sorted(set(entry) - _PYTHON_ENTRY_KEYS)
        if unknown:
            raise InvalidConfigurationError(
                f"{where}: unknown key(s) {', '.join(unknown)}; allowed: import, spec"
            )
        spec, raw_import = entry.get("spec"), entry.get("import")
        if raw_import is not None:
            if not isinstance(raw_import, str) or not raw_import:
                raise InvalidConfigurationError(f"{where}: 'import' must be a non-empty string")
            import_name = raw_import
    else:
        raise InvalidConfigurationError(f"{where}: must be a string or a mapping with 'spec'")

    if not isinstance(spec, str) or not spec.strip():
        raise InvalidConfigurationError(f"{where}: 'spec' must be a non-empty PEP 508 string")
    try:
        Requirement(spec)
    except InvalidRequirement as e:
        raise InvalidConfigurationError(f"{where}: invalid requirement '{spec}': {e}") from e
    return PythonRequirement(spec=spec.strip(), import_name=import_name)


def _resolve_collections_file(value: Any, blueprint_dir: Path, where: str) -> Path:
    if not isinstance(value, str) or not value:
        raise InvalidConfigurationError(f"{where}: must be a path relative to the blueprint")
    root = blueprint_dir.resolve()
    path = (root / value).resolve()
    if root != path and root not in path.parents:
        raise InvalidConfigurationError(f"{where}: '{value}' points outside the blueprint")
    if not path.is_file():
        raise InvalidConfigurationError(f"{where}: file not found: {path}")
    return path


def _parse_collections_file(path: Path, blueprint_name: str) -> tuple[CollectionRequirement, ...]:
    where = f"blueprint '{blueprint_name}' collections file {path.name}"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise InvalidConfigurationError(f"{where}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise InvalidConfigurationError(f"{where}: must be a mapping with 'collections'")

    parsed = []
    for idx, entry in enumerate(_as_list(data.get("collections"), f"{where} collections")):
        entry_where = f"{where} collections[{idx}]"
        if isinstance(entry, str):
            name, version = entry, None
        elif isinstance(entry, dict) and isinstance(entry.get("name"), str):
            name, version = entry["name"], entry.get("version")
        else:
            raise InvalidConfigurationError(f"{entry_where}: must be a name or have 'name'")
        parsed.append(
            CollectionRequirement(name=name, version=_galaxy_specifier(version, entry_where))
        )
    return tuple(parsed)


def _galaxy_specifier(version: Any, where: str) -> str | None:
    """Convert an ``ansible-galaxy`` version field to a PEP 440 specifier.

    Galaxy accepts ``*`` (any), a bare version (exact) or comma-separated
    ``>=``/``<``/``==``/``!=`` clauses.
    """
    if version is None:
        return None
    text = str(version).strip()
    if text in ("", "*"):
        return None
    if text[0].isdigit():
        text = f"=={text}"
    try:
        SpecifierSet(text)
    except InvalidSpecifier as e:
        raise InvalidConfigurationError(f"{where}: invalid version '{version}': {e}") from e
    return text
