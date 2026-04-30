"""Unit tests for the VLAN direct-API spike (``tools/spikes/vlan_direct_api.py``).

These tests cover env-var loading, YAML parsing/validation, the diff engine,
the typed-surface fallback path, and the apply-loop dry-run guard. No live
OPNsense box is contacted — ``OPNsenseClient`` is patched at the spike
module's import path, mirroring the inline ``unittest.mock.patch()`` pattern
in ``tests/unit/providers/opnsense/test_dhcpv6_change_detection.py:165-167``.

Live-box validation is operator-driven and recorded in
``docs/development/opnsense-spike-vlan-findings.md``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# The spike module lives under ``tools/spikes/`` which is already on sys.path
# (see ``tests/unit/test_blueprint_portability_lint.py`` which imports from
# ``tools.lint_blueprint_portability`` the same way).
from tools.spikes import vlan_direct_api as spike

# Module path used by ``patch(...)`` to substitute the OPNsense client class
# *as imported by the spike*. Patching ``opnsense_openapi.OPNsenseClient``
# directly would not affect the already-bound name inside the spike module.
SPIKE_CLIENT_PATH = "tools.spikes.vlan_direct_api.OPNsenseClient"


# ---------------------------------------------------------------------------
# load_env_credentials
# ---------------------------------------------------------------------------


class TestLoadEnvCredentials:
    """Env var resolution into a ``Credentials`` dataclass."""

    def test_happy_path_all_set(self) -> None:
        env = {
            "OPNSENSE_API_URL": "https://fw.example.lan",
            "OPNSENSE_API_KEY": "key-123",
            "OPNSENSE_API_SECRET": "secret-456",
            "OPNSENSE_VERIFY_SSL": "true",
        }
        creds = spike.load_env_credentials(env)
        assert creds.api_url == "https://fw.example.lan"
        assert creds.api_key == "key-123"
        assert creds.api_secret == "secret-456"
        assert creds.verify_ssl is True

    def test_missing_api_key_raises(self) -> None:
        env = {
            "OPNSENSE_API_URL": "https://fw",
            "OPNSENSE_API_SECRET": "secret",
        }
        with pytest.raises(RuntimeError) as exc_info:
            spike.load_env_credentials(env)
        # Error message must name the missing var so the operator can fix it.
        assert "OPNSENSE_API_KEY" in str(exc_info.value)

    def test_missing_multiple_vars_lists_all(self) -> None:
        env: dict[str, str] = {}
        with pytest.raises(RuntimeError) as exc_info:
            spike.load_env_credentials(env)
        msg = str(exc_info.value)
        assert "OPNSENSE_API_URL" in msg
        assert "OPNSENSE_API_KEY" in msg
        assert "OPNSENSE_API_SECRET" in msg

    def test_empty_string_treated_as_missing(self) -> None:
        env = {
            "OPNSENSE_API_URL": "",
            "OPNSENSE_API_KEY": "k",
            "OPNSENSE_API_SECRET": "s",
        }
        with pytest.raises(RuntimeError) as exc_info:
            spike.load_env_credentials(env)
        assert "OPNSENSE_API_URL" in str(exc_info.value)

    def test_verify_ssl_default_when_unset(self) -> None:
        env = {
            "OPNSENSE_API_URL": "https://fw",
            "OPNSENSE_API_KEY": "k",
            "OPNSENSE_API_SECRET": "s",
        }
        creds = spike.load_env_credentials(env)
        assert creds.verify_ssl is True

    @pytest.mark.parametrize("falsey", ["false", "False", "0", "no", "off", "OFF"])
    def test_verify_ssl_falsey_values(self, falsey: str) -> None:
        env = {
            "OPNSENSE_API_URL": "https://fw",
            "OPNSENSE_API_KEY": "k",
            "OPNSENSE_API_SECRET": "s",
            "OPNSENSE_VERIFY_SSL": falsey,
        }
        creds = spike.load_env_credentials(env)
        assert creds.verify_ssl is False


# ---------------------------------------------------------------------------
# load_vlans_from_yaml
# ---------------------------------------------------------------------------


class TestLoadVlansFromYaml:
    """YAML parsing + per-field validation."""

    def test_valid_yaml_parses(self, tmp_path: Path) -> None:
        path = tmp_path / "vlans.yaml"
        path.write_text(
            """
- provider: opnsense
  type: vlan
  name: vlan-storage
  config:
    device: igb1
    tag: 100
    description: storage
    priority: 0
""",
            encoding="utf-8",
        )
        result = spike.load_vlans_from_yaml(path)
        assert len(result) == 1
        assert result[0].name == "vlan-storage"
        assert result[0].device == "igb1"
        assert result[0].tag == 100
        assert result[0].description == "storage"
        assert result[0].priority == 0

    def test_non_vlan_resources_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "mixed.yaml"
        path.write_text(
            """
- provider: opnsense
  type: vlan
  name: v1
  config: {device: igb0, tag: 10, description: a, priority: 0}
- provider: opnsense
  type: alias
  name: irrelevant
  config: {}
""",
            encoding="utf-8",
        )
        result = spike.load_vlans_from_yaml(path)
        assert len(result) == 1
        assert result[0].name == "v1"

    def test_top_level_not_list_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("provider: opnsense\n", encoding="utf-8")
        with pytest.raises(ValueError, match="top-level list"):
            spike.load_vlans_from_yaml(path)

    def test_missing_required_field(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.yaml"
        path.write_text(
            """
- provider: opnsense
  type: vlan
  name: v1
  config:
    device: igb0
    tag: 10
    description: a
""",  # priority missing
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="priority"):
            spike.load_vlans_from_yaml(path)

    def test_tag_out_of_range(self, tmp_path: Path) -> None:
        path = tmp_path / "bad-tag.yaml"
        path.write_text(
            """
- provider: opnsense
  type: vlan
  name: v1
  config: {device: igb0, tag: 5000, description: a, priority: 0}
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="tag 5000"):
            spike.load_vlans_from_yaml(path)

    def test_priority_out_of_range(self, tmp_path: Path) -> None:
        path = tmp_path / "bad-pcp.yaml"
        path.write_text(
            """
- provider: opnsense
  type: vlan
  name: v1
  config: {device: igb0, tag: 10, description: a, priority: 9}
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="priority 9"):
            spike.load_vlans_from_yaml(path)

    def test_non_integer_tag(self, tmp_path: Path) -> None:
        path = tmp_path / "non-int.yaml"
        path.write_text(
            """
- provider: opnsense
  type: vlan
  name: v1
  config: {device: igb0, tag: "not-an-int", description: a, priority: 0}
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="non-integer"):
            spike.load_vlans_from_yaml(path)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def _vlan(device: str, tag: int, desc: str = "x", pcp: int = 0) -> spike.VlanConfig:
    return spike.VlanConfig(
        name=f"vlan-{device}-{tag}",
        device=device,
        tag=tag,
        description=desc,
        priority=pcp,
    )


def _live(uuid: str, device: str, tag: int, desc: str = "x", pcp: int = 0) -> spike.LiveVlan:
    return spike.LiveVlan(uuid=uuid, device=device, tag=tag, description=desc, priority=pcp)


class TestComputeDiff:
    """``compute_diff`` keyed by ``(device, tag)``."""

    def test_no_changes_when_desired_matches_current(self) -> None:
        desired = [_vlan("igb0", 10, "storage", 0)]
        current = [_live("u1", "igb0", 10, "storage", 0)]
        diff = spike.compute_diff(desired, current)
        assert diff.is_empty
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []

    def test_add_only(self) -> None:
        desired = [_vlan("igb0", 10)]
        current: list[spike.LiveVlan] = []
        diff = spike.compute_diff(desired, current)
        assert len(diff.adds) == 1
        assert len(diff.updates) == 0
        assert len(diff.deletes) == 0
        assert diff.adds[0].diff_key == ("igb0", 10)

    def test_remove_only(self) -> None:
        desired: list[spike.VlanConfig] = []
        current = [_live("u1", "igb0", 10)]
        diff = spike.compute_diff(desired, current)
        assert len(diff.adds) == 0
        assert len(diff.updates) == 0
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"

    def test_update_only_when_description_differs(self) -> None:
        desired = [_vlan("igb0", 10, desc="new-desc")]
        current = [_live("u1", "igb0", 10, desc="old-desc")]
        diff = spike.compute_diff(desired, current)
        assert len(diff.adds) == 0
        assert len(diff.updates) == 1
        assert len(diff.deletes) == 0
        live, want = diff.updates[0]
        assert live.uuid == "u1"
        assert want.description == "new-desc"

    def test_update_only_when_priority_differs(self) -> None:
        desired = [_vlan("igb0", 10, pcp=3)]
        current = [_live("u1", "igb0", 10, pcp=0)]
        diff = spike.compute_diff(desired, current)
        assert len(diff.updates) == 1

    def test_diff_keypair_is_device_tag_not_name_or_uuid(self) -> None:
        # Same UUID, same description — but different (device, tag) means add+delete,
        # not an update. Identity is parent-NIC + tag, full stop.
        desired = [_vlan("igb1", 10, desc="same")]
        current = [_live("u1", "igb0", 10, desc="same")]
        diff = spike.compute_diff(desired, current)
        assert len(diff.adds) == 1
        assert len(diff.deletes) == 1
        assert len(diff.updates) == 0
        assert diff.adds[0].device == "igb1"
        assert diff.deletes[0].device == "igb0"

    def test_mixed_add_update_delete(self) -> None:
        desired = [
            _vlan("igb0", 10, desc="keep"),  # unchanged
            _vlan("igb0", 20, desc="updated"),  # update
            _vlan("igb0", 30, desc="brand-new"),  # add
        ]
        current = [
            _live("u1", "igb0", 10, desc="keep"),
            _live("u2", "igb0", 20, desc="old"),
            _live("u3", "igb0", 99, desc="going-away"),  # delete
        ]
        diff = spike.compute_diff(desired, current)
        assert len(diff.adds) == 1
        assert len(diff.updates) == 1
        assert len(diff.deletes) == 1
        assert diff.adds[0].tag == 30
        assert diff.updates[0][0].uuid == "u2"
        assert diff.deletes[0].uuid == "u3"


# ---------------------------------------------------------------------------
# Typed-surface fallback
# ---------------------------------------------------------------------------


class TestSearchVlansFallback:
    """``search_vlans`` must fall back to ``client.post(...)`` when the typed surface fails."""

    def test_fallback_when_typed_search_unavailable(self) -> None:
        # Build a mock client whose typed surface raises AttributeError on .sync(),
        # forcing the fallback path.
        client = MagicMock()
        function_proxy = MagicMock()
        function_proxy.sync.side_effect = AttributeError("not generated")
        # client.api.interfaces.<anything> -> function_proxy
        type(client.api.interfaces).vlansettings_search_item = function_proxy
        # Configure fallback POST to return realistic shape.
        client.post.return_value = {
            "rows": [
                {"uuid": "u1", "if": "igb0", "tag": "10", "descr": "vlan10", "pcp": "0"},
            ]
        }

        result = spike.search_vlans(client)

        assert len(result) == 1
        assert result[0].uuid == "u1"
        assert result[0].device == "igb0"
        assert result[0].tag == 10
        client.post.assert_called_once_with("interfaces", "vlansettings", "searchItem")

    def test_typed_search_used_when_available(self) -> None:
        client = MagicMock()
        # Typed surface returns rows directly — no AttributeError.
        client.api.interfaces.vlansettings_search_item.sync.return_value = {
            "rows": [
                {"uuid": "u2", "if": "igb1", "tag": "20", "descr": "v20", "pcp": "3"},
            ]
        }

        result = spike.search_vlans(client)

        assert len(result) == 1
        assert result[0].device == "igb1"
        assert result[0].tag == 20
        assert result[0].priority == 3
        # Fallback must not have been used.
        client.post.assert_not_called()

    def test_empty_response_returns_empty_list(self) -> None:
        client = MagicMock()
        client.api.interfaces.vlansettings_search_item.sync.return_value = {"rows": []}
        assert spike.search_vlans(client) == []

    def test_malformed_rows_filtered(self) -> None:
        client = MagicMock()
        client.api.interfaces.vlansettings_search_item.sync.return_value = {
            "rows": ["not-a-dict", {"uuid": "u1", "if": "igb0", "tag": "5"}],
        }
        result = spike.search_vlans(client)
        assert len(result) == 1
        assert result[0].uuid == "u1"


# ---------------------------------------------------------------------------
# Apply loop
# ---------------------------------------------------------------------------


class TestCmdApply:
    """``cmd_apply`` dispatches mutations only when ``--confirm`` is passed."""

    @staticmethod
    def _yaml_with(tmp_path: Path, *, device: str, tag: int) -> Path:
        path = tmp_path / "v.yaml"
        path.write_text(
            f"""
- provider: opnsense
  type: vlan
  name: v1
  config:
    device: {device}
    tag: {tag}
    description: spike
    priority: 0
""",
            encoding="utf-8",
        )
        return path

    def test_dry_run_dispatches_no_mutations(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        client = MagicMock()
        client.api.interfaces.vlansettings_search_item.sync.return_value = {"rows": []}
        yaml_path = self._yaml_with(tmp_path, device="igb0", tag=100)

        rc = spike.cmd_apply(client, yaml_path, confirm=False)

        assert rc == 0
        # No add/set/del/reconfigure typed calls.
        client.api.interfaces.vlansettings_add_item.sync.assert_not_called()
        client.api.interfaces.vlansettings_set_item.sync.assert_not_called()
        client.api.interfaces.vlansettings_del_item.sync.assert_not_called()
        client.api.interfaces.vlansettings_reconfigure.sync.assert_not_called()
        # And no fallback POSTs to mutating endpoints.
        for call in client.post.call_args_list:
            assert call.args[2] == "searchItem"
        out = capsys.readouterr().out
        assert "Dry run" in out

    def test_confirm_dispatches_typed_add_call(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.api.interfaces.vlansettings_search_item.sync.return_value = {"rows": []}
        client.api.interfaces.vlansettings_add_item.sync.return_value = {
            "result": "saved",
            "uuid": "new-uuid",
        }
        client.api.interfaces.vlansettings_reconfigure.sync.return_value = {"status": "ok"}
        yaml_path = self._yaml_with(tmp_path, device="igb0", tag=100)

        rc = spike.cmd_apply(client, yaml_path, confirm=True)

        assert rc == 0
        client.api.interfaces.vlansettings_add_item.sync.assert_called_once()
        client.api.interfaces.vlansettings_reconfigure.sync.assert_called_once()
        # Inspect the payload that was passed to add_item — must wrap under "vlan".
        call_kwargs = client.api.interfaces.vlansettings_add_item.sync.call_args.kwargs
        assert "json_body" in call_kwargs
        assert call_kwargs["json_body"]["vlan"]["if"] == "igb0"
        assert call_kwargs["json_body"]["vlan"]["tag"] == "100"

    def test_confirm_with_no_diff_skips_mutations(self, tmp_path: Path) -> None:
        client = MagicMock()
        # Existing row matches the YAML exactly.
        client.api.interfaces.vlansettings_search_item.sync.return_value = {
            "rows": [
                {"uuid": "u1", "if": "igb0", "tag": "100", "descr": "spike", "pcp": "0"},
            ]
        }
        yaml_path = self._yaml_with(tmp_path, device="igb0", tag=100)

        rc = spike.cmd_apply(client, yaml_path, confirm=True)

        assert rc == 0
        client.api.interfaces.vlansettings_add_item.sync.assert_not_called()
        client.api.interfaces.vlansettings_set_item.sync.assert_not_called()
        client.api.interfaces.vlansettings_del_item.sync.assert_not_called()
        client.api.interfaces.vlansettings_reconfigure.sync.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_inspect
# ---------------------------------------------------------------------------


class TestCmdInspect:
    """``cmd_inspect`` prints version + endpoint count + typed-surface readiness."""

    def test_reports_version_and_endpoints(self, capsys: pytest.CaptureFixture[str]) -> None:
        client = MagicMock()
        client.detect_version.return_value = "25.7.6"
        client.list_endpoints.return_value = [
            ("/api/interfaces/vlansettings/addItem", "POST", "Add a VLAN"),
            ("/api/interfaces/vlansettings/searchItem", "POST", "Search VLANs"),
            ("/api/core/firmware/info", "GET", "Firmware info"),
        ]
        client.api.interfaces.vlansettings_search_item.sync.return_value = {"rows": []}

        rc = spike.cmd_inspect(client)

        assert rc == 0
        out = capsys.readouterr().out
        assert "25.7.6" in out
        assert "Total endpoints in matched spec: 3" in out
        assert "VLAN endpoints" in out
        assert "Typed-surface search available: True" in out

    def test_typed_surface_unavailable_reported(self, capsys: pytest.CaptureFixture[str]) -> None:
        client = MagicMock()
        client.detect_version.return_value = "26.1.6"
        client.list_endpoints.return_value = []
        client.api.interfaces.vlansettings_search_item.sync.side_effect = AttributeError("nope")
        # Fallback POST must also be wired so the inspection probe doesn't blow up.
        client.post.return_value = {"rows": []}

        rc = spike.cmd_inspect(client)

        assert rc == 0
        out = capsys.readouterr().out
        # The typed probe returns None when AttributeError fires — reported as False.
        assert "Typed-surface search available: False" in out


# ---------------------------------------------------------------------------
# build_client patches OPNsenseClient at the spike's import path
# ---------------------------------------------------------------------------


class TestBuildClient:
    """``build_client`` instantiates the OpenAPI client with auto_detect_version=True."""

    def test_client_constructed_with_auto_detect(self) -> None:
        creds = spike.Credentials(
            api_url="https://fw",
            api_key="k",
            api_secret="s",
            verify_ssl=False,
        )
        with patch(SPIKE_CLIENT_PATH) as client_cls:
            spike.build_client(creds)
        client_cls.assert_called_once_with(
            base_url="https://fw",
            api_key="k",
            api_secret="s",
            verify_ssl=False,
            auto_detect_version=True,
        )


# ---------------------------------------------------------------------------
# main() smoke test — exercises argparse + finally block
# ---------------------------------------------------------------------------


class TestMainEntryPoint:
    """``main`` dispatches to the right subcommand and always closes the client."""

    def test_main_inspect_closes_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPNSENSE_API_URL", "https://fw")
        monkeypatch.setenv("OPNSENSE_API_KEY", "k")
        monkeypatch.setenv("OPNSENSE_API_SECRET", "s")
        monkeypatch.setenv("OPNSENSE_VERIFY_SSL", "false")

        fake_client = MagicMock()
        fake_client.detect_version.return_value = "25.7.6"
        fake_client.list_endpoints.return_value = []
        fake_client.api.interfaces.vlansettings_search_item.sync.return_value = {"rows": []}

        with patch(SPIKE_CLIENT_PATH, return_value=fake_client):
            rc = spike.main(["inspect"])

        assert rc == 0
        fake_client.close.assert_called_once()

    def test_main_propagates_missing_env_var_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Strip env so credential loading fails fast.
        for key in ("OPNSENSE_API_URL", "OPNSENSE_API_KEY", "OPNSENSE_API_SECRET"):
            monkeypatch.delenv(key, raising=False)
        with pytest.raises(RuntimeError, match="Missing"):
            spike.main(["inspect"])


# ---------------------------------------------------------------------------
# VlanConfig.to_payload — payload shape pinned for OPNsense API compatibility
# ---------------------------------------------------------------------------


class TestVlanPayloadShape:
    """The API expects ``{"vlan": {"if", "tag", "descr", "pcp"}}`` with stringified ints."""

    def test_payload_keys_and_types(self) -> None:
        v = spike.VlanConfig(name="v1", device="igb0", tag=100, description="hello", priority=3)
        payload = v.to_payload()
        assert set(payload.keys()) == {"vlan"}
        inner = payload["vlan"]
        assert inner["if"] == "igb0"
        # OPNsense expects strings even for integer-looking fields.
        assert inner["tag"] == "100"
        assert inner["descr"] == "hello"
        assert inner["pcp"] == "3"


# ---------------------------------------------------------------------------
# Module reload sanity — confirms the spike imports cleanly with no side effects
# ---------------------------------------------------------------------------


def test_spike_module_imports_without_side_effects() -> None:
    """Importing the spike must not contact the network or read env vars eagerly."""
    # Drop and re-import — must not raise even with no OPNSENSE_* env vars set.
    sys.modules.pop("tools.spikes.vlan_direct_api", None)
    reloaded: Any = importlib.import_module("tools.spikes.vlan_direct_api")
    assert hasattr(reloaded, "main")
    assert hasattr(reloaded, "compute_diff")
