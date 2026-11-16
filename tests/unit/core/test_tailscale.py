"""Structural regression tests for the Tailscale cloud-init module constants.

Guards ``TAILSCALE_MODULE_SOURCE`` against the failure mode that motivated
issue #767: the constant was set to ``"tailscale/cloudinit/tailscale"``,
flipping the 2nd and 3rd Terraform Registry path segments. Terraform's
registry source format is ``<namespace>/<name>/<provider>``, and the
canonical Tailscale cloud-init module lives at
``https://registry.terraform.io/modules/tailscale/tailscale/cloudinit``.
The wrong path returns HTTP 404 from the registry; ``terraform init``
fails before any rendered output is consumed.

These tests pin the constant against canonical registry coordinates
without performing any network call.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.tailscale import (
    TAILSCALE_MODULE_SOURCE,
    TailnetDeviceCleanup,
    TailscaleSchemaError,
    device_matches,
    plan_tailnet_cleanup,
    process_tailscale_config,
    remove_tailnet_devices,
)


def test_module_source_has_three_segments() -> None:
    """``TAILSCALE_MODULE_SOURCE`` must be a 3-segment slash-separated path.

    Guards against accidental flattening (e.g. ``"tailscale/tailscale-cloudinit"``)
    or an extra segment getting introduced. Terraform Registry sources are
    always exactly ``<namespace>/<name>/<provider>``.
    """
    parts = TAILSCALE_MODULE_SOURCE.split("/")
    assert len(parts) == 3, (
        f"Expected 3 slash-separated segments, got {len(parts)}: {TAILSCALE_MODULE_SOURCE!r}"
    )


def test_module_source_segments_match_canonical_registry_path() -> None:
    """``TAILSCALE_MODULE_SOURCE`` segments must equal the canonical path.

    The canonical Tailscale cloud-init module is published at
    ``https://registry.terraform.io/modules/tailscale/tailscale/cloudinit``.
    Per Terraform Registry conventions, the module-block ``source`` is
    ``<namespace>/<name>/<provider>``. This test would have caught the
    original bug (#767), where the 2nd and 3rd segments were flipped
    to ``"tailscale/cloudinit/tailscale"`` (HTTP 404).
    """
    namespace, name, provider = TAILSCALE_MODULE_SOURCE.split("/")
    assert (namespace, name, provider) == ("tailscale", "tailscale", "cloudinit")


# ---------------------------------------------------------------------------
# OAuth auth mode (issue #1311)
# ---------------------------------------------------------------------------


def _oauth_resource(
    *, tags: Any = ("tag:example",), oauth: dict[str, Any] | None = None
) -> ResourceConfig:
    oauth_block: dict[str, Any] = (
        oauth
        if oauth is not None
        else {
            "client_id_secret": "tailscale.oauth_client_id",
            "client_secret_secret": "tailscale.oauth_client_secret",
        }
    )
    tailscale: dict[str, Any] = {"auth": {"oauth": oauth_block}}
    if tags is not None:
        tailscale["advertise_tags"] = list(tags) if isinstance(tags, tuple) else tags
    return ResourceConfig(
        name="node-a", type="instance", provider="oci", config={"tailscale": tailscale}
    )


class TestOAuthMode:
    def test_client_secret_becomes_auth_key_var(self) -> None:
        resource = _oauth_resource()
        cfg = process_tailscale_config(resource, base64_encode=True)
        assert cfg is not None
        assert cfg["auth_mode"] == "oauth"
        assert cfg["auth_key_var"] == "tailscale_oauth_client_secret"
        assert "oauth_client_id_var" not in cfg
        assert "oauth_client_secret_var" not in cfg

    def test_only_client_secret_ref_added_to_terraform_secrets(self) -> None:
        resource = _oauth_resource()
        process_tailscale_config(resource, base64_encode=True)
        assert resource.config["terraform_secrets"] == ["tailscale.oauth_client_secret"]

    def test_client_id_secret_is_optional(self) -> None:
        resource = _oauth_resource(oauth={"client_secret_secret": "tailscale.oauth_client_secret"})
        cfg = process_tailscale_config(resource, base64_encode=True)
        assert cfg is not None
        assert cfg["auth_key_var"] == "tailscale_oauth_client_secret"

    @pytest.mark.parametrize("bad", ["", 5])
    def test_client_id_secret_invalid_rejected(self, bad: Any) -> None:
        resource = _oauth_resource(
            oauth={
                "client_id_secret": bad,
                "client_secret_secret": "tailscale.oauth_client_secret",
            }
        )
        with pytest.raises(TailscaleSchemaError, match="client_id_secret"):
            process_tailscale_config(resource, base64_encode=True)

    def test_client_secret_secret_required(self) -> None:
        resource = _oauth_resource(oauth={"client_id_secret": "tailscale.oauth_client_id"})
        with pytest.raises(TailscaleSchemaError, match="client_secret_secret"):
            process_tailscale_config(resource, base64_encode=True)

    @pytest.mark.parametrize("tags", [None, []])
    def test_missing_or_empty_tags_rejected(self, tags: Any) -> None:
        resource = _oauth_resource(tags=tags)
        with pytest.raises(TailscaleSchemaError, match="advertise_tags"):
            process_tailscale_config(resource, base64_encode=True)


class TestAuthKeyModeUnchanged:
    def test_auth_key_mode_needs_no_tags(self) -> None:
        resource = ResourceConfig(
            name="node-a",
            type="instance",
            provider="oci",
            config={"tailscale": {"auth": {"auth_key_secret": "tailscale.auth_key"}}},
        )
        cfg = process_tailscale_config(resource, base64_encode=False)
        assert cfg is not None
        assert cfg["auth_mode"] == "auth_key"
        assert cfg["auth_key_var"] == "tailscale_auth_key"
        assert resource.config["terraform_secrets"] == ["tailscale.auth_key"]


# ---------------------------------------------------------------------------
# Tailnet device cleanup on destroy (issue #1401)
# ---------------------------------------------------------------------------

CLIENT_ID = "placeholder-client-id"
CLIENT_SECRET = "placeholder-client-secret"
TOKEN = "placeholder-access-token"
SECRETS: dict[str, Any] = {
    "tailscale": {"oauth_client_id": CLIENT_ID, "oauth_client_secret": CLIENT_SECRET}
}


def _target(hostname: str = "node-a", tags: tuple[str, ...] = ("tag:example",)) -> Any:
    return TailnetDeviceCleanup(
        resource_name=hostname,
        hostname=hostname,
        tags=tags,
        client_id_ref="tailscale.oauth_client_id",
        client_secret_ref="tailscale.oauth_client_secret",
    )


def _resp(status: int = 200, body: Any = None) -> MagicMock:
    return MagicMock(status_code=status, json=lambda: body)


def _session(
    devices: list[dict[str, Any]], delete_status: int = 200, token_status: int = 200
) -> MagicMock:
    session = MagicMock()
    session.post.return_value = _resp(token_status, {"access_token": TOKEN})
    session.get.return_value = _resp(200, {"devices": devices})
    session.delete.return_value = _resp(delete_status)
    return session


class TestRemoveOnDestroySchema:
    def test_defaults_to_true(self) -> None:
        cfg = process_tailscale_config(_oauth_resource(), base64_encode=False)
        assert cfg is not None
        assert cfg["remove_on_destroy"] is True

    def test_accepts_false(self) -> None:
        resource = _oauth_resource()
        resource.config["tailscale"]["remove_on_destroy"] = False
        cfg = process_tailscale_config(resource, base64_encode=False)
        assert cfg is not None
        assert cfg["remove_on_destroy"] is False

    @pytest.mark.parametrize("value", ["no", 1])
    def test_rejects_non_bool(self, value: Any) -> None:
        resource = _oauth_resource()
        resource.config["tailscale"]["remove_on_destroy"] = value
        with pytest.raises(TailscaleSchemaError):
            process_tailscale_config(resource, base64_encode=False)

    def test_oauth_auth_info_carries_client_id_ref(self) -> None:
        from infrafoundry.core.tailscale import _validate_auth_block

        with_id = _validate_auth_block(
            "node-a", {"oauth": {"client_id_secret": "a.b", "client_secret_secret": "a.c"}}
        )
        without = _validate_auth_block("node-a", {"oauth": {"client_secret_secret": "a.c"}})
        assert with_id["client_id_ref"] == "a.b"
        assert without["client_id_ref"] is None


class TestPlanTailnetCleanup:
    def test_oauth_resource_becomes_target(self) -> None:
        targets, messages = plan_tailnet_cleanup([_oauth_resource()])
        assert messages == []
        assert targets == [
            TailnetDeviceCleanup(
                resource_name="node-a",
                hostname="node-a",
                tags=("tag:example",),
                client_id_ref="tailscale.oauth_client_id",
                client_secret_ref="tailscale.oauth_client_secret",
            )
        ]

    def test_custom_hostname_honoured(self) -> None:
        resource = _oauth_resource()
        resource.config["tailscale"]["hostname"] = "node-b"
        targets, _ = plan_tailnet_cleanup([resource])
        assert targets[0].hostname == "node-b"

    def test_no_tailscale_block_ignored(self) -> None:
        plain = ResourceConfig(name="x", type="instance", provider="oci", config={})
        assert plan_tailnet_cleanup([plain]) == ([], [])

    def test_remove_on_destroy_false_skipped(self) -> None:
        resource = _oauth_resource()
        resource.config["tailscale"]["remove_on_destroy"] = False
        targets, messages = plan_tailnet_cleanup([resource])
        assert targets == []
        assert "remove_on_destroy" in messages[0]

    def test_auth_key_skipped(self) -> None:
        resource = ResourceConfig(
            name="node-a",
            type="instance",
            provider="oci",
            config={"tailscale": {"auth": {"auth_key_secret": "tailscale.key"}}},
        )
        targets, messages = plan_tailnet_cleanup([resource])
        assert targets == []
        assert "auth key" in messages[0]

    def test_missing_client_id_skipped(self) -> None:
        resource = _oauth_resource(oauth={"client_secret_secret": "tailscale.oauth_client_secret"})
        targets, messages = plan_tailnet_cleanup([resource])
        assert targets == []
        assert "client_id_secret" in messages[0]

    def test_invalid_block_reports_without_raising(self) -> None:
        resource = _oauth_resource(tags=None)
        targets, messages = plan_tailnet_cleanup([resource])
        assert targets == []
        assert len(messages) == 1

    def test_input_not_mutated(self) -> None:
        resource = _oauth_resource()
        plan_tailnet_cleanup([resource])
        assert "terraform_secrets" not in resource.config


class TestDeviceMatches:
    def test_hostname_and_tag(self) -> None:
        assert device_matches(
            {"hostname": "node-a", "tags": ["tag:example"]}, "node-a", ["tag:example"]
        )

    def test_no_shared_tag(self) -> None:
        assert not device_matches(
            {"hostname": "node-a", "tags": ["tag:other"]}, "node-a", ["tag:example"]
        )

    def test_different_hostname(self) -> None:
        assert not device_matches(
            {"hostname": "node-b", "tags": ["tag:example"]}, "node-a", ["tag:example"]
        )

    def test_case_insensitive(self) -> None:
        assert device_matches(
            {"hostname": "NODE-A", "tags": ["tag:example"]}, "node-a", ["tag:Example"]
        )

    def test_no_tags_key(self) -> None:
        assert not device_matches({"hostname": "node-a"}, "node-a", ["tag:example"])


class TestRemoveTailnetDevices:
    def test_happy_path(self) -> None:
        devices = [
            {"id": "100000000001", "hostname": "node-a", "tags": ["tag:example"]},
            {"id": "100000000002", "hostname": "node-a", "tags": ["tag:other"]},
        ]
        session = _session(devices)
        report = remove_tailnet_devices([_target()], SECRETS, session=session)
        session.post.assert_called_once()
        assert session.post.call_args.kwargs["data"] == {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        assert session.get.call_args.args[0].endswith("/tailnet/-/devices")
        assert session.get.call_args.kwargs["headers"] == {"Authorization": f"Bearer {TOKEN}"}
        session.delete.assert_called_once()
        assert session.delete.call_args.args[0].endswith("/device/100000000001")
        assert len(report.removed) == 1
        assert report.warnings == []

    def test_collision_copies_all_deleted(self) -> None:
        devices = [
            {"id": "100000000001", "hostname": "node-a", "tags": ["tag:example"]},
            {"id": "100000000002", "hostname": "node-a", "tags": ["tag:example"]},
        ]
        session = _session(devices)
        report = remove_tailnet_devices([_target()], SECRETS, session=session)
        assert session.delete.call_count == 2
        assert len(report.removed) == 2

    def test_no_match_skipped(self) -> None:
        session = _session([])
        report = remove_tailnet_devices([_target()], SECRETS, session=session)
        session.delete.assert_not_called()
        assert len(report.skipped) == 1

    def test_shared_credentials_fetch_once(self) -> None:
        session = _session([])
        remove_tailnet_devices([_target("node-a"), _target("node-b")], SECRETS, session=session)
        assert session.post.call_count == 1
        assert session.get.call_count == 1

    def test_token_failure_warns(self) -> None:
        session = _session([], token_status=401)
        report = remove_tailnet_devices([_target()], SECRETS, session=session)
        assert "401" in report.warnings[0]
        session.get.assert_not_called()

    def test_device_list_connection_error_warns(self) -> None:
        session = _session([])
        session.get.side_effect = requests.ConnectionError("boom")
        report = remove_tailnet_devices([_target()], SECRETS, session=session)
        assert len(report.warnings) == 1

    def test_delete_failure_does_not_stop_others(self) -> None:
        devices = [
            {"id": "100000000001", "hostname": "node-a", "tags": ["tag:example"]},
            {"id": "100000000002", "hostname": "node-a", "tags": ["tag:example"]},
        ]
        session = _session(devices)
        session.delete.side_effect = [_resp(403), _resp(200)]
        report = remove_tailnet_devices([_target()], SECRETS, session=session)
        assert session.delete.call_count == 2
        assert "403" in report.warnings[0]
        assert len(report.removed) == 1

    @pytest.mark.parametrize("secrets", [None, {"tailscale": {"oauth_client_id": CLIENT_ID}}])
    def test_missing_secret_warns_with_ref(self, secrets: Any) -> None:
        session = _session([])
        report = remove_tailnet_devices([_target()], secrets, session=session)
        assert "tailscale.oauth_client_secret" in report.warnings[0]
        session.post.assert_not_called()

    def test_no_secret_leakage(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG)
        for session in (
            _session([], token_status=401),
            _session(
                [{"id": "1", "hostname": "node-a", "tags": ["tag:example"]}], delete_status=500
            ),
        ):
            report = remove_tailnet_devices([_target()], SECRETS, session=session)
            text = " ".join(report.removed + report.skipped + report.warnings) + caplog.text
            assert CLIENT_SECRET not in text
            assert TOKEN not in text
