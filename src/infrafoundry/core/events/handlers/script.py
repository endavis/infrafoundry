"""Shell script handler for events."""

import os
import re
import subprocess  # nosec B404 - required for running user scripts
import time
from pathlib import Path
from typing import Any, override

from infrafoundry.core.events.context import EventContext, EventResult
from infrafoundry.core.events.handlers.base import BaseHandler


class ScriptHandler(BaseHandler):
    """Handler that executes a shell script.

    Configuration:
        script: Path to script (relative to environment directory)
        env: Additional environment variables
        timeout: Maximum execution time in seconds (default: 300)
        continue_on_error: If True, don't abort on failure (default: False)
        description: Optional description for logging

    Environment variables injected:
        INFRAFOUNDRY_ENV: Environment name
        INFRAFOUNDRY_EVENT: Event type
        INFRAFOUNDRY_PROVIDER: Provider name (if applicable)
        INFRAFOUNDRY_RESOURCE: Resource name (if applicable)
        INFRAFOUNDRY_RUNNER: Runner name (if applicable, e.g., "terraform")
        INFRAFOUNDRY_CONFIG_DIR: Path to environment config directory

    Example config:
        type: script
        script: scripts/notify-slack.sh
        timeout: 60
        env:
          SLACK_CHANNEL: "#infra"
    """

    # Pattern to match {{ secrets.key }} or {{ secrets.key.subkey }}
    SECRET_PATTERN = re.compile(r"\{\{\s*secrets\.([a-zA-Z0-9_.]+)\s*\}\}")

    def __init__(
        self,
        config: dict[str, Any],
        config_base_dir: Path | None = None,
        secret_resolver: Any | None = None,
    ) -> None:
        """Initialize script handler.

        Args:
            config: Handler configuration
            config_base_dir: Base directory for config (contains envs/)
            secret_resolver: Optional callable to resolve secrets
        """
        super().__init__(config)
        self.config_base_dir = config_base_dir or Path.cwd()
        self.secret_resolver = secret_resolver

    @override
    def validate_config(self) -> list[str]:
        """Validate handler configuration."""
        errors: list[str] = []

        if "script" not in self.config:
            errors.append("Script handler requires 'script' field")

        timeout = self.config.get("timeout", 300)
        if not isinstance(timeout, int) or timeout < 1 or timeout > 3600:
            errors.append("Timeout must be an integer between 1 and 3600")

        return errors

    @override
    def execute(self, context: EventContext) -> EventResult:
        """Execute the script handler.

        Args:
            context: Event context

        Returns:
            EventResult with script output
        """
        env_dir = self.config_base_dir / "envs" / context.environment
        script_path = env_dir / self.config["script"]
        timeout = self.config.get("timeout", 300)

        # Validate script exists
        if not script_path.exists():
            return EventResult(
                success=False,
                reason=f"Script not found: {script_path}",
                handler_name=self.name,
            )

        # Validate script is executable
        if not os.access(script_path, os.X_OK):
            return EventResult(
                success=False,
                reason=f"Script not executable: {script_path}",
                handler_name=self.name,
            )

        # Prepare environment
        env = self._prepare_environment(context, env_dir)

        # Execute script
        start_time = time.monotonic()
        try:
            result = subprocess.run(  # nosec B603 - user-controlled scripts
                [str(script_path)],
                cwd=env_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration = time.monotonic() - start_time

            success = result.returncode == 0
            return EventResult(
                success=success,
                abort=not success and not self.config.get("continue_on_error", False),
                reason=None if success else f"Exit code: {result.returncode}",
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=duration,
                handler_name=self.name,
            )

        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start_time
            return EventResult(
                success=False,
                abort=not self.config.get("continue_on_error", False),
                reason=f"Timeout after {timeout} seconds",
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=e.stderr.decode() if e.stderr else "",
                duration_seconds=duration,
                handler_name=self.name,
            )

        except PermissionError:
            return EventResult(
                success=False,
                reason=f"Permission denied: {script_path}",
                handler_name=self.name,
                duration_seconds=time.monotonic() - start_time,
            )

        except OSError as e:
            return EventResult(
                success=False,
                reason=f"OS error: {e}",
                handler_name=self.name,
                duration_seconds=time.monotonic() - start_time,
            )

    def _prepare_environment(
        self,
        context: EventContext,
        working_dir: Path,
    ) -> dict[str, str]:
        """Prepare environment variables for script execution.

        Args:
            context: Event context
            working_dir: Working directory for script

        Returns:
            Environment variable dictionary
        """
        # Start with current environment
        env = os.environ.copy()

        # Add InfraFoundry-specific variables
        env["INFRAFOUNDRY_ENV"] = context.environment
        env["INFRAFOUNDRY_CONFIG_DIR"] = str(working_dir)
        env["INFRAFOUNDRY_EVENT"] = context.event_type.value

        if context.provider:
            env["INFRAFOUNDRY_PROVIDER"] = context.provider

        if context.resource:
            env["INFRAFOUNDRY_RESOURCE"] = context.resource

        if context.runner:
            env["INFRAFOUNDRY_RUNNER"] = context.runner

        if context.deployment_id:
            env["INFRAFOUNDRY_DEPLOYMENT_ID"] = str(context.deployment_id)

        # Add custom environment variables from config
        custom_env = self.config.get("env", {})
        for key, value in custom_env.items():
            resolved_value = self._resolve_secrets(value, context.environment)
            env[key] = resolved_value

        return env

    def _resolve_secrets(self, value: str, env_name: str) -> str:
        """Resolve {{ secrets.xxx }} templates in a value.

        Args:
            value: String that may contain secret templates
            env_name: Environment name for secret lookup

        Returns:
            Value with secrets resolved
        """
        if "{{" not in value or self.secret_resolver is None:
            return value

        def replace_secret(match: re.Match[str]) -> str:
            secret_path = match.group(1)
            if self.secret_resolver is None:
                return ""
            try:
                return str(self.secret_resolver(env_name, secret_path))
            except Exception:
                return ""

        return self.SECRET_PATTERN.sub(replace_secret, value)
