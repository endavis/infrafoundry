"""Install unmet blueprint requirements (#1047).

Python packages go into the interpreter running InfraFoundry, the one the
preflight check inspects, through ``uv pip install --python <interpreter>``.
Ansible collections go through ``ansible-galaxy collection install --upgrade``.
Nothing here runs during ``infra plan``/``apply``/``destroy``; only ``foundry deps
sync`` calls it.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 - runs uv and ansible-galaxy with fixed argument lists
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from infrafoundry.core.exceptions import RequirementInstallError
from infrafoundry.core.requirements.models import RequirementKind, RequirementStatus

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]
Which = Callable[[str], str | None]


@dataclass(frozen=True)
class InstallStep:
    """One install command.

    Attributes:
        kind: What it installs
        command: The argument list it runs
        covers: Names of the requirements it installs
    """

    kind: RequirementKind
    command: tuple[str, ...]
    covers: tuple[str, ...]

    def display(self) -> str:
        """The command as a single line, for output."""
        return " ".join(self.command)


def plan_install(
    unmet: Iterable[RequirementStatus], python_executable: str = sys.executable
) -> list[InstallStep]:
    """Build the commands that install the given requirements.

    Args:
        unmet: Requirements to install
        python_executable: Interpreter that ``uv`` installs Python packages into

    Returns:
        One ``uv pip install`` step for every Python requirement, then one
        ``ansible-galaxy`` step per requirements file or loose collection
    """
    specs: list[str] = []
    python_names: list[str] = []
    collection_targets: dict[str, list[str]] = {}
    for status in unmet:
        if status.kind is RequirementKind.PYTHON:
            specs.extend(a for a in status.install_args if a not in specs)
            python_names.append(status.name)
        else:
            for target in status.install_args:
                collection_targets.setdefault(target, []).append(status.name)

    steps: list[InstallStep] = []
    if specs:
        steps.append(
            InstallStep(
                kind=RequirementKind.PYTHON,
                command=("uv", "pip", "install", "--python", python_executable, *specs),
                covers=tuple(python_names),
            )
        )
    for target, names in collection_targets.items():
        # A requirements file is an absolute path (the resolver resolves it);
        # a loose collection is "name<spec>".
        source = ("-r", target) if Path(target).is_absolute() else (target,)
        steps.append(
            InstallStep(
                kind=RequirementKind.ANSIBLE_COLLECTION,
                command=("ansible-galaxy", "collection", "install", "--upgrade", *source),
                covers=tuple(names),
            )
        )
    return steps


def run_install(
    steps: Iterable[InstallStep],
    run: Runner | None = None,
    which: Which = shutil.which,
) -> None:
    """Run install steps in order.

    Every tool is located before the first step runs, so a missing ``uv`` or
    ``ansible-galaxy`` changes nothing.

    Args:
        steps: Steps from :func:`plan_install`
        run: Runs one command; defaults to :func:`subprocess.run`
        which: Locates an executable

    Raises:
        RequirementInstallError: If a tool is missing or a step fails
    """
    steps = list(steps)
    missing = sorted({s.command[0] for s in steps if which(s.command[0]) is None})
    if missing:
        raise RequirementInstallError(
            f"Cannot install blueprint requirements: {', '.join(missing)} not found on PATH",
            context={"missing_tools": missing},
        )
    runner = run or _run
    for step in steps:
        result = runner(list(step.command))
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RequirementInstallError(
                f"Install failed (exit {result.returncode}): {step.display()}"
                + (f"\n{detail}" if detail else ""),
                context={"command": list(step.command), "exit_code": result.returncode},
            )


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - fixed argument list, no shell
        args, capture_output=True, text=True, check=False, timeout=900
    )
