"""Guard: every nosec and noqa in project-owned code names its IDs and a reason (#595).

Form: nosec IDs, then a second hash and the reason; noqa codes, then a second hash and the
reason. Only comment tokens are read, so a string literal mentioning a marker is ignored. The
scan covers the paths with no template counterpart: src, blueprints, tools/opnsense-parser.py,
tests/unit and tests/helpers.
"""

import io
import re
import tokenize
from pathlib import Path

# Markers are assembled so the template-shipped line scanners do not read the fixtures below.
NS = "# no" + "sec"
NQ = "# no" + "qa"
REPO_ROOT = Path(__file__).resolve().parents[2]

_NOSEC = re.compile(r"#\s*nosec\b(.*)$")
_NOQA = re.compile(r"#\s*noqa\b(.*)$")
_NOSEC_BODY = re.compile(r"((?:\s+B\d+)+)\s*(?:#\s*(\S.*))?")
_NOQA_BODY = re.compile(r":\s*([A-Z]+\d+(?:\s*,\s*[A-Z]+\d+)*)\s*(?:#\s*(\S.*))?")


def _bad_comment(comment: str) -> str | None:
    """Return a problem description for a malformed suppression comment, else None."""
    match = _NOSEC.search(comment)
    if match:
        body = _NOSEC_BODY.fullmatch(match.group(1).rstrip())
        if body is None:
            return "nosec needs test IDs only before the reason: `# nosec B123  # reason`"
        if not body.group(2):
            return "nosec has no reason: `# nosec B123  # reason`"
    match = _NOQA.search(comment)
    if match:
        body = _NOQA_BODY.fullmatch(match.group(1).rstrip())
        if body is None:
            return "noqa needs codes: `# noqa: E123  # reason`"
        if not body.group(2):
            return "noqa has no reason: `# noqa: E123  # reason`"
    return None


def _offenders(source: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            problem = _bad_comment(tok.string)
            if problem:
                found.append((tok.start[0], problem))
    return found


def test_detector_rejects_malformed_suppressions() -> None:
    bad = [
        f"x = 1  {NS}",
        f"x = 1  {NS} B105",
        f"x = 1  {NS} B105 - why",
        f"x = 1  {NQ}",
        f"x = 1  {NQ}: E402",
    ]
    for line in bad:
        assert _offenders(line), line


def test_detector_accepts_well_formed_suppressions() -> None:
    good = [
        f"x = 1  {NS} B105  # why",
        f"x = 1  {NS} B603 B607  # why",
        f"x = 1  {NQ}: F401  # why",
        f"x = 1  {NQ}: E402, F401  # why",
        "x = 1  # plain comment",
    ]
    for line in good:
        assert not _offenders(line), line


def test_detector_ignores_string_literals() -> None:
    assert not _offenders(f'x = "{NS}"\ny = "{NQ}"\n')


def _project_paths() -> list[Path]:
    paths: list[Path] = [REPO_ROOT / "tools" / "opnsense-parser.py"]
    for name in ("src", "blueprints", "tests/unit", "tests/helpers"):
        paths.extend((REPO_ROOT / name).rglob("*.py"))
    this_file = Path(__file__).resolve()
    return [p for p in paths if p.is_file() and p.resolve() != this_file]


def test_project_suppressions_name_ids_and_a_reason() -> None:
    offenders: list[str] = []
    for path in _project_paths():
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(REPO_ROOT)}:{line}: {problem}"
            for line, problem in _offenders(source)
        )
    assert not offenders, "\n".join(offenders)
