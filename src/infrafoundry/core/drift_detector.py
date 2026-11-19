"""Drift detection for infrastructure resources."""

from typing import Any, cast, override

from infrafoundry.core.base_manager import BaseManager
from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.models import IaCTool
from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.exceptions import (
    ConfigurationError,
    InfraFoundryError,
    TerraformError,
)
from infrafoundry.core.managed_set import build_managed_resources
from infrafoundry.core.protocols import DriftDetectable, Plannable
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.result_types import DriftInfo
from infrafoundry.core.runners import BaseRunner, RunnerRegistry
from infrafoundry.core.state import StateManager


class DriftDetector(BaseManager):
    """Detects infrastructure drift from declared configuration."""

    def __init__(
        self,
        config_manager: ConfigManager,
        runner_registry: RunnerRegistry,
        event_manager: EventManager,
        providers: dict[str, ProviderBase],
        state_manager: StateManager | None = None,
    ) -> None:
        """Initialize drift detector.

        Args:
            config_manager: Configuration manager instance
            runner_registry: Registry for creating tool runners
            event_manager: Event manager for notifications
            providers: Dict of registered provider instances
            state_manager: State manager that supplies the managed rows a direct runner
                needs to tell an adopted resource (``update``) from a new one (``create``),
                as ``infra plan`` does (ADR-0018, #1495). Without it no managed set is passed.
        """
        super().__init__()
        self.config_manager = config_manager
        self.runner_registry = runner_registry
        self.event_manager = event_manager
        self.providers = providers
        self.state_manager = state_manager

    def detect(self, env_name: str) -> dict[str, Any]:
        """Detect infrastructure drift from declared configuration.

        Compares the actual infrastructure state (from Terraform state) with
        the declared configuration to identify resources that have been
        modified, added, or deleted outside of InfraFoundry.

        A provider with a drift-detectable direct runner (not Terraform or OpenTofu,
        for example MikroTik, ADR-0026) is planned add-only through that runner
        instead of Terraform.

        Args:
            env_name: Environment name

        Returns:
            Dict with drift detection results per provider:
                {
                    "provider_name": {
                        "has_changes": bool,
                        "to_add": int,
                        "to_change": int,
                        "to_destroy": int,
                        "summary": str,
                        "raw_output": str,
                        "parsed": False  # only when the plan output was unparsable
                    }
                }
        """
        # Emit drift check started event
        self.event_manager.emit_event(
            EventType.DRIFT_CHECK_STARTED,
            env_name,
            {"environment": env_name},
        )

        self._log_info(f"Checking for drift in: {env_name}")

        results = {}
        drift_detected = False

        # Resolve IaC tool from environment config
        iac_tool = IaCTool.TERRAFORM
        try:
            env_config = self.config_manager.load_environment(env_name)
            iac_tool = env_config.iac_tool
        except FileNotFoundError:
            pass  # Use default (terraform) when no env config exists

        # Dynamically create the runner for the configured IaC tool
        terraform_runner = self.runner_registry.create_runner(iac_tool.value)
        if not terraform_runner:
            raise InfraFoundryError(f"Could not create {iac_tool.value} runner")

        try:
            # Get all resources and discover providers dynamically
            all_resources = self.config_manager.get_all_resources_all_providers(env_name)

            # Group resources by provider
            resources_by_provider: dict[str, list[Any]] = {}
            for resource in all_resources:
                if resource.provider not in resources_by_provider:
                    resources_by_provider[resource.provider] = []
                resources_by_provider[resource.provider].append(resource)

            for provider_name, _resources in resources_by_provider.items():
                if provider_name not in self.providers:
                    continue

                provider = self.providers[provider_name]

                self._log_info(f"Checking {provider_name}...")

                try:
                    drift_info = self._detect_provider(
                        terraform_runner, provider, provider_name, env_name
                    )
                except Exception as e:  # one provider must not abort the others
                    self._log_warning(f"Could not check drift for {provider_name}: {e}")
                    results[provider_name] = DriftInfo(
                        has_changes=False,
                        to_add=0,
                        to_change=0,
                        to_destroy=0,
                        summary=f"Drift check failed: {e}",
                        raw_output="",
                        parsed=False,
                    )
                    continue
                if drift_info is None:
                    continue

                if drift_info["has_changes"]:
                    drift_detected = True
                    self._log_warning(f"Drift detected: {drift_info['summary']}")
                    self.event_manager.emit_event(
                        EventType.DRIFT_DETECTED,
                        env_name,
                        {"provider": provider_name, "changes": drift_info},
                    )
                elif drift_info.get("parsed") is False:
                    self._log_warning(
                        f"Could not determine drift for {provider_name}: {drift_info['summary']}"
                    )
                else:
                    self._log_info(f"No drift detected for {provider_name}")

                results[provider_name] = drift_info

            # Emit drift check completed event
            self.event_manager.emit_event(
                EventType.DRIFT_CHECK_COMPLETED,
                env_name,
                {
                    "drift_detected": drift_detected,
                    "results": results,
                },
            )

            if not drift_detected:
                self._log_info("All infrastructure matches declared configuration")

        except (ConfigurationError, TerraformError) as e:
            self._log_error(f"Error detecting drift: {e}", e)
            raise
        except InfraFoundryError as e:
            self._log_error(f"InfraFoundry error detecting drift: {e}", e)
            raise
        except Exception as e:
            self._log_error(f"Unexpected error detecting drift: {e}", e)
            raise

        return results

    def _detect_provider(
        self,
        terraform_runner: BaseRunner,
        provider: ProviderBase,
        provider_name: str,
        env_name: str,
    ) -> DriftInfo | None:
        """Detect drift for one provider.

        Returns:
            The drift info, or ``None`` when the runner cannot detect drift.

        Raises:
            Exception: Any failure of the plan or its parsing; ``detect`` records it
                as this provider's result and carries on with the others.
        """
        direct_runner = self._direct_drift_runner(provider)
        if direct_runner is not None:
            return self._detect_direct(direct_runner, provider, provider_name, env_name)

        if not isinstance(terraform_runner, Plannable):
            self._log_warning(
                f"Runner {terraform_runner.tool_name} does not support plan operation"
            )
            return None
        if not isinstance(terraform_runner, DriftDetectable):
            self._log_warning(
                f"Runner {terraform_runner.tool_name} does not support drift detection"
            )
            return None

        # Point the provider at the environment's generated directory first, as
        # every other caller does; otherwise terraform_dir is env-less (#1488).
        provider.set_environment(env_name)
        # Compare current state with declared config
        plan_result = terraform_runner.plan(provider)
        return terraform_runner.parse_plan_for_drift(plan_result)

    def _direct_drift_runner(self, provider: ProviderBase) -> BaseRunner | None:
        """Return a direct-API runner that can detect drift for ``provider``.

        A direct runner is an IaC runner other than Terraform and OpenTofu that is
        ``Plannable`` and ``DriftDetectable`` and whose provider offers a
        ``generate_<tool_name>`` method. OPNsense keeps the Terraform path because
        its runner is not ``DriftDetectable``.
        """
        for tool_name in self.runner_registry.list_runners():
            if tool_name in ("terraform", "opentofu"):
                continue
            runner = self.runner_registry.create_runner(tool_name)
            if (
                runner is not None
                and runner.is_iac_runner
                and isinstance(runner, Plannable)
                and isinstance(runner, DriftDetectable)
                and callable(getattr(type(provider), f"generate_{runner.tool_name}", None))
            ):
                return runner
        return None

    def _detect_direct(
        self, runner: BaseRunner, provider: ProviderBase, provider_name: str, env_name: str
    ) -> DriftInfo:
        """Plan add-only through a direct runner and parse the result as drift.

        The environment's managed rows go to ``plan`` as ``infra plan`` does, so a
        resource an earlier apply adopted is labelled ``update``, not ``create``.
        """
        provider.set_environment(env_name)
        planner = cast(Plannable, runner)
        kwargs: dict[str, Any] = {}
        if self.state_manager is not None:
            kwargs["managed_resources"] = build_managed_resources(
                self.state_manager.get_managed_resources(env_name, provider_name), provider_name
            )
        plan_result = planner.plan(provider, add_only=True, env_name=env_name, **kwargs)
        return cast(DriftDetectable, runner).parse_plan_for_drift(plan_result)

    @override
    def cleanup(self) -> None:
        """Clean up resources (required by BaseManager).

        DriftDetector has no persistent resources to clean up.
        """
        self._log_debug("DriftDetector cleanup complete")
