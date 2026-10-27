"""Destroyed hosts are removed from the package jumphost's ``known_hosts`` (#656)."""

from __future__ import annotations

import shlex
import subprocess
from typing import Any

from infrafoundry.core.known_hosts import RESERVATION_TYPE, forget_on_jumphost, hosts_to_forget
from infrafoundry.core.provider import ResourceConfig

JUMP = "ansible@jump.example"


def _vm(name: str, jumphost: str = JUMP) -> ResourceConfig:
    pkg_vars = {"jumphost": jumphost} if jumphost else {}
    return ResourceConfig(
        name=name, type="vm", provider="proxmox", config={}, package_variables=pkg_vars
    )


def _reservation(name: str, hostname: str, ip: str) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type=RESERVATION_TYPE,
        provider="opnsense",
        config={"hostname": hostname, "ip_address": ip},
        package_variables={"jumphost": JUMP},
    )


class TestHostsToForget:
    def test_vm_name_and_its_reservation_ip(self) -> None:
        vm = _vm("k3s-server")
        everything = [vm, _reservation("k3s-server-dhcp", "k3s-server", "10.0.1.10")]

        assert hosts_to_forget([vm], everything) == {JUMP: ["k3s-server", "10.0.1.10"]}

    def test_package_without_jumphost_is_skipped(self) -> None:
        vm = _vm("plain", jumphost="")

        assert hosts_to_forget([vm], [vm, _reservation("plain", "plain", "10.0.1.11")]) == {}

    def test_no_matching_reservation_gives_the_name_only(self) -> None:
        vm = _vm("oci-node")

        assert hosts_to_forget([vm], [vm]) == {JUMP: ["oci-node"]}

    def test_entries_are_deduplicated_across_resources(self) -> None:
        """aiqum names its reservation after the VM, so both may be destroyed."""
        vm = _vm("aiqum")
        reservation = _reservation("aiqum", "aiqum", "10.0.1.12")

        assert hosts_to_forget([vm, reservation], [vm, reservation]) == {
            JUMP: ["aiqum", "10.0.1.12"]
        }

    def test_each_jumphost_gets_its_own_list(self) -> None:
        a, b = _vm("a"), _vm("b", jumphost="root@other.example")

        assert hosts_to_forget([a, b], [a, b]) == {JUMP: ["a"], "root@other.example": ["b"]}


class _Run:
    """Stand-in for ``subprocess.run`` that records the call."""

    def __init__(self, returncode: int = 0, stderr: str = "", exc: Exception | None = None) -> None:
        self.returncode, self.stderr, self.exc = returncode, stderr, exc
        self.argv: list[str] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.argv = argv
        assert kwargs["timeout"] > 0
        if self.exc:
            raise self.exc
        return subprocess.CompletedProcess(argv, self.returncode, "", self.stderr)


class TestForgetOnJumphost:
    def test_one_ssh_call_removes_every_host(self) -> None:
        run = _Run()

        assert forget_on_jumphost(JUMP, ["vm1", "10.0.1.10"], run=run) is None

        assert run.argv[0] == "ssh"
        assert "BatchMode=yes" in run.argv
        assert run.argv[-2] == JUMP
        assert "ssh-keygen -R vm1 " in run.argv[-1]
        assert "ssh-keygen -R 10.0.1.10 " in run.argv[-1]

    def test_hosts_are_shell_quoted(self) -> None:
        run = _Run()

        forget_on_jumphost(JUMP, ["x; rm -rf ~"], run=run)

        assert f"ssh-keygen -R {shlex.quote('x; rm -rf ~')} " in run.argv[-1]

    def test_nothing_to_remove_makes_no_call(self) -> None:
        run = _Run()

        assert forget_on_jumphost(JUMP, [], run=run) is None
        assert run.argv == []

    def test_ssh_failure_is_returned_not_raised(self) -> None:
        run = _Run(returncode=255, stderr="ssh: connect to host jump.example: No route to host\n")

        error = forget_on_jumphost(JUMP, ["vm1"], run=run)

        assert error is not None
        assert "255" in error
        assert "No route to host" in error

    def test_timeout_and_missing_ssh_are_returned(self) -> None:
        timeout = _Run(exc=subprocess.TimeoutExpired("ssh", 60))
        missing = _Run(exc=FileNotFoundError("ssh"))

        assert "timed out" in (forget_on_jumphost(JUMP, ["vm1"], run=timeout) or "")
        assert "could not run ssh" in (forget_on_jumphost(JUMP, ["vm1"], run=missing) or "")
