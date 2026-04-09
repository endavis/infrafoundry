"""Manifest text utilities.

Provides helpers that operate on the raw text of manifest files before
they are parsed as YAML.  The primary use case is extracting the raw
``inventory:`` block so it can be rendered through Jinja2 as a full
template (including ``{% for %}`` and ``{% if %}`` control flow) before
YAML parsing.  This is required because Jinja control-flow tags are not
valid YAML and cannot survive a ``yaml.safe_load`` pass.
"""

from __future__ import annotations

import textwrap

from infrafoundry.core.exceptions import InvalidConfigurationError

_INVENTORY_KEY = "inventory:"


def extract_inventory_block(file_text: str) -> tuple[str, str | None]:
    """Strip the top-level ``inventory:`` block from manifest text.

    Performs a line-based scan for a column-0 ``inventory:`` key.  When
    found, all subsequent indented (or blank/comment) lines are captured
    as the block body up to the next column-0 non-blank non-comment line
    (or EOF).  The leading ``inventory:`` line is removed from the
    captured body which is then de-dented with :func:`textwrap.dedent` so
    the caller receives a standalone YAML fragment.

    To keep YAML parser error messages pointing at correct original
    source lines, the captured slice in the returned ``text_without_inventory``
    is replaced with ``inventory: null`` followed by blank-line padding
    that preserves the original line count.

    A single-line flow-style declaration (``inventory: {groups: ...}``)
    is rejected with :class:`InvalidConfigurationError` because flow
    style cannot contain Jinja control-flow and the render-then-parse
    pipeline does not support it.

    This extractor is intentionally simple and is NOT safe for
    pathological input (e.g., a top-level key whose multi-line string
    value happens to contain a line starting with ``inventory:``).  The
    manifest format is well-defined and the loader is the only consumer.

    Args:
        file_text: Full raw text of the manifest file.

    Returns:
        A tuple ``(text_without_inventory, inventory_raw)`` where
        ``inventory_raw`` is the dedented body of the inventory block,
        or ``None`` when no ``inventory:`` block is present.

    Raises:
        InvalidConfigurationError: If the ``inventory:`` declaration
            uses flow style.
    """
    lines = file_text.splitlines(keepends=True)

    # Locate the column-0 ``inventory:`` line.
    start_idx: int | None = None
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        # Must start at column 0 (no leading whitespace) and match the key.
        if line.startswith(_INVENTORY_KEY):
            start_idx = idx
            break

    if start_idx is None:
        return file_text, None

    header_line = lines[start_idx]
    after_key = header_line[len(_INVENTORY_KEY) :].strip()

    # Reject flow-style single-line declarations.  A bare ``inventory:``
    # or ``inventory:  # comment`` is fine; anything else on the same
    # line means the value is inline.
    if after_key and not after_key.startswith("#"):
        raise InvalidConfigurationError(
            "Inventory declaration must use block style, not flow style. "
            "Use a multi-line 'inventory:' block with indented children."
        )

    # Capture body: subsequent lines that are blank, comment, or indented.
    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        line = lines[idx]
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        # A non-blank non-comment line at column 0 terminates the block.
        if not line[0].isspace():
            end_idx = idx
            break

    body_lines = lines[start_idx + 1 : end_idx]
    body_text = "".join(body_lines)
    inventory_raw = textwrap.dedent(body_text) if body_text else ""

    # Build replacement that preserves line numbers: ``inventory: null``
    # then (end_idx - start_idx - 1) blank lines.
    replacement_lines: list[str] = ["inventory: null\n"]
    replacement_lines.extend("\n" for _ in range(end_idx - start_idx - 1))
    # Handle final-line case where the header had no trailing newline.
    if not header_line.endswith("\n"):
        replacement_lines[0] = "inventory: null"
        if replacement_lines[1:]:
            replacement_lines[1] = "\n"

    new_lines = lines[:start_idx] + replacement_lines + lines[end_idx:]
    text_without_inventory = "".join(new_lines)

    return text_without_inventory, inventory_raw
