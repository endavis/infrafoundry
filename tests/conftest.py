"""Pytest fixtures and Hypothesis profiles for InfraFoundry tests."""

import os
import subprocess  # nosec B404 - guarding subprocess use, not invoking it
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
import yaml
from hypothesis import HealthCheck, settings

from infrafoundry.core.config import ConfigManager

Spec = dict[str, Any] | BaseException | Callable[[list[str]], MagicMock | BaseException]

# CI profile: fewer examples, no deadline.
#
# `deadline=None` rather than a larger number (#736). These are property tests
# over string validation — they assert what a value *is*, never how long it took,
# and `benchmark.yml` covers timing separately. A wall-clock budget on a shared
# runner only adds a way for them to fail for reasons unrelated to the property.
#
# Windows runners were seen taking 1506ms on an example's first call and 0.01ms
# on the retry: interpreter and import warmup, not the code under test. The
# earlier 200ms -> 500ms relaxation did not survive that, and any finite
# replacement is a threshold a bad runner can still cross.
#
# Note that `suppress_health_check=[HealthCheck.too_slow]` does *not* cover this.
# The health check and the per-example deadline are separate mechanisms, which is
# why the profile looked protected against slow runners while still failing on
# them.
settings.register_profile(
    "ci",
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.differing_executors],
)

# Default profile: more thorough exploration for local development.
# Keeps Hypothesis's default deadline — a developer machine is not a shared
# runner, so a genuinely pathological slowdown is worth surfacing locally.
settings.register_profile(
    "default",
    max_examples=200,
    suppress_health_check=[HealthCheck.differing_executors],
)

settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


@pytest.fixture
def mock_subprocess() -> Iterator[MagicMock]:
    """Patch ``tools.doit.github.subprocess.run`` with a prefix-dispatch mock.

    Register command-prefix -> spec mappings via ``.register({...})``. Spec is one
    of: a dict of MagicMock kwargs (``stdout``/``stderr``/``returncode``,
    default ``returncode=0``), a ``BaseException`` instance to raise, or a
    callable ``(cmd) -> MagicMock | BaseException`` for prefix collisions where
    behavior depends on a later argument. Unknown prefixes raise ``AssertionError``.
    """
    with patch("tools.doit.github.subprocess.run") as mock_run:
        dispatch: dict[tuple[str, ...], Spec] = {}

        def side_effect(cmd: list[str], *_a: object, **_kw: object) -> MagicMock:
            for prefix, spec in dispatch.items():
                if tuple(cmd[: len(prefix)]) == prefix:
                    if isinstance(spec, BaseException):
                        raise spec
                    if callable(spec):
                        result = spec(cmd)
                        if isinstance(result, BaseException):
                            raise result
                        return result
                    return MagicMock(
                        returncode=spec.get("returncode", 0),
                        stdout=spec.get("stdout", ""),
                        stderr=spec.get("stderr", ""),
                    )
            raise AssertionError(f"unexpected cmd: {cmd}")

        mock_run.side_effect = side_effect
        mock_run.register = dispatch.update
        yield mock_run


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config_manager(temp_dir: Path) -> Mock:
    """Create a mock ConfigManager with required attributes for Orchestrator tests."""
    config_manager = Mock(spec=ConfigManager)
    config_manager.base_dir = temp_dir
    config_manager.load_environment.return_value = None
    return config_manager


@pytest.fixture
def mock_config_dir(temp_dir: Path) -> Any:
    """Create a mock configuration directory structure."""
    config_dir = temp_dir / "config"
    config_dir.mkdir()

    # Create envs directory
    envs_dir = config_dir / "envs"
    envs_dir.mkdir()

    # Create dev environment
    dev_dir = envs_dir / "dev"
    dev_dir.mkdir()

    # Environment config
    env_config = {
        "name": "dev",
        "description": "Development environment",
        "variables": {"datacenter": "dc1", "network": "vmbr0"},
    }
    with open(dev_dir / "settings.yaml", "w") as f:
        yaml.dump(env_config, f)

    # Proxmox provider directory
    proxmox_dir = dev_dir / "proxmox"
    proxmox_dir.mkdir()

    # VM config
    vm_config = {
        "vm": [
            {
                "name": "test-vm-01",
                "template": "ubuntu-22.04",
                "cores": 2,
                "memory": 4096,
                "disk_size": 50,
            }
        ]
    }
    with open(proxmox_dir / "vm.yaml", "w") as f:
        yaml.dump(vm_config, f)

    # Resources directory (resource-centric format)
    resources_dir = dev_dir / "resources"
    resources_dir.mkdir()

    resource_config = {
        "resources": [
            {
                "provider": "proxmox",
                "type": "vm",
                "name": "web-server-01",
                "config": {
                    "template": "ubuntu-22.04",
                    "cores": 4,
                    "memory": 8192,
                    "disk_size": 100,
                },
            }
        ]
    }
    with open(resources_dir / "web-servers.yaml", "w") as f:
        yaml.dump(resource_config, f)

    return config_dir


@pytest.fixture
def mock_secrets_dir(temp_dir: Path) -> Any:
    """Create a mock secrets directory."""
    secrets_dir = temp_dir / "secrets"
    secrets_dir.mkdir()

    # Create unencrypted secrets for testing
    proxmox_secrets = {
        "proxmox": {"api_url": "https://proxmox.example.com:8006", "api_token": "test-token"}
    }
    with open(secrets_dir / "proxmox.yaml", "w") as f:
        yaml.dump(proxmox_secrets, f)

    return secrets_dir


@pytest.fixture
def mock_policy_dir(temp_dir: Path) -> Any:
    """Create a mock policy directory."""
    policy_dir = temp_dir / "policies"
    policy_dir.mkdir()

    # Resource limits policy
    resource_limits_file = {
        "policies": [
            {
                "name": "resource_limits",
                "type": "resource_limit",
                "description": "Enforce VM resource limits",
                "level": "warning",
                "rules": {
                    "limits": {
                        "max_cpu": 16,
                        "max_memory_mb": 65536,
                    }
                },
            }
        ]
    }
    with open(policy_dir / "resource_limits.yaml", "w") as f:
        yaml.dump(resource_limits_file, f)

    # Required tags policy
    required_tags_file = {
        "policies": [
            {
                "name": "require_tags",
                "type": "required_tags",
                "description": "Require tags on all resources",
                "level": "error",
                "rules": {"tags": ["environment", "owner", "project"]},
            }
        ]
    }
    with open(policy_dir / "require_tags.yaml", "w") as f:
        yaml.dump(required_tags_file, f)

    return policy_dir


@pytest.fixture
def mock_config() -> dict[str, Any]:
    """Create mock configuration data for orchestrator tests."""
    from unittest.mock import Mock

    # Mock environment
    environment = {
        "name": "dev",
        "description": "Development environment",
        "variables": {"datacenter": "dc1", "network": "vmbr0"},
    }

    # Mock resources
    resources = []
    for i in range(2):
        resource = Mock()
        resource.provider = "proxmox"
        resource.type = "vm"
        resource.name = f"web-0{i + 1}"
        resource.config = {"cores": 2, "memory": 4096}
        resource.hooks = None  # No lifecycle hooks configured
        resources.append(resource)

    return {"environment": environment, "resources": resources}


@pytest.fixture
def mock_terraform_state() -> dict[str, Any]:
    """Create a mock Terraform state."""
    return {
        "version": 4,
        "terraform_version": "1.6.0",
        "serial": 1,
        "lineage": "test-lineage",
        "outputs": {},
        "resources": [
            {
                "mode": "managed",
                "type": "proxmox_vm_qemu",
                "name": "test_vm_01",
                "provider": 'provider["registry.terraform.io/telmate/proxmox"]',
                "instances": [
                    {
                        "schema_version": 0,
                        "attributes": {
                            "id": "test-vm-01",
                            "name": "test-vm-01",
                            "cores": 2,
                            "memory": 4096,
                            "disk": {"size": 50, "storage": "local-lvm"},
                        },
                    }
                ],
            }
        ],
    }


@pytest.fixture
def mock_provider_config() -> dict[str, Any]:
    """Create a mock provider configuration."""
    return {
        "proxmox": {
            "api_url": "https://proxmox.example.com:8006",
            "api_token": "test-token",
            "node": "pve1",
        },
        "opnsense": {"api_url": "https://firewall.example.com", "api_key": "test-key"},
        "kubernetes": {
            "context": "test-cluster",
            "namespace": "default",
        },
    }


@pytest.fixture(autouse=True)
def _isolated_state_db(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Give every test its own state database instead of ``~/.infrafoundry/state.db``.

    ``StateManager()`` without a connection string falls back to
    ``~/.infrafoundry``, so tests that build a real ``Orchestrator`` left rows and
    deployment locks in the developer's database, and a stale lock from one run
    failed the next (#1110). The directory comes from ``tmp_path_factory`` so a
    test's own ``tmp_path`` stays empty. A test that sets these variables itself
    still wins, since its ``monkeypatch`` runs after this one.
    """
    monkeypatch.setenv("INFRAFOUNDRY_STATE_HOME", str(tmp_path_factory.mktemp("state-home")))
    monkeypatch.delenv("INFRAFOUNDRY_STATE_BACKEND", raising=False)
    monkeypatch.delenv("INFRAFOUNDRY_STATE_CONNECTION", raising=False)


@pytest.fixture
def mock_environment_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up mock environment variables."""
    monkeypatch.setenv("INFRAFOUNDRY_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ANSIBLE_HOST_KEY_CHECKING", "False")


@pytest.fixture
def sample_vm_resource() -> dict[str, Any]:
    """Sample VM resource configuration."""
    return {
        "name": "test-vm-01",
        "template": "ubuntu-22.04",
        "cores": 4,
        "memory": 8192,
        "disk_size": 100,
        "network": "vmbr0",
        "tags": {"environment": "dev", "owner": "team-infra"},
    }


@pytest.fixture
def sample_firewall_rule() -> dict[str, Any]:
    """Sample firewall rule configuration."""
    return {
        "name": "allow-http",
        "action": "pass",
        "interface": "wan",
        "protocol": "tcp",
        "source": "any",
        "destination": "web-servers",
        "port": 80,
    }


@pytest.fixture
def sample_k8s_deployment() -> dict[str, Any]:
    """Sample Kubernetes deployment configuration."""
    return {
        "name": "web-app",
        "replicas": 3,
        "image": "nginx:latest",
        "ports": [{"name": "http", "containerPort": 80}],
        "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}},
    }


# ---------------------------------------------------------------------------
# Hermetic PATH (#710)
# ---------------------------------------------------------------------------

# Unit tests were reaching the real `gh` binary 18 times per run — 14 of them
# `gh api user`, which is a *network* call. That makes results depend on whether
# the developer happens to be authenticated: #689 spent time diagnosing a 0.54pp
# coverage difference that turned out to be exactly this.
#
# Every test now runs with a stub `gh` ahead of the real one. It answers the
# handful of commands the code under test invokes with fixed output matching an
# unauthenticated CI runner, and exits 127 with a loud marker for anything else —
# so a new unmocked call fails visibly rather than depending on the machine.
#
# Tests needing specific `gh` behaviour prepend their own stub ahead of this one
# (see tests/test_statusline_gh_user.py::_stub_gh), which still works. Tests of
# Python code that shells out should mock `subprocess.run` instead; this fixture
# is the backstop for what slips through, and for shell scripts under test, which
# cannot be mocked at the Python level.
_GH_STUB_PY = """import sys

args = sys.argv[1:]
head = " ".join(args[:2])

if head == "auth status":
    # No token markers, so `_check_token_permissions` takes its else branch.
    # Both branches are pinned explicitly in test_setup_repo.py.
    print("Logged in to github.com as test-user", file=sys.stderr)
    sys.exit(0)

if head == "api user":
    # Unauthenticated: the statusline must render no user segment.
    print("gh: authentication required", file=sys.stderr)
    sys.exit(1)

if args[:1] == ["--version"]:
    print("gh version 0.0.0-stub (hermetic test stub)")
    sys.exit(0)

print(
    "HERMETIC-STUB: unmocked 'gh " + " ".join(args) + "' reached the real PATH (#710)",
    file=sys.stderr,
)
sys.exit(127)
"""


# Commands no test may reach through Python's subprocess. The PATH stub above
# covers shell scripts under test, but it cannot help on Windows: CreateProcess
# searches only `gh` and `gh.exe` and never consults PATHEXT for `.CMD`, so a
# Python-level `subprocess.run(["gh", ...])` would still find the real binary
# there. Failing the call outright makes hermeticity hold on every platform
# rather than on POSIX only (#710).
#
# Only `gh` is covered. `git` is invoked against tmp_path repositories where
# running the real binary is the point of the test, not a leak.
_UNMOCKED_COMMANDS = frozenset({"gh"})


@pytest.fixture(autouse=True)
def _no_unmocked_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test shells out to `gh` without mocking it."""
    real_run = subprocess.run

    def guarded(cmd: object, *args: object, **kwargs: object) -> object:
        if isinstance(cmd, (list, tuple)) and cmd and str(cmd[0]) in _UNMOCKED_COMMANDS:
            raise AssertionError(
                f"unmocked subprocess call to {list(cmd)!r}. Patch subprocess.run in "
                "the module under test — a real call makes the result depend on the "
                "developer's machine (#710)."
            )
        # Deliberately signature-agnostic: this forwards arbitrary calls, so it
        # cannot match subprocess.run's overload set.
        return real_run(cmd, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", guarded)


@pytest.fixture(autouse=True)
def _hermetic_path(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Put a stub `gh` ahead of the real one for every test.

    The dispatch lives in Python so there is one implementation; only the
    launcher differs per platform. Windows resolves executables through
    ``PATHEXT``, so an extensionless shell script named ``gh`` is not executable
    there — the first version of this fixture silently no-opped on Windows and
    the suite kept calling the real binary.

    Both launchers are written on Windows: ``gh.CMD`` for ``PATHEXT`` resolution,
    and an extensionless ``gh`` for the Git Bash used to run the shell scripts
    under test, which does not consult ``PATHEXT``.
    """
    bin_dir = tmp_path_factory.mktemp("hermetic-bin")
    (bin_dir / "_gh_stub.py").write_text(_GH_STUB_PY, encoding="utf-8")

    shim = bin_dir / "gh"
    shim.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/_gh_stub.py" "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)

    if os.name == "nt":
        (bin_dir / "gh.CMD").write_text(
            f'@echo off\r\n"{sys.executable}" "%~dp0_gh_stub.py" %*\r\n',
            encoding="utf-8",
        )

    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
