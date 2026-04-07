"""Integration test for the rocky9-template blueprint conversion.

Loads the real example-config package via PackageLoader and asserts that
the merged configuration (blueprint defaults + package overrides) produces
the expected resources. This is a regression guard for issue #503 and a
template for future blueprint conversions (#502, #504, #505, #506).

The test depends only on files checked into this repository:
  - blueprints/rocky9-template/         (the blueprint)
  - example-config/envs/dev/proxmox/rocky9-template/  (the example consumer)

It does NOT depend on the private endavis-infra/ config repo.
"""

import textwrap
from pathlib import Path

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "dev" / "proxmox" / "rocky9-template"


@pytest.fixture
def loader() -> PackageLoader:
    """PackageLoader pointed at the real example-config envs/ directory."""
    resolver = BlueprintResolver(EXAMPLE_ENVS)
    return PackageLoader(EXAMPLE_ENVS, blueprint_resolver=resolver)


def test_rocky9_example_package_loads_blueprint(loader: PackageLoader) -> None:
    """The rocky9-template example package loads via the blueprint resolver."""
    _resources, _events, variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    # --- Per-instance overrides come from the package manifest ---
    assert variables["vmid"] == 901
    assert variables["target_node"] == "pve1"
    assert variables["storage"] == "local-lvm"

    # --- Blueprint defaults flow through unchanged ---
    assert variables["template_name"] == "rocky9-template"
    assert variables["cores"] == 2
    assert variables["memory"] == 2048
    assert variables["disk_size"] == 32
    assert variables["bridge"] == "vmbr0"
    assert variables["ciuser"] == "rocky"
    assert variables["image_filename"] == "Rocky-9-GenericCloud-Base.latest.x86_64.qcow2"
    assert "rockylinux.org" in variables["image_url"]


def test_rocky9_example_renders_single_template_resource(loader: PackageLoader) -> None:
    """The merged config renders to exactly one proxmox template resource."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    assert len(resources) == 1
    resource = resources[0]
    assert resource.provider == "proxmox"
    assert resource.type == "template"
    assert resource.name == "rocky9-template"


def test_rocky9_example_resource_config_merges_defaults_and_overrides(
    loader: PackageLoader,
) -> None:
    """Rendered resource config combines blueprint defaults with package overrides."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    config = resources[0].config

    # Per-instance overrides
    assert config["vmid"] == 901
    assert config["target_node"] == "pve1"
    assert config["cloud_init_datastore"] == "local-lvm"
    assert config["disk"]["storage"] == "local-lvm"

    # Blueprint defaults
    assert config["name"] == "rocky9-template"
    assert config["cores"] == 2
    assert config["memory"] == 2048
    assert config["disk"]["size"] == 32
    assert config["network"]["bridge"] == "vmbr0"
    assert config["ciuser"] == "rocky"
    assert config["agent"] is True
    assert config["cloud_init"] is True
    assert config["tags"] == ["template", "rocky9"]
    assert config["download_image"]["filename"] == "Rocky-9-GenericCloud-Base.latest.x86_64.qcow2"
    assert "rockylinux.org" in config["download_image"]["url"]


def test_rocky9_blueprint_supports_multiple_instances(tmp_path: Path) -> None:
    """Two packages instantiating the same blueprint must produce distinct
    resources without colliding on the framework resource identifier.

    Regression guard for issue #511: the original PR #509 hardcoded the
    outer resource ``name`` instead of using the provider-centric shorthand
    format, which made multi-instance use impossible.
    """
    envs = tmp_path / "envs"
    pkg_a = envs / "test" / "proxmox" / "rocky9-a"
    pkg_b = envs / "test" / "proxmox" / "rocky9-b"
    pkg_a.mkdir(parents=True)
    pkg_b.mkdir(parents=True)

    (pkg_a / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: rocky9-a
            description: "Rocky 9 template instance A"
            blueprint: rocky9-template
            variables:
              template_name: rocky9-a
              vmid: 910
              target_node: pve1
              storage: local-lvm
            """
        )
    )
    (pkg_b / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: rocky9-b
            description: "Rocky 9 template instance B"
            blueprint: rocky9-template
            variables:
              template_name: rocky9-b
              vmid: 911
              target_node: pve2
              storage: local-lvm
            """
        )
    )

    resolver = BlueprintResolver(envs)
    loader = PackageLoader(envs, blueprint_resolver=resolver)

    resources_a, _, _ = loader.load_package(pkg_a, provider="proxmox", env_name="test")
    resources_b, _, _ = loader.load_package(pkg_b, provider="proxmox", env_name="test")

    assert len(resources_a) == 1
    assert len(resources_b) == 1

    # Framework identifiers must come from the per-instance template_name
    # so the two packages produce distinct resources.
    assert resources_a[0].name == "rocky9-a"
    assert resources_b[0].name == "rocky9-b"
    assert resources_a[0].name != resources_b[0].name

    # Per-instance config values flow through too.
    assert resources_a[0].config["vmid"] == 910
    assert resources_b[0].config["vmid"] == 911
    assert resources_a[0].config["target_node"] == "pve1"
    assert resources_b[0].config["target_node"] == "pve2"
