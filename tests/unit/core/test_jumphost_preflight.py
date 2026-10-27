"""Jumphost preflight checks run by ``infra doctor`` (#657)."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from infrafoundry.core import jumphost_preflight
from infrafoundry.core.jumphost_preflight import (
    REQUIRED_TOOLS,
    Status,
    Target,
    check_jumphost,
    deployment_state,
    jumphosts_to_check,
    output_checks,
    targets_by_jumphost,
)
from infrafoundry.core.known_hosts import RESERVATION_TYPE
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.state.models import ResourceState

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


def _reservation(hostname: str, ip: str) -> ResourceConfig:
    return ResourceConfig(
        name=f"{hostname}-dhcp",
        type=RESERVATION_TYPE,
        provider="opnsense",
        config={"hostname": hostname, "ip_address": ip},
        package_variables={"jumphost": JUMP},
    )


class TestTargetsByJumphost:
    def test_vm_with_reservation_is_a_target(self) -> None:
        vm, plain = _resource("vm1"), _resource("no-reservation")
        reservation = _reservation("vm1", "10.0.1.10")

        targets = targets_by_jumphost(
            [vm, plain, reservation], [vm, plain, reservation], lambda r: True
        )

        assert targets == {JUMP: [Target("vm1", "10.0.1.10", "ansible", True)]}

    def test_ssh_user_overrides_the_jumphost_user(self) -> None:
        vm = ResourceConfig(
            name="vm1",
            type="vm",
            provider="proxmox",
            config={},
            package_variables={"jumphost": "jump.example", "ssh_user": "admin"},
        )
        bare = ResourceConfig(
            name="vm2",
            type="vm",
            provider="proxmox",
            config={},
            package_variables={"jumphost": "jump.example"},
        )
        everything = [vm, bare, _reservation("vm1", "10.0.1.10"), _reservation("vm2", "10.0.1.11")]

        targets = targets_by_jumphost([vm, bare], everything, lambda r: False)

        assert [(t.name, t.user) for t in targets["jump.example"]] == [
            ("vm1", "admin"),
            ("vm2", None),
        ]


def _row(name: str, state: ResourceState, age_minutes: int) -> SimpleNamespace:
    created = datetime(2026, 1, 1, tzinfo=UTC) - timedelta(minutes=age_minutes)
    return SimpleNamespace(provider="proxmox", name=name, state=state, created_at=created)


class _State:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    def get_resources(self, environment: str | None = None) -> list[Any]:
        assert environment == "prod"
        return list(self.rows)


class TestDeploymentState:
    def test_newer_planned_rows_do_not_hide_a_deployment(self) -> None:
        """Every plan adds a planned row; it says nothing about what is deployed."""
        lookup = deployment_state(
            _State([_row("vm1", ResourceState.ACTIVE, 60), _row("vm1", ResourceState.PLANNED, 1)]),
            "prod",
        )

        assert lookup(_resource("vm1")) is True

    def test_newest_real_row_wins(self) -> None:
        lookup = deployment_state(
            _State([_row("vm1", ResourceState.ACTIVE, 60), _row("vm1", ResourceState.DELETED, 5)]),
            "prod",
        )

        assert lookup(_resource("vm1")) is False

    def test_untracked_and_planned_only_are_not_deployed(self) -> None:
        lookup = deployment_state(_State([_row("vm2", ResourceState.PLANNED, 1)]), "prod")

        assert lookup(_resource("vm1")) is False
        assert lookup(_resource("vm2")) is False

    def test_in_between_states_are_unknown(self) -> None:
        lookup = deployment_state(_State([_row("vm1", ResourceState.ERROR, 1)]), "prod")

        assert lookup(_resource("vm1")) is None


def _target_report(targets: list[Target], extra: list[str]) -> Any:
    run = _Run(_stdout() + "\n".join(extra) + "\n")
    report = check_jumphost(JUMP, [], targets, run=run)
    return report, run


class TestTargetChecks:
    def test_deployed_target_ssh_ok(self) -> None:
        target = Target("vm1", "10.0.1.10", "ansible", True)

        report, run = _target_report([target], ["target 0 ssh 0"])

        check = report.checks[-1]
        assert (check.name, check.status) == ("target vm1 (10.0.1.10)", Status.OK)
        assert "ansible@10.0.1.10 true" in run.calls[0][-1]
        assert "UserKnownHostsFile=/dev/null" in run.calls[0][-1]

    def test_deployed_target_ssh_failure_carries_the_reason(self) -> None:
        target = Target("vm1", "10.0.1.10", "ansible", True)

        report, _ = _target_report(
            [target],
            [
                "target 0 ssh 255",
                "target-error 0 ansible@10.0.1.10: Permission denied (publickey).",
            ],
        )

        check = report.checks[-1]
        assert check.status is Status.FAIL
        assert check.detail == (
            "ssh as ansible failed (exit 255): ansible@10.0.1.10: Permission denied (publickey)."
        )
        assert report.failed

    @pytest.mark.parametrize(
        ("route", "ping", "status", "detail"),
        [
            (0, 1, Status.OK, "not deployed; routable and unused"),
            (0, 0, Status.FAIL, "not deployed, but something answers at this IP"),
            (2, 1, Status.FAIL, "not deployed; no route from the jumphost"),
            (127, 1, Status.WARN, "not deployed; 'ip' missing on the jumphost"),
        ],
    )
    def test_undeployed_target(self, route: int, ping: int, status: Status, detail: str) -> None:
        target = Target("vm1", "10.0.1.10", "ansible", False)

        report, run = _target_report([target], [f"target 0 route {route}", f"target 0 ping {ping}"])

        assert (report.checks[-1].status, report.checks[-1].detail) == (status, detail)
        assert "ip route get 10.0.1.10" in run.calls[0][-1]
        assert "ssh -o BatchMode=yes -o ConnectTimeout=5" not in run.calls[0][-1]

    def test_unknown_state_and_missing_user_are_skipped(self) -> None:
        targets = [
            Target("vm1", "10.0.1.10", "ansible", None),
            Target("vm2", "10.0.1.11", None, True),
        ]

        report, run = _target_report(targets, [])

        assert [c.status for c in report.checks[-2:]] == [Status.SKIP, Status.SKIP]
        assert "10.0.1.10" not in run.calls[0][-1]
        assert "10.0.1.11" not in run.calls[0][-1]

    def test_target_values_are_shell_quoted(self) -> None:
        target = Target("vm1", "10.0.1.10; rm -rf ~", "ansible", False)

        _, run = _target_report([target], [])

        assert "ip route get '10.0.1.10; rm -rf ~'" in run.calls[0][-1]

    def test_undeployed_target_lines_run_in_a_real_shell(self) -> None:
        """Route and ping report through bash; 192.0.2.1 (TEST-NET-1) never answers."""
        lines = jumphost_preflight._target_lines([Target("vm1", "192.0.2.1", "ansible", False)])

        result = subprocess.run(
            ["bash", "-c", "; ".join(lines)], capture_output=True, text=True, check=False
        )

        kinds = [line.split()[2] for line in result.stdout.splitlines()]
        assert kinds == ["route", "ping"]


def _handler(dest: str, requires: str = "vm1") -> dict[str, Any]:
    return {"type": "script", "requires": [requires], "outputs": [{"source": dest, "dest": dest}]}


def _with_vars(**pkg_vars: Any) -> ResourceConfig:
    return ResourceConfig(
        name="vm1",
        type="vm",
        provider="proxmox",
        config={},
        package_variables={"jumphost": JUMP, **pkg_vars},
    )


class TestOutputChecks:
    def test_renders_and_accepts_a_creatable_destination(self, tmp_path: Path) -> None:
        resource = _with_vars(out_dir=str(tmp_path / "new" / "dir"))

        checks = output_checks([_handler("{{ out_dir }}/k.yaml")], [resource])

        check = checks[JUMP][0]
        assert check.name == f"output {tmp_path}/new/dir/k.yaml"
        assert check.status is Status.OK

    def test_existing_writable_file(self, tmp_path: Path) -> None:
        (tmp_path / "k.yaml").write_text("x")

        checks = output_checks([_handler(str(tmp_path / "k.yaml"))], [_with_vars()])

        assert (checks[JUMP][0].status, checks[JUMP][0].detail) == (Status.OK, "exists, writable")

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
    def test_unwritable_parent_warns(self, tmp_path: Path) -> None:
        locked = tmp_path / "locked"
        locked.mkdir(mode=0o500)

        try:
            checks = output_checks([_handler(str(locked / "sub" / "k.yaml"))], [_with_vars()])
        finally:
            locked.chmod(0o700)

        assert checks[JUMP][0].status is Status.WARN
        assert checks[JUMP][0].detail == f"{locked} is not a writable directory"

    def test_unrenderable_and_relative_destinations_warn(self) -> None:
        checks = output_checks(
            [_handler("{{ missing }}/k.yaml"), _handler("relative/k.yaml")], [_with_vars()]
        )

        assert [c.status for c in checks[JUMP]] == [Status.WARN, Status.WARN]
        assert "does not render" in checks[JUMP][0].detail
        assert checks[JUMP][1].detail == "not an absolute path"

    def test_out_of_scope_and_jumphostless_handlers_are_ignored(self, tmp_path: Path) -> None:
        local = ResourceConfig(name="vm2", type="vm", provider="proxmox", config={})
        dest = str(tmp_path / "k.yaml")

        checks = output_checks(
            [_handler(dest, requires="other"), _handler(dest, requires="vm2")],
            [_with_vars(), local],
        )

        assert checks == {}

    def test_same_destination_is_checked_once(self, tmp_path: Path) -> None:
        dest = str(tmp_path / "k.yaml")

        checks = output_checks([_handler(dest), _handler(dest)], [_with_vars()])

        assert len(checks[JUMP]) == 1
