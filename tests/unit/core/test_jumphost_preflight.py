"""Jumphost preflight checks run by ``infra doctor`` (#657)."""

from __future__ import annotations

import subprocess
from typing import Any

from infrafoundry.core import jumphost_preflight
from infrafoundry.core.jumphost_preflight import (
    REQUIRED_TOOLS,
    Status,
    check_jumphost,
    jumphosts_to_check,
)
from infrafoundry.core.provider import ResourceConfig

JUMP = "ansible@jump.example"
KEY_A = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKeyA ansible@ops"
KEY_B = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKeyB other@ops"


def _resource(
    name: str,
    jumphost: str = JUMP,
    ssh_public_key: str | None = None,
    ssh_keys: list[str] | None = None,
) -> ResourceConfig:
    pkg_vars: dict[str, Any] = {"jumphost": jumphost} if jumphost else {}
    if ssh_public_key is not None:
        pkg_vars["ssh_public_key"] = ssh_public_key
    config: dict[str, Any] = {"ssh_keys": ssh_keys} if ssh_keys is not None else {}
    return ResourceConfig(
        name=name, type="vm", provider="proxmox", config=config, package_variables=pkg_vars
    )


class TestJumphostsToCheck:
    def test_groups_by_jumphost_with_declared_keys(self) -> None:
        resources = [
            _resource("a", ssh_public_key=KEY_A),
            _resource("b", ssh_keys=[KEY_A, KEY_B]),
            _resource("c", jumphost="root@other.example"),
        ]

        assert jumphosts_to_check(resources) == {JUMP: [KEY_A, KEY_B], "root@other.example": []}

    def test_resources_without_jumphost_are_left_out(self) -> None:
        assert jumphosts_to_check([_resource("plain", jumphost="")]) == {}


def _stdout(
    agent: int = 0,
    keys: tuple[str, ...] = (KEY_A,),
    missing: tuple[str, ...] = (),
    tmp_ok: bool = True,
) -> str:
    lines = ["connect ok", f"agent {agent}", *(f"key {k}" for k in keys)]
    lines += [f"tool {t} {'missing' if t in missing else 'ok'}" for t in REQUIRED_TOOLS]
    lines.append("tmp ok" if tmp_ok else "tmp fail")
    return "\n".join(lines) + "\n"


class _Run:
    """Stand-in for ``subprocess.run`` that records each call."""

    def __init__(
        self, stdout: str = "", returncode: int = 0, stderr: str = "", exc: Exception | None = None
    ) -> None:
        self.stdout, self.returncode, self.stderr, self.exc = stdout, returncode, stderr, exc
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        assert kwargs["timeout"] > 0
        if self.exc:
            raise self.exc
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def _statuses(report: Any) -> dict[str, Status]:
    return {c.name: c.status for c in report.checks}


class TestCheckJumphost:
    def test_all_checks_pass_in_one_ssh_call(self) -> None:
        run = _Run(_stdout())

        report = check_jumphost(JUMP, [KEY_A], run=run)

        assert len(run.calls) == 1
        assert run.calls[0][0] == "ssh"
        assert "BatchMode=yes" in run.calls[0]
        assert run.calls[0][-2] == JUMP
        assert not report.failed
        assert _statuses(report) == {
            "SSH to jumphost": Status.OK,
            "ssh-agent": Status.OK,
            "key match: ansible@ops": Status.OK,
            "tools": Status.OK,
            "writable /tmp": Status.OK,
        }

    def test_key_match_ignores_the_comment(self) -> None:
        loaded = KEY_A.rsplit(" ", 1)[0] + " a-different-comment"

        report = check_jumphost(JUMP, [KEY_A], run=_Run(_stdout(keys=(loaded,))))

        assert _statuses(report)["key match: ansible@ops"] is Status.OK

    def test_loaded_keys_without_the_package_key_fail(self) -> None:
        report = check_jumphost(JUMP, [KEY_A], run=_Run(_stdout(keys=(KEY_B,))))

        assert report.failed
        assert _statuses(report)["key match: ansible@ops"] is Status.FAIL

    def test_no_declared_key_skips_the_match(self) -> None:
        report = check_jumphost(JUMP, [], run=_Run(_stdout()))

        assert _statuses(report)["key match"] is Status.SKIP
        assert not report.failed

    def test_agent_without_keys_fails(self) -> None:
        report = check_jumphost(JUMP, [KEY_A], run=_Run(_stdout(agent=1, keys=())))

        agent = next(c for c in report.checks if c.name == "ssh-agent")
        assert agent.status is Status.FAIL
        assert "no keys loaded" in agent.detail
        assert not any(c.name.startswith("key match") for c in report.checks)

    def test_unreachable_agent_fails_with_its_own_message(self) -> None:
        report = check_jumphost(JUMP, [KEY_A], run=_Run(_stdout(agent=2, keys=())))

        agent = next(c for c in report.checks if c.name == "ssh-agent")
        assert agent.status is Status.FAIL
        assert "no ssh-agent reachable" in agent.detail

    def test_missing_tools_and_tmp_fail(self) -> None:
        report = check_jumphost(
            JUMP, [KEY_A], run=_Run(_stdout(missing=("rsync", "python3"), tmp_ok=False))
        )

        tools = next(c for c in report.checks if c.name == "tools")
        assert tools.status is Status.FAIL
        assert tools.detail == "missing: rsync, python3"
        assert _statuses(report)["writable /tmp"] is Status.FAIL

    def test_unreachable_jumphost_is_the_only_check(self) -> None:
        run = _Run(returncode=255, stderr="ssh: connect to host jump.example: No route to host\n")

        report = check_jumphost(JUMP, [KEY_A], run=run)

        assert len(report.checks) == 1
        assert report.checks[0].status is Status.FAIL
        assert "255" in report.checks[0].detail
        assert "No route to host" in report.checks[0].detail

    def test_timeout_and_missing_ssh_fail(self) -> None:
        timeout = check_jumphost(JUMP, [], run=_Run(exc=subprocess.TimeoutExpired("ssh", 60)))
        missing = check_jumphost(JUMP, [], run=_Run(exc=FileNotFoundError("ssh")))

        assert "timed out" in timeout.checks[0].detail
        assert "could not run ssh" in missing.checks[0].detail
        assert timeout.failed and missing.failed


class TestRemoteScript:
    def test_script_output_parses_against_a_real_shell(self) -> None:
        """The remote script runs under bash and prints every tagged line."""
        result = subprocess.run(
            ["bash", "-c", jumphost_preflight._REMOTE_SCRIPT],
            capture_output=True,
            text=True,
            check=False,
        )

        tags = {line.split(" ", 1)[0] for line in result.stdout.splitlines()}
        assert {"connect", "agent", "tool", "tmp"} <= tags
        assert result.returncode == 0
