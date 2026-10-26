"""InfraFoundry checks on ``[tool.mutmut]`` that the template's tests cannot know (#1108).

``tests/test_mutmut_config.py`` (from the template) keeps the test selection to
what ``mutants/`` can import. Two more things stopped the stats run here, and so
every mutant went unchecked:

- Blueprint and example-config tests read files under ``blueprints/`` and
  ``example-config/``. mutmut copies neither into ``mutants/`` unless
  ``also_copy`` lists it.
- Mutating a method of a ``runtime_checkable`` Protocol adds mutmut's
  trampoline attributes to the protocol. ``isinstance()`` then fails for every
  real implementation, so those modules go in ``do_not_mutate``.

These are structural asserts on the parsed TOML and the source. They do not run mutmut.
"""

from __future__ import annotations

import ast
import fnmatch
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent

# Repository directories that tests read data from (not import).
DATA_DIRS = ("blueprints", "example-config")


def _mutmut_config() -> dict[str, Any]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as f:
        config: dict[str, Any] = tomllib.load(f)["tool"]["mutmut"]
    return config


def _selected_test_modules(config: dict[str, Any]) -> list[Path]:
    modules: set[Path] = set()
    for entry in config["pytest_add_cli_args_test_selection"]:
        if entry.startswith("-"):
            continue
        path = REPO_ROOT / entry.split("::")[0]
        modules |= set(path.rglob("*.py")) if path.is_dir() else {path}
    return sorted(modules)


def _data_dirs_named(source: str) -> set[str]:
    """Return the ``DATA_DIRS`` that *source* names in a string literal."""
    named: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            head = node.value.split("/")[0]
            if head in DATA_DIRS:
                named.add(head)
    return named


def _is_runtime_checkable(node: ast.ClassDef) -> bool:
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "runtime_checkable":
            return True
        if isinstance(decorator, ast.Attribute) and decorator.attr == "runtime_checkable":
            return True
    return False


def _gives_mutmut_something_to_mutate(method: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if mutmut would generate a mutant for *method*.

    A stub (optional docstring, then ``...`` or ``pass``) with no default
    arguments has nothing to mutate, so mutmut leaves its protocol alone.
    """
    if method.args.defaults or any(d is not None for d in method.args.kw_defaults):
        return True
    return not all(
        isinstance(stmt, ast.Pass)
        or (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and (stmt.value.value is Ellipsis or isinstance(stmt.value.value, str))
        )
        for stmt in method.body
    )


def _defines_mutable_runtime_protocol(source: str) -> bool:
    """Return True if *source* has a runtime_checkable class with a method mutmut would mutate."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and _is_runtime_checkable(node):
            methods = [
                n for n in node.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
            if any(_gives_mutmut_something_to_mutate(m) for m in methods):
                return True
    return False


def test_also_copy_holds_the_data_dirs_selected_tests_read() -> None:
    config = _mutmut_config()
    copied = {Path(entry).parts[0] for entry in config.get("also_copy", [])}
    missing = {
        module.relative_to(REPO_ROOT).as_posix(): sorted(named - copied)
        for module in _selected_test_modules(config)
        if (named := _data_dirs_named(module.read_text(encoding="utf-8"))) - copied
    }

    assert not missing, (
        f"these selected tests read directories mutmut does not copy into mutants/: {missing}. "
        "Add them to also_copy in [tool.mutmut]."
    )


def test_runtime_protocol_modules_are_not_mutated() -> None:
    config = _mutmut_config()
    patterns = config.get("do_not_mutate", [])
    unprotected = []
    for source_root in config["source_paths"]:
        for path in sorted((REPO_ROOT / source_root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(fnmatch.fnmatch(rel, p) for p in patterns):
                continue
            if _defines_mutable_runtime_protocol(path.read_text(encoding="utf-8")):
                unprotected.append(rel)

    assert not unprotected, (
        "these modules define a runtime_checkable protocol whose methods mutmut would mutate, "
        f"which breaks isinstance() for real implementations: {unprotected}. "
        "Add them to do_not_mutate in [tool.mutmut]."
    )


def test_the_scanners_see_what_they_look_for() -> None:
    assert _data_dirs_named('ROOT / "blueprints" / "x"\nP = "example-config/envs"\n') == {
        "blueprints",
        "example-config",
    }
    assert _data_dirs_named('x = "scripts"\n') == set()
    stub = 'class P(Protocol):\n    def f(self, x: int) -> None:\n        """Doc."""\n        ...\n'
    defaulted = "class P(Protocol):\n    def f(self, x: bool = True) -> None: ...\n"
    assert not _defines_mutable_runtime_protocol("@runtime_checkable\n" + stub)
    assert _defines_mutable_runtime_protocol("@runtime_checkable\n" + defaulted)
    assert _defines_mutable_runtime_protocol("@typing.runtime_checkable\n" + defaulted)
    assert not _defines_mutable_runtime_protocol(defaulted)
