"""``-h`` is a short alias for ``--help`` on every ``foundry`` command (#822)."""

from __future__ import annotations

from collections.abc import Iterator

import click
import pytest
from click.testing import CliRunner

from infrafoundry.cli import foundry


def _usage(args: list[str]) -> str:
    """Return the output of ``foundry <args>``, asserting it exited cleanly."""
    result = CliRunner().invoke(foundry, args)
    assert result.exit_code == 0, result.output
    return result.output


@pytest.mark.parametrize(
    "path",
    [
        [],
        ["infra"],
        ["config"],
        ["state"],
        ["secrets"],
        ["policy"],
        ["infra", "plan"],
        ["config", "doctor"],
    ],
    ids=lambda path: " ".join(["foundry", *path]),
)
def test_short_flag_prints_the_same_help_as_the_long_one(path: list[str]) -> None:
    short = _usage([*path, "-h"])

    assert short.startswith("Usage: ")
    assert short == _usage([*path, "--help"])


def _commands(ctx: click.Context) -> Iterator[click.Command]:
    """Yield every command under *ctx*'s command, depth first."""
    command = ctx.command
    yield command
    if isinstance(command, click.Group):
        for name in command.list_commands(ctx):
            sub = command.get_command(ctx, name)
            if sub is not None:
                yield from _commands(click.Context(sub, info_name=name, parent=ctx))


def test_no_command_takes_h_for_its_own_option() -> None:
    """An option spelled ``-h`` would shadow the help alias on that command."""
    root = click.Context(foundry, info_name="foundry")
    clashes = [
        f"{command.name}: {param.name}"
        for command in _commands(root)
        for param in command.params
        if isinstance(param, click.Option)
        and "-h" in param.opts + param.secondary_opts
        and not param.is_eager
    ]

    assert clashes == []
