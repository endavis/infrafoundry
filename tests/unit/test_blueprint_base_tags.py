"""The ``base_tags`` input of the ontap-cluster and opnsense-vm blueprints (#1303).

Loads packages through PackageLoader so the real ``vm.yaml`` renders with the
real blueprint defaults. ``base_tags`` defaults to the list each template used
to hardcode; ``extra_tags`` is still appended to it.
"""

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

BLUEPRINTS_DIR = Path(__file__).resolve().parents[2] / "blueprints"

ONTAP_VARIABLES = """\
cluster_name: ontap-demo
cluster_mgmt_ip: "172.20.99.80"
data_lif1_ip: "172.20.99.83"
data_lif2_ip: "172.20.99.84"
node01_name: ontap-node-1
node01_vmid: 1130
node01_target: node2
node01_mgmt_ip: "172.20.99.81"
node02_name: ontap-node-2
node02_vmid: 1131
node02_target: node3
node02_mgmt_ip: "172.20.99.82"
ontap_password: test-password
"""

OPNSENSE_VARIABLES = """\
vm_name: fw-demo
vmid: 951
target_node: node1
hostname: fw-demo
domain: lab.example.com
root_password: test-password
api_key: key123
api_secret: secret-456
wan_ip: "172.20.10.250"
lan_ip: "172.20.99.1"
"""


def _vm_tags(tmp_path: Path, blueprint: str, variables: str, extra: str) -> list[list[str]]:
    envs = tmp_path / "envs"
    package = envs / "test" / "proxmox" / "demo"
    package.mkdir(parents=True)
    (package / "infrafoundry.yml").write_text(
        f"name: demo\nblueprint: {blueprint}\nvariables:\n"
        + textwrap.indent(variables + extra, "  ")
    )
    loader = PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))
    resources, _events, _variables = loader.load_package(
        package, provider="proxmox", env_name="test"
    )
    return [r.config["tags"] for r in resources if r.type in ("vm", "ova_vm")]


@pytest.mark.unit
class TestOntapClusterBaseTags:
    """ontap-cluster renders ``base_tags + extra_tags`` on both nodes."""

    def test_unset_keeps_the_old_hardcoded_tags(self, tmp_path: Path) -> None:
        tags = _vm_tags(tmp_path, "ontap-cluster", ONTAP_VARIABLES, "")
        assert tags == [["ontap", "ontap-sim"]] * 2

    def test_extra_tags_still_append(self, tmp_path: Path) -> None:
        tags = _vm_tags(tmp_path, "ontap-cluster", ONTAP_VARIABLES, "extra_tags: [demo]\n")
        assert tags == [["ontap", "ontap-sim", "demo"]] * 2

    def test_base_tags_replace_the_default(self, tmp_path: Path) -> None:
        extra = "base_tags: [sim, lab]\nextra_tags: [demo]\n"
        tags = _vm_tags(tmp_path, "ontap-cluster", ONTAP_VARIABLES, extra)
        assert tags == [["sim", "lab", "demo"]] * 2


@pytest.mark.unit
class TestOpnsenseVmBaseTags:
    """opnsense-vm renders ``base_tags + extra_tags``."""

    def test_unset_keeps_the_old_hardcoded_tags(self, tmp_path: Path) -> None:
        tags = _vm_tags(tmp_path, "opnsense-vm", OPNSENSE_VARIABLES, "")
        assert tags == [["opnsense", "fw-test"]]

    def test_extra_tags_still_append(self, tmp_path: Path) -> None:
        tags = _vm_tags(tmp_path, "opnsense-vm", OPNSENSE_VARIABLES, "extra_tags: [x]\n")
        assert tags == [["opnsense", "fw-test", "x"]]

    def test_base_tags_replace_the_default(self, tmp_path: Path) -> None:
        extra = "base_tags: [fw-demo]\nextra_tags: [x]\n"
        tags = _vm_tags(tmp_path, "opnsense-vm", OPNSENSE_VARIABLES, extra)
        assert tags == [["fw-demo", "x"]]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("blueprint", "expected"),
    [("ontap-cluster", ["ontap", "ontap-sim"]), ("opnsense-vm", ["opnsense", "fw-test"])],
)
def test_blueprint_declares_base_tags_default(blueprint: str, expected: list[str]) -> None:
    text = (BLUEPRINTS_DIR / blueprint / "blueprint.yaml").read_text()
    data: dict[str, Any] = yaml.safe_load(text)
    by_name = {entry["name"]: entry for entry in data["inputs"] if "name" in entry}
    assert by_name["base_tags"]["default"] == expected
