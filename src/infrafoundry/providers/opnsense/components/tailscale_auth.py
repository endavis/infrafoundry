"""Tailscale auth component manager for OPNsense (#787).

Singleton component manager for the ``tailscale.auth`` dotted resource
type. Implements the standard ``plan`` / ``apply`` / ``destroy`` /
``get_resource_ids`` surface so that ``OPNsenseDirectRunner`` can dispatch
tailscale authentication settings alongside the other direct-API components.

Singleton semantics:

- Plan / apply enforce ``len(resources) == 1`` defensively.
- Destroy is a no-op (auth settings are never auto-uninstalled).
- ``get_resource_ids()`` returns ``{"auth": "global"}``.

The ``pre_auth_key`` field is **write-only** on the OPNsense side — the API
returns an empty string for it on GET responses. The diff comparison will
therefore always see ``pre_auth_key`` as drifted (desired has a value, live
is empty), which is the correct and intentional behavior: auth credentials
are always re-applied to ensure they are present.

Reconfiguration is deferred to the runner's ``tailscale_reconfigure``
finalization hook which is shared by all three tailscale managers.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.tailscale import TailscaleService
from ._singleton import SingletonDiff, diff_singleton, enforce_singleton
from .base import BaseComponentManager


class TailscaleAuthManager(BaseComponentManager):
    """Manager for OPNsense tailscale authentication singleton."""

    #: Shared tailscale finalization hook (#787). Fired once per apply
    #: when any of the three tailscale managers mutated state.
    FINALIZATION_HOOK: ClassVar[str] = "tailscale_reconfigure"

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> SingletonDiff:
        """Compute the diff between live tailscale auth and the YAML singleton.

        Note: ``pre_auth_key`` is write-only on the OPNsense side — the GET
        response always returns an empty string. The diff will therefore show
        the key as drifted whenever it is set in YAML, which triggers a
        re-apply of the auth payload. This is intentional.

        In plan output the ``pre_auth_key`` value is shown as ``<redacted>``
        to avoid surfacing credentials in terminal output; the raw value is
        retained in the diff for the apply path.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``tailscale.auth``
                ``ResourceConfig`` (singleton).
            add_only: No-op for singletons.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``SingletonDiff`` exposing the standard plan-shape surface.

        Raises:
            InvalidConfigurationError: If ``len(resources) != 1``.
        """
        del add_only
        enforce_singleton(resources, "tailscale.auth")
        service = TailscaleService.from_environment(env_name, provider_name, self.config_dir)
        live = service.extract_auth_fields(service.get_authentication())
        desired = service.build_desired_auth_fields(resources[0])
        diff = diff_singleton(live, desired)
        return SingletonDiff(diff)

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the singleton diff: write tailscale auth if drifted.

        Uses :meth:`TailscaleService.set_authentication` directly — the auth
        endpoint is independent of the settings endpoint so no
        read-modify-write is required.

        Does NOT call ``service.reconfigure()`` — the runner fires the
        ``tailscale_reconfigure`` finalization hook once after all three
        tailscale managers have applied.

        Args:
            env_name: Active environment name.
            resources: Should contain exactly one ``tailscale.auth``
                ``ResourceConfig``.
            auto_approve: No-op.
            add_only: No-op for singletons.
            provider_name: Provider identifier.

        Returns:
            Dict with ``resources_updated`` count and ``resource_outcomes``.
        """
        del auto_approve, add_only
        enforce_singleton(resources, "tailscale.auth")
        service = TailscaleService.from_environment(env_name, provider_name, self.config_dir)
        live = service.extract_auth_fields(service.get_authentication())
        desired = service.build_desired_auth_fields(resources[0])
        diff = diff_singleton(live, desired)

        if diff is None:
            return {
                "success": True,
                "resources_created": 0,
                "resources_updated": 0,
                "resources_deleted": 0,
                "resource_outcomes": [],
            }

        wire = service.build_auth_wire_payload(diff)
        service.set_authentication(wire)
        return {
            "success": True,
            "resources_created": 0,
            "resources_updated": 1,
            "resources_deleted": 0,
            "resource_outcomes": [
                ResourceOutcome(
                    address="opnsense_tailscale_auth.auth",
                    action="update",
                    resource_name="auth",
                )
            ],
        }

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """No-op: tailscale auth settings are never auto-uninstalled."""
        del env_name, resources, auto_approve, provider_name
        return {
            "success": True,
            "resources_destroyed": 0,
            "resource_outcomes": [],
        }

    def get_resource_ids(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        provider_name: str = "opnsense",
    ) -> dict[str, str]:
        """Return ``{"auth": "global"}`` for the singleton.

        Args:
            env_name: Active environment name (unused).
            resources: Singleton ``tailscale.auth`` resource list (unused).
            provider_name: Provider identifier (unused).

        Returns:
            Single-entry mapping with stable id ``"global"``.
        """
        del env_name, resources, provider_name
        return {"auth": "global"}

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
    ) -> str:
        """Export current tailscale auth settings to InfraFoundry YAML.

        Note: ``pre_auth_key`` is omitted from the export because the live
        API returns an empty string for it (write-only on the wire).

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier.

        Returns:
            YAML string under the ``opnsense.tailscale.auth`` namespace.
        """
        service = TailscaleService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_auth_to_yaml()
