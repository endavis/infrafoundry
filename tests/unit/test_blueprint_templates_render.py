"""Every blueprint resource template renders to valid YAML (#1100).

``check-yaml`` skips blueprint resource templates (#1096): unrendered, they
are Jinja2, not YAML. This test checks what matters instead. It renders each
template listed in a ``blueprint.yaml`` (top-level ``resources:`` and every
``providers.<name>.resources:``) with the blueprint's input defaults, plus a
typed placeholder for each required input, through the same path
``PackageLoader`` uses, and asserts the output parses to a non-empty mapping.

New blueprints are picked up automatically through ``BlueprintResolver``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import InvalidConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"

# Placeholder for a required input (one with no default), by declared type.
# True takes the optional branches; an untyped input is a string.
_PLACEHOLDERS: dict[str, Any] = {"integer": 100, "boolean": True, "list": []}


def _context(inputs: list[dict[str, Any]] | None, defaults: dict[str, Any]) -> dict[str, Any]:
    """Build a render context from an ``inputs:`` list and its defaults."""
    context: dict[str, Any] = {}
    for entry in inputs or []:
        name = entry["name"]
        if name in defaults:
            context[name] = defaults[name]
        else:
            context[name] = _PLACEHOLDERS.get(entry.get("type", ""), f"placeholder-{name}")
    return context


def _template_cases(resolver: BlueprintResolver) -> list[tuple[str, str, Path, dict[str, Any]]]:
    """Return ``(blueprint, provider, template path, context)`` for every template."""
    cases: list[tuple[str, str, Path, dict[str, Any]]] = []
    for name in resolver.list_blueprints():
        blueprint = resolver.resolve(name)
        blueprint_dir = Path(blueprint["blueprint_dir"])
        raw = yaml.safe_load((blueprint_dir / "blueprint.yaml").read_text())

        top = _context(raw.get("inputs"), blueprint["defaults"])
        for resource in blueprint["resources"]:
            cases.append((name, "", blueprint_dir / resource, top))

        for provider, block in (blueprint.get("providers") or {}).items():
            context = {
                **top,
                **_context(raw["providers"][provider].get("inputs"), block["defaults"]),
            }
            for resource in block.get("resources", []):
                cases.append((name, provider, blueprint_dir / resource, context))
    return cases


def _render(path: Path, context: dict[str, Any], provider: str) -> dict[str, Any]:
    loader = PackageLoader(EXAMPLE_ENVS)
    return loader._render_resource_file(path, context, provider=provider or None)


_CASES = _template_cases(BlueprintResolver(EXAMPLE_ENVS))


def test_every_blueprint_has_a_template() -> None:
    blueprints = {name for name, _provider, _path, _context in _CASES}

    assert blueprints == set(BlueprintResolver(EXAMPLE_ENVS).list_blueprints())


@pytest.mark.parametrize(
    ("provider", "path", "context"),
    [(provider, path, context) for _name, provider, path, context in _CASES],
    ids=[
        f"{name}:{path.relative_to(REPO_ROOT / 'blueprints' / name)}"
        for name, _p, path, _c in _CASES
    ],
)
def test_template_renders_to_a_yaml_mapping(
    provider: str, path: Path, context: dict[str, Any]
) -> None:
    data = _render(path, context, provider)

    assert data, f"{path} rendered to an empty document"


def _write_blueprint(root: Path, template: str) -> BlueprintResolver:
    blueprint_dir = root / "blueprints" / "broken"
    blueprint_dir.mkdir(parents=True)
    (blueprint_dir / "blueprint.yaml").write_text(
        "name: broken\n"
        "inputs:\n"
        "  - name: vmid\n"
        "    type: integer\n"
        "  - name: tags\n"
        "    default: [a]\n"
        "resources:\n"
        "  - vm.yaml\n"
    )
    (blueprint_dir / "vm.yaml").write_text(template)
    resolver = BlueprintResolver(EXAMPLE_ENVS)
    resolver.blueprints_dir = root / "blueprints"
    return resolver


def test_placeholders_and_defaults_reach_the_template(tmp_path: Path) -> None:
    resolver = _write_blueprint(tmp_path, "vms:\n  - vmid: {{ vmid }}\n    tags: {{ tags }}\n")

    [(_name, provider, path, context)] = _template_cases(resolver)

    assert _render(path, context, provider) == {"vms": [{"vmid": 100, "tags": ["a"]}]}


@pytest.mark.parametrize(
    "template",
    [
        pytest.param("vms:\n  - vmid: {{ vmid }}\n   bad: indent\n", id="bad-indentation"),
        pytest.param("vms: [{{ vmid }}\n", id="unbalanced-bracket"),
        pytest.param("vms:\n  - vmid: {{ undeclared }}\n", id="undefined-variable"),
    ],
)
def test_a_broken_template_is_caught(tmp_path: Path, template: str) -> None:
    resolver = _write_blueprint(tmp_path, template)

    [(_name, provider, path, context)] = _template_cases(resolver)

    with pytest.raises(InvalidConfigurationError):
        _render(path, context, provider)
