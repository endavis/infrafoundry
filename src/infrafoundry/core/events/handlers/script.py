"""Shell script handler for events."""

from __future__ import annotations

import json
import os
import re
import subprocess  # nosec B404 - required for running user scripts
import threading
import time
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, override

from infrafoundry.core.events.context import EventContext, EventResult
from infrafoundry.core.events.handlers.base import BaseHandler

if TYPE_CHECKING:
    from rich.console import Console


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
        INFRAFOUNDRY_PHASE: Workflow phase (if applicable, e.g., "plan", "apply", "destroy")
        INFRAFOUNDRY_CONFIG_DIR: Path to environment config directory
        INFRAFOUNDRY_PACKAGE_VARS: JSON string of all package variables (if available)
        INFRAFOUNDRY_VAR_<key>: Individual package variable values (if available)

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
        console: Console | None = None,
    ) -> None:
        """Initialize script handler.

        Args:
            config: Handler configuration
            config_base_dir: Base directory for config (contains envs/)
            secret_resolver: Optional callable to resolve secrets
            console: Rich console for real-time output streaming
        """
        super().__init__(config)
        self.config_base_dir = config_base_dir or Path.cwd()
        self.secret_resolver = secret_resolver
        self.console = console

    @override
    def validate_config(self) -> list[str]:
        """Validate handler configuration."""
        errors: list[str] = []

        if "script" not in self.config:
            errors.append("Script handler requires 'script' field")

        timeout = self.config.get("timeout", 300)
        if not isinstance(timeout, int) or timeout < 1 or timeout > 14400:
            errors.append("Timeout must be an integer between 1 and 14400")

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
        raw_script = self.config["script"]
        timeout = self.config.get("timeout", 300)

        # Resolve script path: absolute paths (from blueprint resolution)
        # are used directly; relative paths are resolved against env_dir
        script_candidate = Path(raw_script)
        script_path = script_candidate if script_candidate.is_absolute() else env_dir / raw_script

        # Determine working directory: blueprint dir if set, else env_dir
        blueprint_dir_str = self.config.get("_blueprint_dir")
        working_dir = Path(blueprint_dir_str) if blueprint_dir_str else env_dir

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

        # Inject blueprint-specific env vars
        if blueprint_dir_str:
            env["INFRAFOUNDRY_BLUEPRINT_DIR"] = blueprint_dir_str

        # Inject inventory path if a generated inventory exists
        package_dir = self.config.get("_package_dir")
        if package_dir:
            inventory_path = Path(package_dir) / ".generated-inventory.yml"
            if inventory_path.exists():
                env["INFRAFOUNDRY_INVENTORY"] = str(inventory_path)

        # Execute script with real-time streaming
        start_time = time.monotonic()
        try:
            process = subprocess.Popen(  # nosec B603 - user-controlled scripts
                [str(script_path)],
                cwd=working_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            stdout_lines: list[str] = []
            stderr_lines: list[str] = []

            stdout_thread = threading.Thread(
                target=self._read_stream,
                args=(process.stdout, stdout_lines, ""),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=self._read_stream,
                args=(process.stderr, stderr_lines, "red"),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)
                duration = time.monotonic() - start_time
                return EventResult(
                    success=False,
                    abort=not self.config.get("continue_on_error", False),
                    reason=f"Timeout after {timeout} seconds",
                    stdout="\n".join(stdout_lines),
                    stderr="\n".join(stderr_lines),
                    duration_seconds=duration,
                    handler_name=self.name,
                )

            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            duration = time.monotonic() - start_time

            success = process.returncode == 0
            return EventResult(
                success=success,
                abort=not success and not self.config.get("continue_on_error", False),
                reason=None if success else f"Exit code: {process.returncode}",
                stdout="\n".join(stdout_lines),
                stderr="\n".join(stderr_lines),
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

    def _read_stream(
        self,
        stream: IO[str] | None,
        collected: list[str],
        style: str = "",
    ) -> None:
        """Read a stream line-by-line, optionally printing to console.

        Args:
            stream: The stdout or stderr pipe to read
            collected: List to append lines to for later capture
            style: Rich style name for console output (e.g. "red" for stderr)
        """
        if stream is None:
            return
        for line in stream:
            stripped = line.rstrip("\n")
            collected.append(stripped)
            if self.console is not None:
                if style:
                    self.console.print(f"    [{style}]{stripped}[/{style}]")
                else:
                    self.console.print(f"    {stripped}")

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

        if phase := context.data.get("phase"):
            env["INFRAFOUNDRY_PHASE"] = str(phase)

        if context.deployment_id:
            env["INFRAFOUNDRY_DEPLOYMENT_ID"] = str(context.deployment_id)

        if context.target_resources:
            env["INFRAFOUNDRY_TARGET_RESOURCES"] = ",".join(context.target_resources)

        # Add package variables as JSON and individual env vars
        if context.package_variables:
            env["INFRAFOUNDRY_PACKAGE_VARS"] = json.dumps(context.package_variables)
            for key, value in context.package_variables.items():
                env[f"INFRAFOUNDRY_VAR_{key}"] = str(value)

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
