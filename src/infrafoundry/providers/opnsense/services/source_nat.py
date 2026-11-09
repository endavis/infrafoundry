"""Outbound NAT mode service for OPNsense direct-API operations (#1333).

Manages the ``snat_mode`` field of the ``filter.general`` node of the
``OPNsense\\Firewall\\Filter`` model through ``GET firewall/source_nat/get``,
``POST firewall/source_nat/set`` and ``POST firewall/source_nat/apply``.

The one YAML key, ``snat_mode``, takes ``automatic``, ``hybrid``, ``advanced`` or
``disabled``, sent as-is. Manual outbound rules (``firewall.nat``) take effect, and
``searchRule`` lists them, only in ``hybrid`` or ``advanced`` mode.

Write envelope: ``{"filter": {"general": {"snat_mode": <mode>}}}``. OPNsense before
26.1 keeps the mode outside the MVC model, so ``get`` has no ``filter.general`` node
there and the service fails with a clear error instead of writing.

Verified live: ``set`` with that envelope answered ``saved`` and ``apply`` answered
``OK`` on a 26.1 box. The code path here has not itself been run live.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from infrafoundry.core.exceptions import APIError, InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService, raise_on_failed_write
from .nat_rule import SNAT_MODES, _flatten_model_value

#: YAML key -> wire key under ``filter.general``.
FIELD_MAP: dict[str, str] = {"snat_mode": "snat_mode"}

#: Accepted values of ``snat_mode``.
ALLOWED_MODES: tuple[str, ...] = SNAT_MODES


class SourceNatService(BaseService):
    """Service for the OPNsense outbound NAT mode singleton."""

    def get_settings(self) -> Any:
        """Fetch the ``firewall/source_nat`` model document."""
        return self.client.request(endpoints.SOURCE_NAT_GET.method, endpoints.SOURCE_NAT_GET.path())

    def set_settings(self, desired: dict[str, str]) -> Any:
        """Write the declared general fields.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.client.request(
            endpoints.SOURCE_NAT_SET.method,
            endpoints.SOURCE_NAT_SET.path(),
            data={"filter": {"general": dict(desired)}},
        )
        return raise_on_failed_write(response, "set outbound NAT mode")

    def apply(self) -> Any:
        """Apply the saved outbound NAT mode.

        Called only by the provider's ``source_nat_apply`` finalization hook; the
        manager must not call it directly.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}`` or
                ``{"status": "failed"}``.
        """
        response = self.client.request(
            endpoints.SOURCE_NAT.apply.method, endpoints.SOURCE_NAT.apply.path()
        )
        raise_on_failed_write(response, "apply outbound NAT")
        if isinstance(response, dict) and response.get("status") == "failed":
            raise APIError(
                "OPNsense rejected apply outbound NAT: status failed",
                response=str(response),
                provider="opnsense",
            )
        return response

    def live_general(self, response: Any) -> dict[str, Any]:
        """Return ``response["filter"]["general"]``.

        Raises:
            APIError: If ``snat_mode`` is missing, as on OPNsense before 26.1.
        """
        filter_model = response.get("filter") if isinstance(response, dict) else None
        general = filter_model.get("general") if isinstance(filter_model, dict) else None
        if not isinstance(general, dict) or "snat_mode" not in general:
            raise APIError(
                "firewall.source_nat needs OPNsense 26.1 or later: firewall/source_nat/get "
                "returned no filter.general.snat_mode (older releases keep the outbound NAT "
                "mode outside the MVC model)",
                provider="opnsense",
            )
        return general

    def build_desired(self, resource: ResourceConfig) -> dict[str, str]:
        """Build the desired wire strings for the declared keys only.

        Raises:
            InvalidConfigurationError: On unknown keys or a mode outside ``ALLOWED_MODES``.
        """
        config = resource.config
        unknown = sorted(set(config) - set(FIELD_MAP))
        if unknown:
            raise InvalidConfigurationError(
                f"firewall.source_nat has unknown key(s): {', '.join(unknown)}"
            )
        desired: dict[str, str] = {}
        if "snat_mode" in config:
            mode = config["snat_mode"]
            if not isinstance(mode, str) or mode not in ALLOWED_MODES:
                raise InvalidConfigurationError(
                    f"firewall.source_nat snat_mode must be one of {', '.join(ALLOWED_MODES)}"
                )
            desired["snat_mode"] = mode
        return desired

    def extract_live(self, general: dict[str, Any], keys: Iterable[str]) -> dict[str, str]:
        """Extract the given YAML keys from the live object, as wire strings."""
        return {key: _flatten_model_value(general[FIELD_MAP[key]]) for key in keys}

    def drift(self, live: dict[str, str], desired: dict[str, str]) -> dict[str, str] | None:
        """Compare declared keys; return ``desired`` on any difference."""
        for key, value in desired.items():
            if live.get(key) != value:
                return desired
        return None

    def export_to_yaml(self) -> str:
        """Export the live outbound NAT mode as nested YAML."""
        general = self.live_general(self.get_settings())
        live = self.extract_live(general, ["snat_mode"])
        return emit_nested_singleton_yaml("firewall.source_nat", live)
