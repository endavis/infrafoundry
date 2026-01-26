"""Hook manager for executing lifecycle hooks."""

import os
import re
import subprocess  # nosec B404 - required for running user scripts
import time
from collections.abc import Callable
from pathlib import Path

from infrafoundry.core.base_manager import PathBasedManager
from infrafoundry.core.hooks.models import HookConfig, HookResult, HooksConfig
from infrafoundry.core.secrets.secret_manager import SecretManager


class HookExecutionError(Exception):
    """Raised when a hook execution fails and continue_on_error is False."""

    def __init__(self, message: str, result: HookResult) -> None:
        """Initialize hook execution error.

        Args:
            message: Error description
            result: The HookResult containing execution details
        """
        super().__init__(message)
        self.result = result


class HookManager(PathBasedManager):
    """Manages execution of lifecycle hooks.

    Hooks are user-defined scripts that run at specific points during
    infrastructure operations. The manager handles:
    - Script path resolution relative to environment directory
    - Environment variable injection (INFRAFOUNDRY_*, custom vars)
    - Secret template resolution ({{ secrets.xxx }})
    - Timeout enforcement
    - stdout/stderr capture and logging
    """

    # Pattern to match {{ secrets.key }} or {{ secrets.key.subkey }}
    SECRET_PATTERN = re.compile(r"\{\{\s*secrets\.([a-zA-Z0-9_.]+)\s*\}\}")

    def __init__(
        self,
        config_base_dir: Path,
        secret_manager_factory: Callable[[str], SecretManager],
    ) -> None:
        """Initialize hook manager.

        Args:
            config_base_dir: Base directory for configuration (contains envs/)
            secret_manager_factory: Factory function to create SecretManager for an environment
        """
        super().__init__()
        self.config_base_dir = config_base_dir
        self._secret_manager_factory = secret_manager_factory

    def execute_environment_hooks(
        self,
        env_name: str,
        stage: str,
        hooks_config: HooksConfig | None,
    ) -> list[HookResult]:
        """Execute environment-level hooks for a lifecycle stage.

        Args:
            env_name: Environment name
            stage: Lifecycle stage (e.g., "before_plan", "after_destroy")
            hooks_config: Hooks configuration from environment settings

        Returns:
            List of HookResult objects for each executed hook

        Raises:
            HookExecutionError: If a hook fails and continue_on_error is False
        """
        if not hooks_config:
            return []

        hooks = getattr(hooks_config, stage, [])
        if not hooks:
            return []

        env_dir = self.config_base_dir / "envs" / env_name
        self._log_info(f"Executing {len(hooks)} environment hook(s) for {stage}")

        return self._execute_hooks(
            hooks=hooks,
            env_name=env_name,
            stage=stage,
            working_dir=env_dir,
            resource_name=None,
            provider_name=None,
        )

    def execute_resource_hooks(
        self,
        env_name: str,
        stage: str,
        resource_name: str,
        provider_name: str,
        hooks_config: HooksConfig | None,
    ) -> list[HookResult]:
        """Execute resource-level hooks for a lifecycle stage.

        Args:
            env_name: Environment name
            stage: Lifecycle stage (e.g., "before_plan", "after_destroy")
            resource_name: Name of the resource
            provider_name: Name of the provider
            hooks_config: Hooks configuration from resource config

        Returns:
            List of HookResult objects for each executed hook

        Raises:
            HookExecutionError: If a hook fails and continue_on_error is False
        """
        if not hooks_config:
            return []

        hooks = getattr(hooks_config, stage, [])
        if not hooks:
            return []

        env_dir = self.config_base_dir / "envs" / env_name
        self._log_info(f"Executing {len(hooks)} resource hook(s) for {stage} on {resource_name}")

        return self._execute_hooks(
            hooks=hooks,
            env_name=env_name,
            stage=stage,
            working_dir=env_dir,
            resource_name=resource_name,
            provider_name=provider_name,
        )

    def _execute_hooks(
        self,
        hooks: list[HookConfig],
        env_name: str,
        stage: str,
        working_dir: Path,
        resource_name: str | None,
        provider_name: str | None,
    ) -> list[HookResult]:
        """Execute a list of hooks.

        Args:
            hooks: List of hook configurations to execute
            env_name: Environment name
            stage: Lifecycle stage
            working_dir: Working directory for script execution
            resource_name: Resource name (None for environment-level hooks)
            provider_name: Provider name (None for environment-level hooks)

        Returns:
            List of HookResult objects

        Raises:
            HookExecutionError: If a hook fails and continue_on_error is False
        """
        results: list[HookResult] = []

        for hook in hooks:
            result = self._execute_single_hook(
                hook=hook,
                env_name=env_name,
                stage=stage,
                working_dir=working_dir,
                resource_name=resource_name,
                provider_name=provider_name,
            )
            results.append(result)

            if not result.success and not hook.continue_on_error:
                error_msg = f"Hook '{hook.script}' failed: {result.error_message or result.stderr}"
                self._log_error(error_msg)
                raise HookExecutionError(error_msg, result)

        return results

    def _execute_single_hook(
        self,
        hook: HookConfig,
        env_name: str,
        stage: str,
        working_dir: Path,
        resource_name: str | None,
        provider_name: str | None,
    ) -> HookResult:
        """Execute a single hook script.

        Args:
            hook: Hook configuration
            env_name: Environment name
            stage: Lifecycle stage
            working_dir: Working directory for script execution
            resource_name: Resource name (None for environment-level hooks)
            provider_name: Provider name (None for environment-level hooks)

        Returns:
            HookResult with execution details
        """
        script_path = working_dir / hook.script

        # Validate script exists
        if not script_path.exists():
            return HookResult(
                script=hook.script,
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_seconds=0.0,
                timed_out=False,
                error_message=f"Script not found: {script_path}",
            )

        # Validate script is executable
        if not os.access(script_path, os.X_OK):
            return HookResult(
                script=hook.script,
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_seconds=0.0,
                timed_out=False,
                error_message=f"Script not executable: {script_path}",
            )

        # Prepare environment variables
        env = self._prepare_environment(
            hook=hook,
            env_name=env_name,
            stage=stage,
            working_dir=working_dir,
            resource_name=resource_name,
            provider_name=provider_name,
        )

        # Log execution
        desc = hook.description or hook.script
        if resource_name:
            self._log_info(f"Running hook: {desc} (resource: {resource_name})")
        else:
            self._log_info(f"Running hook: {desc}")

        # Execute script
        start_time = time.monotonic()
        try:
            result = subprocess.run(  # nosec B603 - user-controlled scripts
                [str(script_path)],
                cwd=working_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=hook.timeout,
            )
            duration = time.monotonic() - start_time

            return HookResult(
                script=hook.script,
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=duration,
                timed_out=False,
                error_message=None if result.returncode == 0 else f"Exit code: {result.returncode}",
            )

        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start_time
            return HookResult(
                script=hook.script,
                success=False,
                exit_code=-1,
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=e.stderr.decode() if e.stderr else "",
                duration_seconds=duration,
                timed_out=True,
                error_message=f"Timeout after {hook.timeout} seconds",
            )

        except PermissionError:
            duration = time.monotonic() - start_time
            return HookResult(
                script=hook.script,
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_seconds=duration,
                timed_out=False,
                error_message=f"Permission denied: {script_path}",
            )

        except OSError as e:
            duration = time.monotonic() - start_time
            return HookResult(
                script=hook.script,
                success=False,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_seconds=duration,
                timed_out=False,
                error_message=f"OS error: {e}",
            )

    def _prepare_environment(
        self,
        hook: HookConfig,
        env_name: str,
        stage: str,
        working_dir: Path,
        resource_name: str | None,
        provider_name: str | None,
    ) -> dict[str, str]:
        """Prepare environment variables for hook execution.

        Injects INFRAFOUNDRY_* variables and resolves secret templates
        in custom environment variables.

        Args:
            hook: Hook configuration
            env_name: Environment name
            stage: Lifecycle stage
            working_dir: Working directory
            resource_name: Resource name (None for environment-level hooks)
            provider_name: Provider name (None for environment-level hooks)

        Returns:
            Complete environment variable dictionary
        """
        # Start with current environment
        env = os.environ.copy()

        # Add InfraFoundry-specific variables
        env["INFRAFOUNDRY_ENV"] = env_name
        env["INFRAFOUNDRY_CONFIG_DIR"] = str(working_dir)
        env["INFRAFOUNDRY_EVENT"] = stage

        if resource_name:
            env["INFRAFOUNDRY_RESOURCE"] = resource_name

        if provider_name:
            env["INFRAFOUNDRY_PROVIDER"] = provider_name

        # Resolve custom environment variables with secret templates
        for key, value in hook.env.items():
            resolved_value = self._resolve_secret_templates(value, env_name)
            env[key] = resolved_value

        return env

    def _resolve_secret_templates(self, value: str, env_name: str) -> str:
        """Resolve {{ secrets.xxx }} templates in a value.

        Args:
            value: String that may contain secret templates
            env_name: Environment name for secret lookup

        Returns:
            Value with secrets resolved, or original value if no templates
        """
        if "{{" not in value:
            return value

        def replace_secret(match: re.Match[str]) -> str:
            secret_path = match.group(1)
            try:
                secret_manager = self._secret_manager_factory(env_name)
                # Split path into file and key
                # e.g., "tailscale.api_key" -> "tailscale.yaml", "api_key"
                parts = secret_path.split(".", 1)
                if len(parts) == 1:
                    # Just a filename, return the whole file as string (unlikely use case)
                    self._log_warning(f"Secret path '{secret_path}' has no key, returning empty")
                    return ""

                filename = f"{parts[0]}.yaml"
                key = parts[1]
                return str(secret_manager.get_secret(filename, key))
            except (FileNotFoundError, KeyError) as e:
                self._log_warning(f"Secret '{secret_path}' not found: {e}")
                return ""

        return self.SECRET_PATTERN.sub(replace_secret, value)

    def cleanup(self) -> None:
        """Clean up resources (required by BaseManager)."""
        self._log_debug("HookManager cleanup complete")
