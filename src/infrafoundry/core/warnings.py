"""File-based non-fatal warning collector for ``infra apply``.

Provides a tiny contract used by both Python framework code and blueprint
shell scripts to surface non-fatal abnormalities ("sysctl reported errors
but the params we care about did get set", "kubeconfig copied with one
warning", etc.) without swallowing them or burying them mid-log.

Contract:

- The framework creates a per-deployment temp file and exports its path via
  the ``INFRAFOUNDRY_WARNINGS_FILE`` environment variable before any event
  handlers run. Threads and subprocesses inherit it automatically (the
  script handler already does ``env = os.environ.copy()``; jumphost reexec
  explicitly re-exports it on the remote side).
- Emitters append one JSON object per line: ``{"source": ..., "message": ...}``.
  Shell scripts can ``echo '{"source":"x","message":"y"}' >> \
  "$INFRAFOUNDRY_WARNINGS_FILE"``; Python code calls :func:`emit_warning`.
- At the end of apply (in a ``finally`` block so failed applies still
  summarize), the framework reads the file via :func:`read_warnings` and
  renders a :class:`rich.panel.Panel` via :func:`render_warnings_panel`.

Secrets caveat:
    Warning messages are operator-readable via the panel and via the on-disk
    JSONL file (which lives in ``/tmp`` for the duration of the apply).
    **Do not put credentials, tokens, or raw secret material into warning
    messages** — redact them at the emit site, the same way you would for
    any log line.

Concurrency:
    :func:`emit_warning` uses :func:`fcntl.flock` for an exclusive lock
    before appending. POSIX ``O_APPEND`` is only guaranteed atomic up to
    ``PIPE_BUF`` (typically 4096 bytes), but warning messages from parallel
    apply threads can exceed that. The lock prevents interleaved writes.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger(__name__)

ENV_VAR = "INFRAFOUNDRY_WARNINGS_FILE"


def emit_warning(
    source: str,
    message: str,
    file_path: Path | str | None = None,
) -> None:
    """Append a non-fatal warning to the active warnings file.

    Args:
        source: Short identifier of who emitted the warning (e.g.
            ``"event:after_apply:notify"``, ``"provider:ontap"``).
        message: Human-readable warning text. Must not contain credentials.
        file_path: Explicit path to append to. When ``None`` (default), the
            path is taken from the ``INFRAFOUNDRY_WARNINGS_FILE`` environment
            variable. If both are unset, the call is a silent no-op so
            library callers (e.g. unit tests) don't pay for framework
            integration they aren't using.

    Notes:
        Uses an exclusive ``fcntl`` lock around the append to prevent
        interleaved writes from parallel threads emitting large messages.
        Errors opening or writing the file are logged at debug level and
        swallowed — a warning collector must not itself raise.
    """
    if file_path is None:
        env_value = os.environ.get(ENV_VAR)
        if not env_value:
            return
        target = Path(env_value)
    else:
        target = Path(file_path)

    record = json.dumps({"source": source, "message": message}) + "\n"

    try:
        # Open with O_APPEND so concurrent writers each seek to end before
        # writing; the flock serializes the write-then-flush against other
        # processes/threads using the same file.
        with open(target, "a", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.write(record)
                fh.flush()
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        logger.debug("failed to write warning to %s: %s", target, exc)


def read_warnings(file_path: Path | str) -> list[dict[str, str]]:
    """Read a warnings JSONL file and return its records.

    Args:
        file_path: Path to the warnings file.

    Returns:
        One dict per parseable line. Missing files and empty files both
        return ``[]``. Malformed JSON lines are logged at debug level and
        skipped so a single bad writer cannot break the summary.
    """
    target = Path(file_path)
    if not target.exists():
        return []

    try:
        content = target.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("failed to read warnings file %s: %s", target, exc)
        return []

    warnings_list: list[dict[str, str]] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            logger.debug("skipping malformed warning at %s:%d: %s", target, line_no, exc)
            continue
        if not isinstance(parsed, dict):
            logger.debug("skipping non-object warning at %s:%d", target, line_no)
            continue
        # Coerce known fields to strings defensively.
        warnings_list.append(
            {
                "source": str(parsed.get("source", "unknown")),
                "message": str(parsed.get("message", "")),
            }
        )
    return warnings_list


def render_warnings_panel(
    warnings_list: list[dict[str, str]],
    console: Console,
) -> None:
    """Render a yellow-bordered panel summarizing warnings.

    Args:
        warnings_list: Warning records from :func:`read_warnings`.
        console: Rich console to print the panel to.

    Notes:
        No-op when ``warnings_list`` is empty. Warnings are grouped by
        ``source`` so operators can see at a glance which handler or
        provider surfaced each abnormality.
    """
    if not warnings_list:
        return

    grouped: dict[str, list[str]] = defaultdict(list)
    for w in warnings_list:
        grouped[w.get("source", "unknown")].append(w.get("message", ""))

    body = Text()
    first = True
    for source, messages in grouped.items():
        if not first:
            body.append("\n")
        first = False
        body.append(f"{source}\n", style="bold yellow")
        for msg in messages:
            body.append(f"  - {msg}\n")

    title = f"⚠ Warnings ({len(warnings_list)})"
    console.print(
        Panel(
            body,
            title=title,
            title_align="left",
            border_style="yellow",
        )
    )
