"""Selecting the kubernetes cluster a resource belongs to, and normalizing it (#1539)."""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

import pytest
import yaml

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import DuplicateResourceNameError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

TWO_CLUSTERS = {
    "name": "dev",
    "providers": ["kubernetes"],
    "provider_settings": {
        "kubernetes": {
            "primary": "edge",
            "clusters": {
                "edge": {"kubeconfig_path": "/k/edge.yaml"},
                "cloud": {"kubeconfig_path": "/k/cloud.yaml"},
            },
        }
    },
}

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"


def _env(tmp_path: Path, settings: dict[str, object] | None = None) -> Path:
    env = tmp_path / "dev"
    (env / "kubernetes").mkdir(parents=True)
    (env / "settings.yaml").write_text(yaml.safe_dump(settings or TWO_CLUSTERS))
    return env


def _load(tmp_path: Path) -> list[ResourceConfig]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return ConfigManager(tmp_path).get_all_resources_all_providers("dev")


def _by_key(resources: list[ResourceConfig]) -> dict[tuple[str, str], str]:
    return {(r.name, r.type): r.provider for r in resources}


def test_entry_cluster_on_a_resource_centric_item(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "resources").mkdir()
    (env / "resources" / "r.yaml").write_text(
        "resources:\n"
        "  - {name: one, type: namespaces, provider: kubernetes, cluster: cloud, config: {}}\n"
        "  - {name: two, type: namespaces, provider: kubernetes, cluster: edge, config: {}}\n"
        "  - {name: three, type: namespaces, provider: kubernetes, config: {}}\n"
    )
    providers = _by_key(_load(tmp_path))
    assert providers[("one", "namespaces")] == "kubernetes@cloud"
    assert providers[("two", "namespaces")] == "kubernetes"  # primary, normalized
    assert providers[("three", "namespaces")] == "kubernetes"


def test_file_level_cluster_in_a_resource_centric_file(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "resources").mkdir()
    (env / "resources" / "r.yaml").write_text(
        "cluster: cloud\n"
        "resources:\n"
        "  - {name: one, type: namespaces, provider: kubernetes, config: {}}\n"
        "  - {name: vm1, type: vm, provider: proxmox, config: {}}\n"
        "  - {name: two, type: namespaces, provider: kubernetes, cluster: edge, config: {}}\n"
    )
    providers = _by_key(_load(tmp_path))
    assert providers[("one", "namespaces")] == "kubernetes@cloud"
    assert providers[("two", "namespaces")] == "kubernetes"
    assert providers[("vm1", "vm")] == "proxmox"


def test_file_level_cluster_in_a_provider_centric_file(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "kubernetes" / "namespaces.yaml").write_text(
        "cluster: cloud\nnamespaces:\n  - {name: one}\n  - {name: two, cluster: edge}\n"
    )
    providers = _by_key(_load(tmp_path))
    assert providers[("one", "namespaces")] == "kubernetes@cloud"
    assert providers[("two", "namespaces")] == "kubernetes"


def test_unselected_resources_stay_on_the_primary(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "kubernetes" / "namespaces.yaml").write_text("namespaces:\n  - {name: one}\n")
    assert {r.provider for r in _load(tmp_path)} == {"kubernetes"}


def test_entry_beats_file_beats_manifest_beats_primary(tmp_path: Path) -> None:
    env = _env(tmp_path)
    pkg = env / "kubernetes" / "apps"
    pkg.mkdir()
    (pkg / "infrafoundry.yml").write_text(
        "name: apps\nprovider: kubernetes\ncluster: cloud\nresources:\n"
        "  - namespaces-a.yaml\n  - namespaces-b.yaml\n"
    )
    (pkg / "namespaces-a.yaml").write_text("namespaces:\n  - {name: manifest-level}\n")
    (pkg / "namespaces-b.yaml").write_text("cluster: edge\nnamespaces:\n  - {name: file-level}\n")
    providers = _by_key(_load(tmp_path))
    assert providers[("manifest-level", "namespaces")] == "kubernetes@cloud"
    assert providers[("file-level", "namespaces")] == "kubernetes"


def test_same_name_on_two_clusters_is_allowed(tmp_path: Path) -> None:
    env = _env(tmp_path)
    for cluster in ("edge", "cloud"):
        (env / "kubernetes" / f"namespaces-{cluster}.yaml").write_text(
            f"cluster: {cluster}\nnamespaces:\n  - {{name: shared}}\n"
        )
    assert sorted(r.provider for r in _load(tmp_path)) == ["kubernetes", "kubernetes@cloud"]


def test_same_name_twice_on_one_cluster_is_a_duplicate(tmp_path: Path) -> None:
    env = _env(tmp_path)
    for index in (1, 2):
        (env / "kubernetes" / f"namespaces-{index}.yaml").write_text(
            "cluster: cloud\nnamespaces:\n  - {name: shared}\n"
        )
    with pytest.raises(DuplicateResourceNameError, match="kubernetes@cloud:shared"):
        _load(tmp_path)


def test_cluster_on_a_non_kubernetes_resource_raises(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "resources").mkdir()
    (env / "resources" / "r.yaml").write_text(
        "resources:\n  - {name: vm1, type: vm, provider: proxmox, cluster: cloud, config: {}}\n"
    )
    with pytest.raises(InvalidConfigurationError, match="only supported for provider"):
        _load(tmp_path)


def test_undeclared_cluster_raises(tmp_path: Path) -> None:
    env = _env(tmp_path)
    (env / "kubernetes" / "namespaces.yaml").write_text(
        "cluster: nope\nnamespaces:\n  - {name: one}\n"
    )
    with pytest.raises(InvalidConfigurationError, match="not declared under"):
        _load(tmp_path)


def test_manifest_selectors_stamp_only_their_own_family(tmp_path: Path) -> None:
    env = _env(
        tmp_path,
        {
            **TWO_CLUSTERS,
            "providers": ["kubernetes", "opnsense"],
            "provider_settings": {
                **TWO_CLUSTERS["provider_settings"],  # type: ignore[dict-item]
                "opnsense": {
                    "primary": "fw-a",
                    "firewalls": {"fw-a": {"api_url": "https://fw-a.example.com"}, "fw-b": {}},
                },
            },
        },
    )
    for key in ("firewall: fw-b", "cluster: cloud"):
        pkg = env / "kubernetes" / key.split(":")[0]
        pkg.mkdir(parents=True)
        (pkg / "infrafoundry.yml").write_text(
            f"name: pkg-{key.split(':')[0]}\nprovider: kubernetes\n{key}\nresources:\n  - r.yaml\n"
        )
        (pkg / "r.yaml").write_text(
            "resources:\n"
            "  - {name: ns, type: namespaces, provider: kubernetes, config: {}}\n"
            "  - {name: alias, type: alias, provider: opnsense, config: {type: host}}\n"
        )
    providers = {(r.name, r.provider) for r in _load(tmp_path)}
    assert ("ns", "kubernetes@cloud") in providers
    assert ("alias", "opnsense@fw-b") in providers
    # each package pins only its own family; the other family stays on its primary
    assert ("ns", "kubernetes") in providers
    assert ("alias", "opnsense") in providers


def test_environment_without_clusters_never_reads_the_settings(tmp_path: Path) -> None:
    env = tmp_path / "dev"
    (env / "kubernetes").mkdir(parents=True)  # no settings.yaml at all
    (env / "kubernetes" / "namespaces.yaml").write_text("namespaces:\n  - {name: one}\n")
    assert {r.provider for r in _load(tmp_path)} == {"kubernetes"}


def test_blueprint_package_is_pinned_by_the_manifest_cluster(tmp_path: Path) -> None:
    pkg = tmp_path / "dev" / "proxmox" / "minio"
    shutil.copytree(EXAMPLE_ENVS / "dev" / "proxmox" / "minio", pkg)
    manifest = pkg / "infrafoundry.yml"
    manifest.write_text(manifest.read_text() + "\ncluster: cloud\n")
    loader = PackageLoader(EXAMPLE_ENVS, blueprint_resolver=BlueprintResolver(EXAMPLE_ENVS))
    resources, _events, _variables = loader.load_package(pkg, provider="proxmox", env_name="dev")
    assert len(resources) == 5
    assert {r.provider for r in resources} == {"kubernetes@cloud"}
