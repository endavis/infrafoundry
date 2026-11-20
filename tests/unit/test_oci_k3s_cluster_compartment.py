"""The k3s-cluster blueprint's optional OCI ``compartment`` input."""

from __future__ import annotations

import textwrap
from pathlib import Path

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader


def _load(tmp_path: Path, extra: str) -> list[tuple[str, dict[str, object]]]:
    envs = tmp_path / "envs"
    pkg = envs / "test" / "k3s-comp"
    pkg.mkdir(parents=True)
    body = textwrap.dedent(
        """\
        name: k3s-comp
        description: "k3s with a compartment"
        blueprint: k3s-cluster
        provider: oci
        variables:
          image: "ocid1.image.oc1.iad.example"
          ssh_public_key: "ssh-rsa AAAA"
        """
    )
    (pkg / "infrafoundry.yml").write_text(body + extra)
    loader = PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))
    resources, _events, _variables = loader.load_package(pkg, provider="oci", env_name="test")
    return [(r.type, r.config) for r in resources]


def test_compartment_absent_by_default(tmp_path: Path) -> None:
    """Without the input, no resource carries a compartment field."""
    resources = _load(tmp_path, "")
    assert resources
    assert all("compartment" not in config for _type, config in resources)


def test_compartment_set_on_every_resource(tmp_path: Path) -> None:
    """With the input, the VCN, subnets and instances all carry it."""
    resources = _load(tmp_path, '  compartment: "workload-comp"\n')
    types = {type_ for type_, _config in resources}
    assert types == {"vcn", "subnet", "instance"}
    assert all(config["compartment"] == "workload-comp" for _type, config in resources)
