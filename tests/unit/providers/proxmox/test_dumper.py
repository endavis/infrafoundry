"""Unit tests for ProxmoxStateDumper."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import requests

from infrafoundry.core.exceptions import APIError
from infrafoundry.providers.proxmox.dumper import ProxmoxStateDumper


@pytest.fixture
def env_config():
    """Environment config with usable Proxmox credentials."""
    return {
        "provider_settings": {
            "proxmox": {
                "api_url": "https://proxmox.example.com:8006/api2/json",
                "api_token": "user@pam!token=secret",
                "verify_ssl": False,
            }
        }
    }


def _make_responder(mapping: Mapping[str, Any], default: Any = None):
    """Build a ``get_json`` stub returning the configured payloads.

    ``mapping`` maps endpoint path -> raw ``data`` value (the dumper unwraps
    the PVE ``{"data": ...}`` envelope, so tests pre-unwrap for clarity).
    """

    def _fake_get_json(path: str, **_kwargs):
        if path in mapping:
            return {"data": mapping[path]}
        return {"data": default or []}

    return _fake_get_json


def _minimal_cluster_mapping() -> dict[str, object]:
    """Return a realistic-but-tiny topology used by several tests."""
    return {
        "nodes": [{"node": "pve1"}, {"node": "pve2"}],
        "storage": [{"storage": "local"}, {"storage": "rbd"}],
        "nodes/pve1/qemu": [{"vmid": 100}, {"vmid": 101}],
        "nodes/pve2/qemu": [{"vmid": 200}, {"vmid": 201}],
        "nodes/pve1/lxc": [],
        "nodes/pve2/lxc": [],
    }


def test_dump_writes_expected_sections(env_config, tmp_path):
    """Dumper writes a JSON file containing the top-level sections we expect."""
    output = tmp_path / "dump.json"
    mapping = _minimal_cluster_mapping()

    dumper = ProxmoxStateDumper(env_config, timeout=5)
    with patch.object(dumper._client, "get_json", side_effect=_make_responder(mapping)):
        result = dumper.dump(output)

    # Top-level keys from static endpoints and enumeration.
    assert "meta" in result and "version" in result["meta"]
    assert "cluster" in result
    assert "access" in result
    assert "storage" in result
    assert "storage.detail" in result
    assert result["nodes"] == ["pve1", "pve2"]
    assert "node:pve1" in result and "node:pve2" in result
    assert "node:pve1:qemu" in result and "node:pve2:qemu" in result

    # File on disk matches the returned dict.
    on_disk = json.loads(output.read_text())
    assert on_disk == result


def test_dump_unwraps_data_envelope(env_config, tmp_path):
    """The dumper stores the inner ``data`` value, not the full envelope."""
    output = tmp_path / "dump.json"
    mapping = {
        "nodes": [{"node": "pve1"}],
        "storage": [],
        "nodes/pve1/qemu": [],
        "nodes/pve1/lxc": [],
    }

    dumper = ProxmoxStateDumper(env_config, timeout=5)
    with patch.object(dumper._client, "get_json", side_effect=_make_responder(mapping)):
        result = dumper.dump(output)

    # ``nodes`` is stored as the list of names, not the raw list-of-dicts or
    # the ``{"data": [...]}`` envelope.
    assert result["nodes"] == ["pve1"]
    # ``storage`` is stored as whatever was under ``data`` -- here [].
    assert result["storage"] == []


def test_dump_captures_timeout(env_config, tmp_path):
    """A timeout on one endpoint is recorded inline; the rest of the dump completes."""
    output = tmp_path / "dump.json"
    mapping = _minimal_cluster_mapping()

    def responder(path: str, **_kwargs):
        if path == "cluster/status":
            raise APIError(
                "Proxmox API request timed out",
                provider="proxmox",
            ) from requests.exceptions.Timeout("timed out")
        if path in mapping:
            return {"data": mapping[path]}
        return {"data": []}

    dumper = ProxmoxStateDumper(env_config, timeout=5)
    with patch.object(dumper._client, "get_json", side_effect=responder):
        result = dumper.dump(output)

    # The failing endpoint shows the timeout sentinel, not a crash.
    assert result["cluster"]["status"] == {"__timeout__": True, "path": "cluster/status"}
    # Rest of the dump completed.
    assert result["nodes"] == ["pve1", "pve2"]


def test_dump_captures_api_error(env_config, tmp_path):
    """A non-timeout APIError is captured inline and the dump keeps going."""
    output = tmp_path / "dump.json"
    mapping = _minimal_cluster_mapping()

    def responder(path: str, **_kwargs):
        if path == "access/users":
            raise APIError("Permission denied", status_code=403, provider="proxmox")
        if path in mapping:
            return {"data": mapping[path]}
        return {"data": []}

    dumper = ProxmoxStateDumper(env_config, timeout=5)
    with patch.object(dumper._client, "get_json", side_effect=responder):
        result = dumper.dump(output)

    entry = result["access"]["users"]
    assert entry["path"] == "access/users"
    assert "__error__" in entry
    assert "Permission denied" in entry["__error__"]
    # Dump still wrote subsequent sections.
    assert result["nodes"] == ["pve1", "pve2"]


def test_dump_incremental_save(env_config, tmp_path):
    """Partial dumps on disk remain valid JSON mid-run.

    We simulate a crash after the ``nodes`` enumeration by having the first
    per-node request raise. The on-disk file must already contain the
    static-endpoint sections at that point.
    """
    output = tmp_path / "dump.json"
    mapping = _minimal_cluster_mapping()

    class BoomError(RuntimeError):
        pass

    def responder(path: str, **_kwargs):
        if path == "nodes/pve1/status":
            raise BoomError("kaboom")
        if path in mapping:
            return {"data": mapping[path]}
        return {"data": []}

    dumper = ProxmoxStateDumper(env_config, timeout=5)
    with (
        patch.object(dumper._client, "get_json", side_effect=responder),
        pytest.raises(BoomError),
    ):
        dumper.dump(output)

    # Even though the dump aborted, the file on disk is valid JSON with
    # everything written up to the last successful ``_save`` (the nodes list).
    partial = json.loads(output.read_text())
    assert partial["nodes"] == ["pve1", "pve2"]
    assert "storage" in partial


def test_dump_enumerates_nodes_and_vms(env_config, tmp_path):
    """Per-VM endpoints are called for every VM on every node."""
    output = tmp_path / "dump.json"
    mapping = _minimal_cluster_mapping()
    calls: list[str] = []

    def responder(path: str, **_kwargs):
        calls.append(path)
        if path in mapping:
            return {"data": mapping[path]}
        return {"data": []}

    dumper = ProxmoxStateDumper(env_config, timeout=5)
    with patch.object(dumper._client, "get_json", side_effect=responder):
        dumper.dump(output)

    # 2 VMs/node * 2 nodes * 2 per-VM endpoints (config + pending) = 8.
    config_calls = [c for c in calls if c.endswith("/config") and "/qemu/" in c]
    pending_calls = [c for c in calls if c.endswith("/pending") and "/qemu/" in c]
    assert len(config_calls) == 4
    assert len(pending_calls) == 4


def test_dump_missing_credentials():
    """Dumper raises a clear error when credentials are missing."""
    env_config = {"provider_settings": {"proxmox": {}}}
    with pytest.raises(ValueError, match="credentials"):
        ProxmoxStateDumper(env_config, timeout=5)  # type: ignore[arg-type]


def test_dump_atomic_write_no_tmp_left(env_config, tmp_path):
    """A successful dump leaves no ``.tmp`` file next to the output."""
    output = tmp_path / "dump.json"
    mapping = _minimal_cluster_mapping()

    dumper = ProxmoxStateDumper(env_config, timeout=5)
    with patch.object(dumper._client, "get_json", side_effect=_make_responder(mapping)):
        dumper.dump(output)

    assert output.exists()
    # No lingering .tmp file.
    stray = [p.name for p in output.parent.iterdir() if p.name.endswith(".tmp")]
    assert stray == []


def test_dump_storage_detail_discovered_from_listing(env_config, tmp_path):
    """Each storage ID in the ``storage`` listing gets a per-storage detail call."""
    output = tmp_path / "dump.json"
    mapping = _minimal_cluster_mapping()

    dumper = ProxmoxStateDumper(env_config, timeout=5)
    with patch.object(dumper._client, "get_json", side_effect=_make_responder(mapping, default=[])):
        result = dumper.dump(output)

    assert set(result["storage.detail"].keys()) == {"local", "rbd"}


def test_dump_timeout_overrides_client_timeout(env_config, tmp_path):
    """The --timeout value is propagated to the underlying ProxmoxClient."""
    dumper = ProxmoxStateDumper(env_config, timeout=60)
    assert dumper._client.timeout == 60


def test_dump_creates_parent_directory(env_config, tmp_path):
    """The output parent directory is created if it doesn't exist."""
    output = tmp_path / "nested" / "deep" / "dump.json"
    mapping = _minimal_cluster_mapping()

    dumper = ProxmoxStateDumper(env_config, timeout=5)
    with patch.object(dumper._client, "get_json", side_effect=_make_responder(mapping)):
        dumper.dump(output)

    assert output.exists()


def test_dump_node_section_includes_expected_labels(env_config, tmp_path):
    """The per-node section contains the canonical label set."""
    output = tmp_path / "dump.json"
    mapping = _minimal_cluster_mapping()

    dumper = ProxmoxStateDumper(env_config, timeout=5)
    with patch.object(dumper._client, "get_json", side_effect=_make_responder(mapping)):
        result = dumper.dump(output)

    node_section = result["node:pve1"]
    for label in ("status", "version", "network", "storage", "qemu", "lxc"):
        assert label in node_section


def test_dump_returns_final_dict(env_config, tmp_path: Path):
    """The return value of ``dump`` equals the final on-disk JSON."""
    output = tmp_path / "dump.json"
    mapping = _minimal_cluster_mapping()

    dumper = ProxmoxStateDumper(env_config, timeout=5)
    with patch.object(dumper._client, "get_json", side_effect=_make_responder(mapping)):
        returned = dumper.dump(output)

    on_disk = json.loads(output.read_text())
    assert returned == on_disk
