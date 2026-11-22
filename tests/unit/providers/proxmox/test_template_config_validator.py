"""Unit tests for Proxmox TemplateConfigValidator (#1188) and template rendering (#1190)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox import ProxmoxProvider
from infrafoundry.providers.proxmox.validators.context import ProxmoxConfigContext
from infrafoundry.providers.proxmox.validators.template_config_validator import (
    TemplateConfigValidator,
)


def _tpl(name: str = "tpl", **config: Any) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="template",
        provider="proxmox",
        config={"name": name, "target_node": "pve01", **config},
    )


def _dl(filename: Any) -> dict[str, Any]:
    return {"download_image": {"url": "https://x/y", "filename": filename}}


@pytest.fixture
def report() -> MagicMock:
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def provider(tmp_path: Path) -> ProxmoxProvider:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = ProxmoxProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


class TestDownloadFilename:
    @pytest.mark.parametrize(
        "filename",
        ["a.qcow2", "a.raw", "a.vmdk", "a.ova", "a.ovf", "A.QCOW2", "Ubuntu.Raw"],
    )
    def test_accepted(self, report: MagicMock, filename: str) -> None:
        TemplateConfigValidator(report).validate(
            ProxmoxConfigContext(templates=[_tpl(**_dl(filename))])
        )
        report.add_check.assert_not_called()

    def test_img_rejected_with_hint(self, report: MagicMock) -> None:
        TemplateConfigValidator(report).validate(
            ProxmoxConfigContext(templates=[_tpl(**_dl("noble.img"))])
        )
        kwargs = report.add_check.call_args.kwargs
        assert kwargs["passed"] is False
        assert kwargs["level"] == ValidationLevel.ERROR
        assert "'tpl'" in kwargs["message"]
        assert "noble.img" in kwargs["message"]
        assert "noble.qcow2" in kwargs["message"]

    def test_other_extension_rejected_without_hint(self, report: MagicMock) -> None:
        TemplateConfigValidator(report).validate(
            ProxmoxConfigContext(templates=[_tpl(**_dl("a.iso"))])
        )
        kwargs = report.add_check.call_args.kwargs
        assert kwargs["passed"] is False
        assert "try" not in kwargs["message"]
        assert ".vmdk" in kwargs["message"]

    @pytest.mark.parametrize("filename", [None, "", "   "])
    def test_missing_filename(self, report: MagicMock, filename: Any) -> None:
        TemplateConfigValidator(report).validate(
            ProxmoxConfigContext(templates=[_tpl(**_dl(filename))])
        )
        kwargs = report.add_check.call_args.kwargs
        assert kwargs["passed"] is False
        assert "required" in kwargs["message"]

    def test_no_download_image_ignored(self, report: MagicMock) -> None:
        TemplateConfigValidator(report).validate(
            ProxmoxConfigContext(templates=[_tpl(clone={"source": "x"})])
        )
        report.add_check.assert_not_called()


class TestProviderWiring:
    def test_bad_template_raises(self, provider: ProxmoxProvider) -> None:
        with pytest.raises(SchemaValidationError, match=r"noble\.img"):
            provider._validate_resource_configs({"template": [_tpl(**_dl("noble.img"))]})

    def test_good_template_passes(self, provider: ProxmoxProvider) -> None:
        provider._validate_resource_configs({"template": [_tpl(**_dl("noble.qcow2"))]})


class TestCloudInitDatastoreRendering:
    @staticmethod
    def _render(provider: ProxmoxProvider, **cfg: Any) -> str:
        config: dict[str, Any] = {
            "name": "tpl",
            "target_node": "pve01",
            "vmid": 9000,
            "cloud_init": True,
            "download_image": {"url": "https://x/y", "filename": "y.qcow2"},
            "disk": {"storage": "tank"},
            "network": {"bridge": "vmbr0"},
            **cfg,
        }
        res = ResourceConfig(name="tpl", type="template", provider="proxmox", config=config)
        return provider.render_template("proxmox/templates.tf.j2", {"templates": [res]})

    def test_defaults_to_disk_storage(self, provider: ProxmoxProvider) -> None:
        content = self._render(provider)
        init = content.split("initialization {", 1)[1]
        assert 'datastore_id = "tank"' in init.split("ip_config", 1)[0]

    def test_explicit_value_used(self, provider: ProxmoxProvider) -> None:
        content = self._render(provider, cloud_init_datastore="fast")
        init = content.split("initialization {", 1)[1]
        assert 'datastore_id = "fast"' in init.split("ip_config", 1)[0]


def _tpl_import(import_id: str | None, name: str = "tpl", **config: Any) -> ResourceConfig:
    res = _tpl(name, **config)
    res.import_id = import_id
    return res


class TestImportId:
    _DL: ClassVar[dict[str, Any]] = {
        "vmid": 9000,
        "download_image": {"url": "https://x/y", "filename": "y.qcow2"},
    }

    def test_valid_no_check(self, report: MagicMock) -> None:
        tpl = _tpl_import("pve01/9000", **self._DL)
        TemplateConfigValidator(report).validate(ProxmoxConfigContext(templates=[tpl]))
        report.add_check.assert_not_called()

    @pytest.mark.parametrize("value", ["9000", "pve01/abc", "pve01/9001", "pve02/9000"])
    def test_invalid_errors(self, report: MagicMock, value: str) -> None:
        tpl = _tpl_import(value, **self._DL)
        TemplateConfigValidator(report).validate(ProxmoxConfigContext(templates=[tpl]))
        report.add_check.assert_called_once()
        kwargs = report.add_check.call_args.kwargs
        assert kwargs["check_name"] == "proxmox_template_tpl_import_id"
        assert kwargs["passed"] is False
        assert kwargs["level"] == ValidationLevel.ERROR

    def test_absent_adds_no_check(self, report: MagicMock) -> None:
        TemplateConfigValidator(report).validate(ProxmoxConfigContext(templates=[_tpl(**self._DL)]))
        report.add_check.assert_not_called()

    def test_generate_terraform_rejects_malformed(self, provider: ProxmoxProvider) -> None:
        with pytest.raises(SchemaValidationError, match="import_id"):
            provider.generate_terraform([_tpl_import("9000", **self._DL)])


class TestImportRendering:
    _CLONE: ClassVar[dict[str, Any]] = {"vmid": 9000, "clone": 100}
    _DL: ClassVar[dict[str, Any]] = {
        "vmid": 9000,
        "download_image": {"url": "https://x/y", "filename": "y.qcow2"},
        "disk": {"storage": "tank"},
        "network": {"bridge": "vmbr0"},
    }

    @staticmethod
    def _generate(provider: ProxmoxProvider, tpl: ResourceConfig) -> str:
        provider.generate_terraform([tpl])
        return (provider.terraform_dir / "templates.tf").read_text()

    @pytest.mark.parametrize("config", [_DL, _CLONE], ids=["download_image", "clone"])
    def test_one_import_block(self, provider: ProxmoxProvider, config: dict[str, Any]) -> None:
        tpl = _tpl_import("pve01/9000", name="tpl-a", **config)
        content = self._generate(provider, tpl)
        assert content.count("import {") == 1
        assert (
            'import {\n  to = proxmox_virtual_environment_vm.template_tpl_a\n  id = "pve01/9000"\n}'
        ) in content

    def test_download_file_not_imported(self, provider: ProxmoxProvider) -> None:
        content = self._generate(provider, _tpl_import("pve01/9000", **self._DL))
        assert "to = proxmox_virtual_environment_download_file" not in content

    @pytest.mark.parametrize("config", [_DL, _CLONE], ids=["download_image", "clone"])
    def test_absent_no_import_and_same_render(
        self, provider: ProxmoxProvider, config: dict[str, Any]
    ) -> None:
        without = provider.render_template(
            "proxmox/templates.tf.j2", {"templates": [_tpl_import(None, **config)]}
        )
        assert "import {" not in without
        assert without == provider.render_template(
            "proxmox/templates.tf.j2", {"templates": [_tpl(**config)]}
        )
