"""Shell script handler for events."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import shutil
import subprocess  # nosec B404 - required for running user scripts
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, override

import jinja2

from infrafoundry.core.config.filters import create_jinja2_env
from infrafoundry.core.events.context import EventContext, EventResult
from infrafoundry.core.events.handlers.base import BaseHandler
from infrafoundry.core.warnings import emit_warning

if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger(__name__)


def _build_remote_bash(
    remote_dir: str,
    script_name: str,
    warnings_file: str | None = None,
) -> str:
    """Build the remote bash invocation used by jumphost reexec.

    The wrapper:
    - Fails fast if ``python3`` is missing on the jumphost. Python 3 is a
      hard requirement for ansible and is present in the base install of
      every modern Linux distro, making it strictly more portable than
      ``jq`` (which is not installed by default on Debian/Ubuntu).
    - Reads the full package-vars JSON blob from stdin into
      ``INFRAFOUNDRY_PACKAGE_VARS`` (no secrets on the ssh command line).
    - Re-exports each scalar entry as ``INFRAFOUNDRY_VAR_<key>`` so remote
      scripts see the same env var contract as local execution
      (``script.py:528-531``). Null-delimited python output keeps values
      with newlines/tabs/equals-signs intact.
    - Sets ``INFRAFOUNDRY_ON_JUMPHOST=1`` so blueprint shell helpers that
      implement their own reexec self-deactivate.
    - When ``warnings_file`` is provided, seeds that file on the remote
      side (``: > <path>``) and exports ``INFRAFOUNDRY_WARNINGS_FILE`` so
      the remote script can append JSONL records that the orchestrator
      later scp's back and folds into the local summary.

    Args:
        remote_dir: Absolute path of the rsynced script directory on the
            jumphost.
        script_name: Basename of the script to execute.
        warnings_file: Optional absolute path on the jumphost where remote
            code should append non-fatal warning JSONL records. When
            ``None``, no warnings plumbing is emitted (keeps existing
            callers that don't collect warnings simple).

    Returns:
        A single bash command string to pass to ``ssh``.
    """
    if warnings_file:
        # Seed the file first so scp-back always finds something to copy,
        # and export INFRAFOUNDRY_WARNINGS_FILE for the inner script (and
        # any nested subprocesses) to pick up.
        warnings_setup = (
            f': > "{warnings_file}"; export INFRAFOUNDRY_WARNINGS_FILE="{warnings_file}"; '
        )
    else:
        warnings_setup = ""

    return (
        "command -v python3 >/dev/null 2>&1 || { "
        'echo "infrafoundry: python3 is required on the jumphost '
        'to expand INFRAFOUNDRY_VAR_* env vars" >&2; exit 127; }; '
        f"{warnings_setup}"
        'INFRAFOUNDRY_ON_JUMPHOST=1 INFRAFOUNDRY_PACKAGE_VARS="$(cat)"; '
        "export INFRAFOUNDRY_ON_JUMPHOST INFRAFOUNDRY_PACKAGE_VARS; "
        'while IFS= read -r -d "" entry; do '
        'k="${entry%%=*}"; v="${entry#*=}"; '
        'export "INFRAFOUNDRY_VAR_$k=$v"; '
        "done < <("
        'printf %s "$INFRAFOUNDRY_PACKAGE_VARS" | '
        "python3 -c '"
        "import json,sys;"
        "d=json.load(sys.stdin);"
        '[sys.stdout.buffer.write(f"{k}={v}\\0".encode()) '
        "for k,v in d.items() "
        "if not isinstance(v,(dict,list))]"
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
        outputs: Optional list of artifact files the script produces, to be
            pulled back to the operator's workstation after a successful run.
            Each entry is ``{source: <path>, dest: <path>}``. Both fields are
            Jinja2-rendered against the package variables, and both must
            resolve to absolute paths (``/...`` or ``~/...``). During jumphost
            reexec the ``source`` is scp'd from the jumphost; during local
            execution it is copied with ``shutil.copy2``. All pull-back
            failures (missing source, scp error, permission denied) are
            non-fatal and logged as warnings via
            ``INFRAFOUNDRY_WARNINGS_FILE``. See
            ``docs/development/event-system.md`` for details.

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
        INFRAFOUNDRY_WARNINGS_FILE: Path to the per-apply JSONL warnings file
            (forwarded from the current process; on jumphost reexec the remote
            wrapper points this at a file under the remote tmp dir and the
            contents are scp'd back into the orchestrator's warnings summary).
            Scripts can append non-fatal warnings as one JSON object per line:
            ``echo '{"source":"x","message":"y"}' >> "$INFRAFOUNDRY_WARNINGS_FILE"``.

    Example config:
        type: script
        script: scripts/notify-slack.sh
        timeout: 60
        env:
          SLACK_CHANNEL: "#infra"

    Example with outputs (jumphost-executed blueprint writes a kubeconfig
    on the jumphost; framework scp's it back to the operator)::

        type: script
        script: scripts/proxmox/k3s-post-terraform.sh
        outputs:
          - source: "/tmp/k3s-{{ cluster_name }}/kubeconfig.yaml"
            dest:   "{{ kubeconfig_local_path }}"
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

        # Structural validation of optional outputs: list of dicts each with
        # string ``source`` and ``dest`` keys. The absolute-path check is
        # deferred to execute-time since the values may be Jinja2-templated
        # and need the runtime package variables to resolve.
        outputs = self.config.get("outputs")
        if outputs is not None:
            if not isinstance(outputs, list):
                errors.append("outputs must be a list")
            else:
                for idx, entry in enumerate(outputs):
                    if not isinstance(entry, dict):
                        errors.append(f"outputs[{idx}] must be a mapping")
                        continue
                    source = entry.get("source")
                    dest = entry.get("dest")
                    if not isinstance(source, str) or not source:
                        errors.append(f"outputs[{idx}] requires a non-empty 'source' string")
                    if not isinstance(dest, str) or not dest:
                        errors.append(f"outputs[{idx}] requires a non-empty 'dest' string")

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
        return self._execute_locally(script_path, working_dir, env, context)

    def _execute_locally(
        self,
        script_path: Path,
        working_dir: Path,
        env: dict[str, str],
        context: EventContext,
    ) -> EventResult:
        """Execute the script on the local host with real-time streaming.

        Args:
            script_path: Absolute path to the script to run
            working_dir: Working directory for the subprocess
            env: Environment variables for the subprocess
            context: Event context; forwarded to ``_process_outputs`` so
                declared ``outputs`` can be rendered against package
                variables on successful completion.

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
            if success:
                outputs = self.config.get("outputs") or []
                if outputs:
                    self._process_outputs(outputs, context)
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
        # Warnings collection: if the orchestrator has set up a local
        # warnings file, point the remote wrapper at a file under
        # `remote_dir` so any JSONL records the remote script appends can
        # be scp'd back and folded into the local summary. If the local
        # env var is unset, skip the plumbing entirely so unrelated
        # callers don't pay for it.
        local_warnings_path = env.get("INFRAFOUNDRY_WARNINGS_FILE")
        remote_warnings_path = f"{remote_dir}/warnings.jsonl" if local_warnings_path else None

        # Parity with _execute_locally: re-export each scalar package variable
        # as INFRAFOUNDRY_VAR_<key> on the remote side so scripts using the
        # documented contract work under `set -u`. Object/array values are
        # only exposed via INFRAFOUNDRY_PACKAGE_VARS (JSON) since they can't
        # round-trip as shell scalars. Uses null-delimited output from python3
        # so values containing newlines, tabs, or equals signs are safe.
        # Requires python3 on the jumphost (checked by the wrapper itself).
        remote_bash = _build_remote_bash(
            remote_dir, script_path.name, warnings_file=remote_warnings_path
        )
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
        success = False
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
            # Pull any warnings emitted by the remote script back onto the
            # operator's host and append them to the local warnings file.
            # Best-effort: scp/read failures are non-fatal — we still
            # clean up the remote dir below.
            if local_warnings_path and remote_warnings_path:
                self._fetch_remote_warnings(
                    jumphost,
                    ssh_opts,
                    remote_warnings_path,
                    Path(local_warnings_path),
                )
            # Pull declared outputs back from the jumphost. Gated on
            # ``success`` so failed runs don't ship partial artifacts; run
            # before cleanup so the remote tmp dir still exists. All scp
            # failures are non-fatal and surface as warnings.
            if success:
                outputs = self.config.get("outputs") or []
                if outputs:
                    self._process_outputs(
                        outputs,
                        context,
                        jumphost=jumphost,
                        ssh_opts=ssh_opts,
                    )
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

    def _fetch_remote_warnings(
        self,
        jumphost: str,
        ssh_opts: list[str],
        remote_warnings_path: str,
        local_warnings_path: Path,
    ) -> None:
        """Copy the remote warnings file back and append it to the local one.

        Uses ``scp`` (rather than ``ssh cat``) so stderr from the remote
        shell cannot mix into the data stream. Failure — missing file,
        empty file, ssh error — is non-fatal: the warnings collector is
        supplemental and must not break an otherwise-successful apply.

        Args:
            jumphost: SSH destination.
            ssh_opts: Shared ssh options (e.g. ``-o StrictHostKeyChecking=no``).
            remote_warnings_path: Absolute path on the jumphost.
            local_warnings_path: The orchestrator's local warnings file to
                append the remote content to.
        """
        with tempfile.NamedTemporaryFile(  # nosec B108 - managed lifecycle
            mode="wb",
            suffix=".jsonl",
            prefix="infrafoundry-remote-warnings-",
            delete=False,
        ) as staging:
            staging_path = Path(staging.name)
        try:
            scp_cmd = [
                "scp",
                *ssh_opts,
                f"{jumphost}:{remote_warnings_path}",
                str(staging_path),
            ]
            try:
                result = subprocess.run(  # nosec B603
                    scp_cmd,
                    capture_output=True,
                    timeout=60,
                )
            except (OSError, subprocess.TimeoutExpired) as e:
                logger.debug("scp of remote warnings file failed (ignored): %s", e)
                return
            if result.returncode != 0:
                logger.debug(
                    "scp of remote warnings file returned %d (ignored): %s",
                    result.returncode,
                    result.stderr.decode(errors="replace").strip() if result.stderr else "",
                )
                return
            try:
                remote_content = staging_path.read_bytes()
            except OSError as e:
                logger.debug("reading staged remote warnings failed (ignored): %s", e)
                return
            if not remote_content:
                return
            try:
                with open(local_warnings_path, "ab") as fh:
                    # Hold the lock for the duration of the append so we
                    # don't interleave with any other thread/process
                    # appending to the same file via emit_warning().
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                    try:
                        fh.write(remote_content)
                        if not remote_content.endswith(b"\n"):
                            fh.write(b"\n")
                        fh.flush()
                    finally:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError as e:
                logger.debug("appending remote warnings locally failed (ignored): %s", e)
        finally:
            try:
                staging_path.unlink(missing_ok=True)
            except OSError as e:
                logger.debug("removing staged remote warnings failed (ignored): %s", e)

    def _process_outputs(
        self,
        outputs: list[dict[str, Any]],
        context: EventContext,
        *,
        jumphost: str | None = None,
        ssh_opts: list[str] | None = None,
    ) -> None:
        """Copy declared script outputs back to the operator's workstation.

        Runs after a script handler reports success. Each entry's ``source``
        and ``dest`` are Jinja2-rendered against the package variables, both
        must resolve to absolute paths, and the destination's parent
        directory is created before the copy. When ``jumphost`` is provided
        the transport is ``scp`` (one invocation per entry); otherwise the
        copy is local (``shutil.copy2``). All failure modes — template
        errors, non-absolute paths, missing sources, scp non-zero, permission
        issues — are non-fatal: they emit a warning via
        :func:`infrafoundry.core.warnings.emit_warning` and the loop
        continues to the next entry.

        Args:
            outputs: The validated (possibly empty) ``outputs`` list from the
                handler config.
            context: The event context; ``package_variables`` is used as the
                Jinja2 template context.
            jumphost: SSH destination when the script ran on a jumphost.
                ``None`` for local execution.
            ssh_opts: Shared ssh options (e.g.
                ``["-o", "StrictHostKeyChecking=no"]``). Only used when
                ``jumphost`` is set.
        """
        if not outputs:
            return

        template_env = create_jinja2_env(undefined=jinja2.Undefined)
        template_context = dict(context.package_variables or {})

        for entry in outputs:
            raw_source = entry.get("source", "")
            raw_dest = entry.get("dest", "")
            try:
                rendered_source = template_env.from_string(raw_source).render(**template_context)
                rendered_dest = template_env.from_string(raw_dest).render(**template_context)
            except jinja2.TemplateError as exc:
                message = (
                    f"failed to render output template "
                    f"(source={raw_source!r}, dest={raw_dest!r}): {exc}"
                )
                logger.debug(message)
                emit_warning("script_handler_outputs", message)
                continue

            if not self._is_absolute_output_path(rendered_source):
                message = f"output source must be an absolute path (got {rendered_source!r})"
                logger.debug(message)
                emit_warning("script_handler_outputs", message)
                continue
            if not self._is_absolute_output_path(rendered_dest):
                message = f"output dest must be an absolute path (got {rendered_dest!r})"
                logger.debug(message)
                emit_warning("script_handler_outputs", message)
                continue

            # Expand ~ on the operator-side dest only. ``source`` is either
            # local (also operator-side, where expanding ~ is also fine) or
            # on the jumphost, in which case ``scp`` will expand ~ against
            # the remote user's home for us.
            local_dest = Path(rendered_dest).expanduser()
            try:
                local_dest.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                message = f"failed to create parent directory for {local_dest}: {exc}"
                logger.debug(message)
                emit_warning("script_handler_outputs", message)
                continue

            if jumphost is None:
                self._process_output_local(rendered_source, local_dest)
            else:
                self._process_output_remote(
                    jumphost,
                    ssh_opts or [],
                    rendered_source,
                    local_dest,
                )

    @staticmethod
    def _is_absolute_output_path(value: str) -> bool:
        """Return True if ``value`` looks like an absolute path for outputs.

        Absolute paths start with ``/``; ``~``-prefixed paths (``~`` alone,
        ``~/...``) are also accepted because they're resolvable either by
        :py:meth:`pathlib.Path.expanduser` on the operator side or by the
        remote shell when handed to ``scp``.
        """
        return value.startswith("/") or value.startswith("~")

    def _process_output_local(self, source: str, dest: Path) -> None:
        """Copy a single declared output between two local paths.

        Args:
            source: Rendered source path (absolute; ``~`` accepted).
            dest: Rendered destination path, already ``expanduser``'d.
        """
        source_path = Path(source).expanduser()
        if source_path == dest:
            logger.debug("output source == dest (%s); skipping local copy", dest)
            return
        if not source_path.exists():
            message = f"output source not found: {source_path}"
            logger.debug(message)
            emit_warning("script_handler_outputs", message)
            return
        try:
            shutil.copy2(source_path, dest)
        except OSError as exc:
            message = f"failed to copy {source_path} -> {dest}: {exc}"
            logger.debug(message)
            emit_warning("script_handler_outputs", message)

    def _process_output_remote(
        self,
        jumphost: str,
        ssh_opts: list[str],
        source: str,
        dest: Path,
    ) -> None:
        """Fetch a single declared output from the jumphost via ``scp``.

        Args:
            jumphost: SSH destination (``user@host`` or alias).
            ssh_opts: Shared ssh options reused from the parent handler.
            source: Absolute path on the jumphost. May contain ``~``, which
                the remote shell expands.
            dest: Destination path on the operator's workstation, already
                ``expanduser``'d and with its parent created.
        """
        scp_cmd = [
            "scp",
            *ssh_opts,
            f"{jumphost}:{source}",
            str(dest),
        ]
        try:
            result = subprocess.run(  # nosec B603
                scp_cmd,
                capture_output=True,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            message = f"scp of output {source} -> {dest} failed: {exc}"
            logger.debug(message)
            emit_warning("script_handler_outputs", message)
            return
        if result.returncode != 0:
            stderr_text = result.stderr.decode(errors="replace").strip() if result.stderr else ""
            message = (
                f"scp of output {source} -> {dest} returned {result.returncode}: {stderr_text}"
            )
            logger.debug(message)
            emit_warning("script_handler_outputs", message)

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
