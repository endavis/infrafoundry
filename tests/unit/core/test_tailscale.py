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

from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.tailscale import (
    TAILSCALE_MODULE_SOURCE,
    TailscaleSchemaError,
    process_tailscale_config,
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
