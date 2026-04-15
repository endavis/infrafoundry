"""Tests for the ONTAP cluster console-restore role and blueprint wiring.

Covers issue #596: after the serial-setup role flips the ONTAP console
default to ``comconsole,vidconsole`` for the cluster setup automation,
the noVNC console becomes unusable. The console-restore role and its
matching ``ontap_restore_console`` blueprint input reverse the change
once the cluster is healthy.

Two test classes:

* ``TestConsoleRestoreTemplate`` renders the expect template offline and
  asserts the load-bearing strings (the ``set console=...`` line, the
  ``boot_ontap`` invocation, the log-file naming) and the absence of any
  serial-setup leakage (``SYS_SERIAL_NUM``, the inverted console order).
* ``TestConsoleRestoreBlueprintInput`` loads the ``ontap-cluster``
  blueprint via :class:`BlueprintResolver` and inspects the raw manifest
  to confirm the new input declaration (name, type, default).

Both classes are file-based and offline — no Ansible runtime, no live
ONTAP simulator.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT_DIR = REPO_ROOT / "blueprints" / "ontap-cluster"
ROLE_DIR = BLUEPRINT_DIR / "roles" / "ontap-console-restore"
TEMPLATE_DIR = ROLE_DIR / "templates"
BLUEPRINT_MANIFEST = BLUEPRINT_DIR / "blueprint.yaml"


class TestConsoleRestoreTemplate:
    """Render console-restore.exp.j2 and pin the load-bearing output."""

    @pytest.fixture
    def rendered(self) -> str:
        """Render the expect template with a minimal context."""
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            keep_trailing_newline=True,
            autoescape=False,
        )
        template = env.get_template("console-restore.exp.j2")
        return template.render(ontap_vmid=220, ontap_loader_timeout=300)

    def test_sets_video_primary_console(self, rendered: str) -> None:
        """The script sends exactly one ``set console=vidconsole,comconsole``."""
        assert rendered.count("set console=vidconsole,comconsole") == 1

    def test_invokes_boot_ontap(self, rendered: str) -> None:
        """The script issues ``boot_ontap`` to resume normal boot."""
        assert "boot_ontap" in rendered

    def test_log_file_includes_vmid(self, rendered: str) -> None:
        """The log_file directive embeds the VMID for per-node disambiguation."""
        assert "log_file" in rendered
        assert "ontap-console-restore-220-" in rendered

    def test_spawns_socat_on_correct_serial_socket(self, rendered: str) -> None:
        """socat targets the per-VM Proxmox serial socket."""
        assert "spawn socat" in rendered
        assert "qemu-server/220.serial0" in rendered

    def test_no_serial_setup_console_order(self, rendered: str) -> None:
        """Guard against regression to the serial-primary console order."""
        assert "comconsole,vidconsole" not in rendered

    def test_no_serial_or_sysid_mutation(self, rendered: str) -> None:
        """The restore role must not touch SYS_SERIAL_NUM or sysid."""
        assert "SYS_SERIAL_NUM" not in rendered
        assert "bootarg.nvram.sysid" not in rendered

    def test_loader_timeout_is_used(self, rendered: str) -> None:
        """The expect script honours the configured loader timeout."""
        assert "set timeout 300" in rendered

    def test_handles_halt_reboot_prompt(self, rendered: str) -> None:
        """After `system node halt` the simulator parks at a firmware-level
        'Please press any key to reboot' prompt (SRM_F_POWEROFF_VM). The
        script must match it and send a key so the VM reboots into VLOADER.
        """
        assert "Please press any key to reboot" in rendered
        assert "exp_continue" in rendered

    def test_pokes_serial_before_waiting(self, rendered: str) -> None:
        """The script must write to the serial line before expecting, so a
        VM that parked at the halt prompt before we attached still gets
        its prompt redrawn."""
        spawn_idx = rendered.index("spawn socat")
        first_expect_idx = rendered.index("expect {")
        between = rendered[spawn_idx:first_expect_idx]
        assert 'send "\\r"' in between or 'send "\\r"' in between


class TestConsoleRestoreBlueprintInput:
    """Verify ``ontap_restore_console`` is declared on the blueprint."""

    @pytest.fixture
    def resolved(self) -> dict[str, Any]:
        """Resolve the ontap-cluster blueprint via the production resolver."""
        # BlueprintResolver expects an envs/ path; the example-config envs
        # directory is fine here — we only care about the blueprint, not
        # any specific consuming package.
        envs_dir = REPO_ROOT / "example-config" / "envs"
        resolver = BlueprintResolver(envs_dir)
        return resolver.resolve("ontap-cluster")

    @pytest.fixture
    def manifest(self) -> dict[str, Any]:
        """Load the raw blueprint manifest YAML (preserves input metadata)."""
        with BLUEPRINT_MANIFEST.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        assert isinstance(data, dict), "blueprint manifest must be a mapping"
        return data

    def test_input_declared_in_resolver(self, resolved: dict[str, Any]) -> None:
        """The resolver exposes the input via its synthesized name set."""
        assert "ontap_restore_console" in resolved["input_names"]

    def test_default_is_true(self, resolved: dict[str, Any]) -> None:
        """Default flows through the resolver's defaults dict as boolean True."""
        assert resolved["defaults"]["ontap_restore_console"] is True

    def test_raw_manifest_declares_boolean_type(self, manifest: dict[str, Any]) -> None:
        """The raw manifest declares ``type: boolean`` for the input."""
        inputs = manifest["inputs"]
        matches = [entry for entry in inputs if entry.get("name") == "ontap_restore_console"]
        assert len(matches) == 1, "ontap_restore_console must be declared exactly once"
        entry = matches[0]
        assert entry["type"] == "boolean"
        assert entry["default"] is True
        assert entry.get("description"), "input must carry a description"
