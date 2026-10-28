"""Tests for the required ``ontap_password`` input (issue #1157).

A package that uses the ``ontap-cluster`` blueprint without an ``ontap_password``
secret used to pass ``infra doctor`` and ``plan`` and then send an empty password
over the serial console. The blueprint now declares the input ``required: true``,
the package loader enforces it, and the playbooks and expect template fail fast.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import InvalidConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT_DIR = REPO_ROOT / "blueprints" / "ontap-cluster"
SECRET_VALUE = "s3cr3t-value-do-not-leak"


def _loader_with_blueprint(envs_dir: Path, inputs: list[dict[str, Any]]) -> PackageLoader:
    resolver = BlueprintResolver(envs_dir)
    resolver.blueprints_dir = envs_dir.parent / "blueprints"
    bp_dir = resolver.blueprints_dir / "bp"
    bp_dir.mkdir(parents=True)
    (bp_dir / "blueprint.yaml").write_text(
        yaml.dump({"name": "bp", "inputs": inputs, "resources": ["vm.yaml"]})
    )
    (bp_dir / "vm.yaml").write_text("vm:\n  - name: node-01\n")
    return PackageLoader(envs_dir, blueprint_resolver=resolver)


def _package(
    envs_dir: Path, variables: dict[str, Any], secrets: dict[str, Any] | None = None
) -> Path:
    pkg = envs_dir / "dev" / "proxmox" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "infrafoundry.yml").write_text(
        yaml.dump({"name": "pkg", "blueprint": "bp", "variables": variables})
    )
    if secrets is not None:
        (pkg / "secrets.yaml").write_text(yaml.dump({"variables": secrets}))
    return pkg


@pytest.mark.unit
class TestLoaderEnforcesRequiredInputs:
    """PackageLoader rejects missing or empty required inputs."""

    @pytest.fixture
    def envs_dir(self, temp_dir: Path) -> Path:
        path = temp_dir / "envs"
        path.mkdir()
        return path

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_empty_value_raises(self, envs_dir: Path, value: Any) -> None:
        loader = _loader_with_blueprint(envs_dir, [{"name": "pw", "required": True}])
        pkg = _package(envs_dir, {"pw": value})
        with pytest.raises(InvalidConfigurationError) as exc:
            loader.load_package(pkg, "proxmox", "dev")
        assert "'pw'" in str(exc.value)
        assert "'pkg'" in str(exc.value)

    def test_missing_value_raises(self, envs_dir: Path) -> None:
        loader = _loader_with_blueprint(envs_dir, [{"name": "pw", "required": True}])
        pkg = _package(envs_dir, {})
        with pytest.raises(InvalidConfigurationError, match="missing required input 'pw'"):
            loader.load_package(pkg, "proxmox", "dev")

    def test_value_from_variables_passes(self, envs_dir: Path) -> None:
        loader = _loader_with_blueprint(envs_dir, [{"name": "pw", "required": True}])
        pkg = _package(envs_dir, {"pw": "x"})
        _, _, variables = loader.load_package(pkg, "proxmox", "dev")
        assert variables["pw"] == "x"

    def test_value_from_secrets_passes(self, envs_dir: Path) -> None:
        loader = _loader_with_blueprint(envs_dir, [{"name": "pw", "required": True}])
        pkg = _package(envs_dir, {}, secrets={"pw": SECRET_VALUE})
        _, _, variables = loader.load_package(pkg, "proxmox", "dev")
        assert variables["pw"] == SECRET_VALUE

    def test_error_does_not_contain_other_secret_values(self, envs_dir: Path) -> None:
        loader = _loader_with_blueprint(
            envs_dir, [{"name": "pw", "required": True}, {"name": "tok", "default": ""}]
        )
        pkg = _package(envs_dir, {}, secrets={"tok": SECRET_VALUE})
        with pytest.raises(InvalidConfigurationError) as exc:
            loader.load_package(pkg, "proxmox", "dev")
        assert SECRET_VALUE not in str(exc.value)


@pytest.mark.unit
class TestOntapBlueprintPassword:
    """The ontap-cluster blueprint wires the password check end to end."""

    def test_input_is_required_without_default(self) -> None:
        data = yaml.safe_load((BLUEPRINT_DIR / "blueprint.yaml").read_text())
        entry = next(i for i in data["inputs"] if i["name"] == "ontap_password")
        assert entry["required"] is True
        assert "default" not in entry

    @pytest.mark.parametrize(
        "playbook", ["ontap-lab-cluster-setup.yml", "ontap-lab-console-restore.yml"]
    )
    def test_playbook_asserts_before_any_role(self, playbook: str) -> None:
        plays = yaml.safe_load((BLUEPRINT_DIR / playbook).read_text())
        first = plays[0]
        assert first["hosts"] == "localhost"
        assert "roles" not in first
        task = first["tasks"][0]
        assert "ansible.builtin.assert" in task
        assert task["no_log"] is True
        assert "INFRAFOUNDRY_VAR_ontap_password" in str(task["ansible.builtin.assert"]["that"])

    def test_create_template_exits_on_password_mismatch(self) -> None:
        text = (
            BLUEPRINT_DIR / "roles" / "ontap-cluster-setup" / "templates" / "cluster-create.exp.j2"
        ).read_text()
        start = text.index('"Passwords do not match')
        assert "exit 1" in text[start : start + 200]
