"""Template lookup for provider instances named ``<type>@<name>`` (#1462)."""

from __future__ import annotations

from pathlib import Path

from infrafoundry.providers.opnsense import OPNsenseProvider


def _provider(tmp_path: Path, firewall: str | None = None) -> OPNsenseProvider:
    return OPNsenseProvider(
        config_dir=tmp_path / "cfg", output_dir=tmp_path / "out", firewall=firewall
    )


def test_instance_template_dir_is_the_provider_type_dir(tmp_path: Path) -> None:
    assert _provider(tmp_path, "fw-b").template_dir == _provider(tmp_path).template_dir
    assert _provider(tmp_path, "fw-b").template_dir.parts[-2:] == ("opnsense", "templates")


def test_instance_renders_default_terraform_templates(tmp_path: Path) -> None:
    provider = _provider(tmp_path, "fw-b")
    provider.set_environment("dev")
    provider.generate_terraform([])
    out = tmp_path / "out" / "dev" / "terraform" / "opnsense@fw-b"
    assert "browningluke/opnsense" in (out / "provider.tf").read_text()
    assert (out / "variables.tf").exists()
    assert (out / "outputs.tf").exists()
