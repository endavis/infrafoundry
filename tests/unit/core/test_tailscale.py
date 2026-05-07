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

from infrafoundry.core.tailscale import TAILSCALE_MODULE_SOURCE


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
