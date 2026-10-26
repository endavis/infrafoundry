"""Planning and running the install of unmet blueprint requirements (#1047)."""

from __future__ import annotations

import subprocess

import pytest

from infrafoundry.core.exceptions import RequirementInstallError
from infrafoundry.core.requirements.installer import InstallStep, plan_install, run_install
from infrafoundry.core.requirements.models import RequirementKind, RequirementStatus

PY = "/venv/bin/python"


def _unmet(kind: RequirementKind, name: str, *install_args: str) -> RequirementStatus:
    return RequirementStatus(
        kind=kind,
        name=name,
        wanted="",
        installed=None,
        satisfied=False,
        blueprints=("bp",),
        problem="not installed",
        fix="",
        install_args=install_args,
    )


def test_python_requirements_install_in_one_uv_step_into_the_given_interpreter() -> None:
    steps = plan_install(
        [
            _unmet(RequirementKind.PYTHON, "alpha", "alpha>=1"),
            _unmet(RequirementKind.PYTHON, "beta", "beta"),
        ],
        python_executable=PY,
    )

    assert steps == [
        InstallStep(
            kind=RequirementKind.PYTHON,
            command=("uv", "pip", "install", "--python", PY, "alpha>=1", "beta"),
            covers=("alpha", "beta"),
        )
    ]


def test_collections_install_from_their_requirements_file_once_per_file() -> None:
    steps = plan_install(
        [
            _unmet(RequirementKind.ANSIBLE_COLLECTION, "netapp.ontap", "/bp/requirements.yml"),
            _unmet(RequirementKind.ANSIBLE_COLLECTION, "netapp.um_info", "/bp/requirements.yml"),
        ]
    )

    assert steps == [
        InstallStep(
            kind=RequirementKind.ANSIBLE_COLLECTION,
            command=(
                "ansible-galaxy",
                "collection",
                "install",
                "--upgrade",
                "-r",
                "/bp/requirements.yml",
            ),
            covers=("netapp.ontap", "netapp.um_info"),
        )
    ]


def test_a_collection_without_a_requirements_file_installs_by_name() -> None:
    [step] = plan_install(
        [_unmet(RequirementKind.ANSIBLE_COLLECTION, "netapp.ontap", "netapp.ontap>=22.0.0")]
    )

    assert step.command == (
        "ansible-galaxy",
        "collection",
        "install",
        "--upgrade",
        "netapp.ontap>=22.0.0",
    )
    assert step.display() == "ansible-galaxy collection install --upgrade netapp.ontap>=22.0.0"


def test_python_steps_come_before_collection_steps() -> None:
    steps = plan_install(
        [
            _unmet(RequirementKind.ANSIBLE_COLLECTION, "netapp.ontap", "/bp/requirements.yml"),
            _unmet(RequirementKind.PYTHON, "alpha", "alpha>=1"),
        ],
        python_executable=PY,
    )

    assert [s.kind for s in steps] == [RequirementKind.PYTHON, RequirementKind.ANSIBLE_COLLECTION]


def test_nothing_unmet_plans_nothing() -> None:
    assert plan_install([]) == []


STEPS = plan_install(
    [
        _unmet(RequirementKind.PYTHON, "alpha", "alpha>=1"),
        _unmet(RequirementKind.ANSIBLE_COLLECTION, "netapp.ontap", "/bp/requirements.yml"),
    ],
    python_executable=PY,
)


class _Recorder:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if args[0] == self.fail_on:
            return subprocess.CompletedProcess(args, 2, stdout="", stderr="  boom  \n")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def test_run_install_runs_every_step_in_order() -> None:
    run = _Recorder()

    run_install(STEPS, run=run, which=lambda tool: f"/usr/bin/{tool}")

    assert run.calls == [list(step.command) for step in STEPS]


def test_a_missing_tool_stops_before_anything_runs() -> None:
    run = _Recorder()

    with pytest.raises(RequirementInstallError, match="ansible-galaxy not found on PATH") as exc:
        run_install(STEPS, run=run, which=lambda tool: None if tool == "ansible-galaxy" else tool)

    assert run.calls == []
    assert exc.value.context["missing_tools"] == ["ansible-galaxy"]


def test_a_failing_step_raises_with_its_output_and_stops() -> None:
    run = _Recorder(fail_on="uv")

    with pytest.raises(RequirementInstallError) as exc:
        run_install(STEPS, run=run, which=lambda tool: tool)

    assert str(exc.value).startswith(f"Install failed (exit 2): uv pip install --python {PY}")
    assert "\nboom" in str(exc.value)
    assert exc.value.context["exit_code"] == 2
    assert len(run.calls) == 1
