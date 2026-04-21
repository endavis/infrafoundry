"""Shell script handler for events."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess  # nosec B404 - required for running user scripts
import threading
import time
import uuid
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, override

from infrafoundry.core.events.context import EventContext, EventResult
from infrafoundry.core.events.handlers.base import BaseHandler

if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger(__name__)


def _build_remote_bash(remote_dir: str, script_name: str) -> str:
    """Build the remote bash invocation used by jumphost reexec.

    The wrapper:
    - Reads the full package-vars JSON blob from stdin into
      ``INFRAFOUNDRY_PACKAGE_VARS`` (no secrets on the ssh command line).
    - Re-exports each scalar entry as ``INFRAFOUNDRY_VAR_<key>`` so remote
      scripts see the same env var contract as local execution
      (``script.py:528-531``). Null-delimited jq output keeps values with
      newlines/tabs/equals-signs intact.
    - Sets ``INFRAFOUNDRY_ON_JUMPHOST=1`` so blueprint shell helpers that
      implement their own reexec self-deactivate.

    Args:
        remote_dir: Absolute path of the rsynced script directory on the
            jumphost.
        script_name: Basename of the script to execute.

    Returns:
        A single bash command string to pass to ``ssh``.
    """
    return (
        'INFRAFOUNDRY_ON_JUMPHOST=1 INFRAFOUNDRY_PACKAGE_VARS="$(cat)"; '
        "export INFRAFOUNDRY_ON_JUMPHOST INFRAFOUNDRY_PACKAGE_VARS; "
        'while IFS= read -r -d "" entry; do '
        'k="${entry%%=*}"; v="${entry#*=}"; '
        'export "INFRAFOUNDRY_VAR_$k=$v"; '
        "done < <("
        'printf %s "$INFRAFOUNDRY_PACKAGE_VARS" | '
        "jq -j 'to_entries[] "
        '| select(.value | type != "object" and type != "array") '
        '| "\\(.key)=\\(.value|tostring)\\u0000"'
        "'"
        "); "
        f"bash {remote_dir}/{script_name}"
    )


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
        INFRAFOUNDRY_PACKAGE_DIR: Path to consuming env package directory (if applicable)
        INFRAFOUNDRY_BLUEPRINT_DIR: Path to blueprint directory (if dispatched from blueprint)
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

        # Inject package dir so blueprint scripts can locate consumer-side
        # artifacts (e.g., generated inventory) without deriving them from
        # $(dirname "$0"), which resolves to the blueprint dir.
        package_dir = self.config.get("_package_dir")
        if package_dir:
            env["INFRAFOUNDRY_PACKAGE_DIR"] = str(package_dir)

        # Inject inventory path if a generated inventory exists
        if package_dir:
            inventory_path = Path(package_dir) / ".generated-inventory.yml"
            if inventory_path.exists():
                env["INFRAFOUNDRY_INVENTORY"] = str(inventory_path)

        # Dispatch: jumphost reexec if configured, else run locally.
        # The INFRAFOUNDRY_ON_JUMPHOST env guard prevents double-reexec if the
        # framework is ever invoked on the jumphost itself with that flag set.
        jumphost = str((context.package_variables or {}).get("jumphost", "")).strip()
        if jumphost and not os.environ.get("INFRAFOUNDRY_ON_JUMPHOST"):
            return self._execute_on_jumphost(script_path, env, context, jumphost)
        return self._execute_locally(script_path, working_dir, env)

    def _execute_locally(
        self,
        script_path: Path,
        working_dir: Path,
        env: dict[str, str],
    ) -> EventResult:
        """Execute the script on the local host with real-time streaming.

        Args:
            script_path: Absolute path to the script to run
            working_dir: Working directory for the subprocess
            env: Environment variables for the subprocess

        Returns:
            EventResult with captured stdout/stderr and exit status
        """
        timeout = self.config.get("timeout", 300)
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
                data={"returncode": process.returncode},
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

    def _execute_on_jumphost(
        self,
        script_path: Path,
        env: dict[str, str],
        context: EventContext,
        jumphost: str,
    ) -> EventResult:
        """Execute the script on a remote jumphost via SSH.

        Rsyncs the script's parent directory to a temp directory on the
        jumphost, then re-executes the script remotely. The package variables
        (minus ``jumphost``) are forwarded as JSON on stdin so secrets never
        appear on the command line or in remote ``ps`` output. The remote
        process sees ``INFRAFOUNDRY_ON_JUMPHOST=1`` so any blueprint-side shell
        helper that also implements reexec logic self-deactivates.

        Args:
            script_path: Absolute path to the script on the operator's host
            env: Environment variables used when invoking ssh locally
            context: Event context (source of ``package_variables``)
            jumphost: SSH destination (``user@host`` or host alias)

        Returns:
            EventResult with remote stdout/stderr and exit status
        """
        timeout = self.config.get("timeout", 300)
        script_dir = script_path.parent
        remote_dir = f"/tmp/infrafoundry-{uuid.uuid4().hex}"  # nosec B108

        # Strip 'jumphost' from forwarded package variables so any remote
        # script that branches on ${jumphost:-} does not attempt another hop.
        remote_vars = dict(context.package_variables or {})
        remote_vars.pop("jumphost", None)
        remote_vars_json = json.dumps(remote_vars)

        ssh_opts = ["-o", "StrictHostKeyChecking=no"]
        mkdir_cmd = ["ssh", *ssh_opts, jumphost, f"mkdir -p {remote_dir}"]
        rsync_cmd = [
            "rsync",
            "-a",
            "-e",
            "ssh -o StrictHostKeyChecking=no",
            f"{script_dir}/",
            f"{jumphost}:{remote_dir}/",
        ]
        # Parity with _execute_locally: re-export each scalar package variable
        # as INFRAFOUNDRY_VAR_<key> on the remote side so scripts using the
        # documented contract work under `set -u`. Object/array values are
        # only exposed via INFRAFOUNDRY_PACKAGE_VARS (JSON) since they can't
        # round-trip as shell scalars. Uses null-delimited output from jq so
        # values containing newlines, tabs, or equals signs are safe. Requires
        # jq on the jumphost.
        remote_bash = _build_remote_bash(remote_dir, script_path.name)
        ssh_run_cmd = ["ssh", *ssh_opts, jumphost, remote_bash]
        cleanup_cmd = ["ssh", *ssh_opts, jumphost, f"rm -rf {remote_dir}"]

        start_time = time.monotonic()

        # Step 1: mkdir remote tmp dir
        try:
            mkdir_result = subprocess.run(  # nosec B603
                mkdir_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            return EventResult(
                success=False,
                abort=not self.config.get("continue_on_error", False),
                reason=f"remote mkdir failed: {e}",
                duration_seconds=time.monotonic() - start_time,
                handler_name=self.name,
            )
        if mkdir_result.returncode != 0:
            return EventResult(
                success=False,
                abort=not self.config.get("continue_on_error", False),
                reason=f"remote mkdir failed: {mkdir_result.stderr.strip()}",
                stdout=mkdir_result.stdout,
                stderr=mkdir_result.stderr,
                duration_seconds=time.monotonic() - start_time,
                handler_name=self.name,
            )

        # Step 2: rsync script directory to jumphost
        try:
            rsync_result = subprocess.run(  # nosec B603
                rsync_cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            self._cleanup_remote(cleanup_cmd)
            return EventResult(
                success=False,
                abort=not self.config.get("continue_on_error", False),
                reason=f"rsync setup failed: {e}",
                duration_seconds=time.monotonic() - start_time,
                handler_name=self.name,
            )
        if rsync_result.returncode != 0:
            self._cleanup_remote(cleanup_cmd)
            return EventResult(
                success=False,
                abort=not self.config.get("continue_on_error", False),
                reason=f"rsync setup failed: {rsync_result.stderr.strip()}",
                stdout=rsync_result.stdout,
                stderr=rsync_result.stderr,
                duration_seconds=time.monotonic() - start_time,
                handler_name=self.name,
            )

        # Step 3: run the script remotely with streaming output.
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        try:
            try:
                process = subprocess.Popen(  # nosec B603
                    ssh_run_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
            except OSError as e:
                return EventResult(
                    success=False,
                    abort=not self.config.get("continue_on_error", False),
                    reason=f"failed to launch remote ssh: {e}",
                    duration_seconds=time.monotonic() - start_time,
                    handler_name=self.name,
                )

            # Forward package vars JSON via stdin, then close it so the
            # remote $(cat) returns.
            if process.stdin is not None:
                try:
                    process.stdin.write(remote_vars_json)
                    process.stdin.close()
                except BrokenPipeError:
                    pass

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
                data={"returncode": process.returncode},
                handler_name=self.name,
            )
        finally:
            self._cleanup_remote(cleanup_cmd)

    def _cleanup_remote(self, cleanup_cmd: list[str]) -> None:
        """Run the remote tmp dir cleanup, swallowing all errors.

        Args:
            cleanup_cmd: The full ssh+rm-rf command list to run
        """
        try:
            result = subprocess.run(  # nosec B603
                cleanup_cmd,
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(
                    "Remote cleanup failed (ignored): %s",
                    result.stderr.decode(errors="replace").strip()
                    if result.stderr
                    else f"exit {result.returncode}",
                )
        except (OSError, subprocess.TimeoutExpired) as e:
            logger.warning("Remote cleanup failed (ignored): %s", e)

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
