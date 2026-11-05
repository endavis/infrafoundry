"""Guard: OPNsense API path literals live only in ``endpoints.py`` (#1239)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from infrafoundry.providers.opnsense import endpoints

_PACKAGE = Path(endpoints.__file__).parent
_STATIC_MODULES = (
    "core|firewall|interfaces|kea|unbound|routing|routes|radvd|cron|gdrivebackup|system|diagnostics"
)


def _path_pattern() -> re.Pattern[str]:
    first = {e.template.split("/")[0] for e in endpoints.registered_endpoints()}
    modules = "|".join(sorted(first | set(_STATIC_MODULES.split("|"))))
    return re.compile(rf"^/?(api/)?({modules})/[A-Za-z_]+")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def find_path_literals(source: str) -> list[str]:
    """Rule (a): string constants (and f-string parts) that look like API paths."""
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    pattern = _path_pattern()
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
        and pattern.match(node.value)
    ]


def find_inline_request_paths(source: str) -> list[int]:
    """Rule (b): ``x.request(method, <literal or f-string>)`` calls, by line number."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "request"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant | ast.JoinedStr | ast.BinOp)
    ]


def _sources() -> list[Path]:
    return [p for p in sorted(_PACKAGE.rglob("*.py")) if p.name != "endpoints.py"]


def test_no_path_literals_outside_the_registry() -> None:
    offenders = {
        str(p.relative_to(_PACKAGE)): hits
        for p in _sources()
        if (hits := find_path_literals(p.read_text()))
    }
    assert not offenders, f"move these paths into endpoints.py: {offenders}"


def test_requests_take_registry_paths() -> None:
    offenders = {
        str(p.relative_to(_PACKAGE)): lines
        for p in _sources()
        if (lines := find_inline_request_paths(p.read_text()))
    }
    assert not offenders, f"pass endpoints.X.path(...) to request(): {offenders}"


class TestGuardSelfTest:
    """The guard flags what it should and leaves docstrings and plain ratios alone."""

    def test_flags_literal_request_path(self) -> None:
        src = 'client.request("GET", "core/x/y")'
        assert find_inline_request_paths(src)
        assert find_path_literals(src) == ["core/x/y"]

    def test_flags_fstring_passed_to_request(self) -> None:
        src = 'self.client.request("POST", f"{base}/addRule")'
        assert find_inline_request_paths(src)

    def test_flags_module_constant(self) -> None:
        assert find_path_literals('_X = "firewall/alias"') == ["firewall/alias"]

    def test_ignores_docstrings(self) -> None:
        src = 'def f():\n    """Calls firewall/alias/searchItem."""\n    return 1\n'
        assert find_path_literals(src) == []

    def test_ignores_non_paths(self) -> None:
        src = 'x = f"{subnet}/{bits}"\nclient.request(method, endpoint)\n'
        assert find_path_literals(src) == []
        assert find_inline_request_paths(src) == []
