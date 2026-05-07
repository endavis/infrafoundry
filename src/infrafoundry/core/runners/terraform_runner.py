"""Terraform runner implementation."""

import json
import logging
import os
import re
import subprocess  # nosec B404 - required for running terraform
import threading
from pathlib import Path
from typing import IO, Any, cast, override

from rich.console import Console

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.types import ResourceOutcome

logger = logging.getLogger(__name__)


class TerraformRunner(BaseRunner):
    """Handles Terraform command execution and state management."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize Terraform runner.

        Args:
            console: Rich console for output (creates default if None)
        """
        super().__init__(console)

    @property
    @override
    def tool_name(self) -> str:
        """Return the name of the tool."""
        return "terraform"

    @property
    @override
    def priority(self) -> int:
        """Terraform must run first to provision resources."""
        return 0

    @property
    @override
    def is_iac_runner(self) -> bool:
        """Terraform is an IaC provisioner."""
        return True

    @override
    def is_available(self) -> bool:
        """Check if Terraform is installed."""
        try:
            _ = self.tool_path
            return True
        except FileNotFoundError:
            return False

    @override
    def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
        """Initialize Terraform in the working directory.

        Args:
            working_dir: Directory to initialize
            **kwargs: Additional terraform init options:
                - reconfigure (bool): Force reconfiguration of backend
                - migrate_state (bool): Migrate state to new backend
                - upgrade (bool): Upgrade provider plugins

        Returns:
            Dict with initialization results
        """
        if not self.is_available():
            return {"success": False, "error": "terraform command not found"}

        # Check if backend configuration exists
        backend_file = working_dir / "backend.tf"
        has_backend = backend_file.exists()

        # Check if already initialized
        is_initialized = (working_dir / ".terraform").exists()

        # Determine if we need to reinitialize for backend changes
        reconfigure = kwargs.get("reconfigure", False)
        migrate_state = kwargs.get("migrate_state", False)
        upgrade = kwargs.get("upgrade", False)

        # If already initialized, sniff the state file to detect a backend
        # swap so we can preemptively add -reconfigure (terraform would
        # otherwise error on the first re-init after a swap).
        if is_initialized and not (reconfigure or migrate_state or upgrade):
            terraform_state = working_dir / ".terraform" / "terraform.tfstate"
            if terraform_state.exists():
                import json

                try:
                    with open(terraform_state) as f:
                        state_data = json.load(f)
                        backend_type = state_data.get("backend", {}).get("type")

                        # If we have a backend.tf but state shows local backend (or no backend),
                        # or we don't have backend.tf but state shows remote backend,
                        # we need to reconfigure
                        if (has_backend and backend_type == "local") or (
                            not has_backend and backend_type and backend_type != "local"
                        ):
                            reconfigure = True
                            self.console.print(
                                "[yellow]Backend configuration changed, reconfiguring...[/yellow]"
                            )
                except (json.JSONDecodeError, FileNotFoundError):
                    pass

        # Always run terraform init. It's idempotent for unchanged configs
        # and cheap (~100ms no-op). Running it unconditionally avoids a
        # class of stale-lock / stale-.terraform bugs that arose when we
        # trusted .terraform/ presence as proof of consistency. See #524.
        cmd = [self.tool_path, "init"]
        if reconfigure:
            cmd.append("-reconfigure")
        if migrate_state:
            cmd.append("-migrate-state")
        if upgrade:
            cmd.append("-upgrade")

        try:
            if reconfigure:
                msg = "Reconfiguring Terraform backend..."
            elif migrate_state:
                msg = "Migrating Terraform state..."
            elif is_initialized:
                msg = "Refreshing Terraform init..."
            else:
                msg = "Initializing Terraform..."
            self.console.print(f"[dim]{msg}[/dim]")

            result = subprocess.run(  # nosec B603
                cmd,
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            return {"success": True, "output": result.stdout}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": str(e), "output": e.stderr}

    def plan(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Generate Terraform execution plan.

        Args:
            provider: Provider instance
            **kwargs: Additional terraform plan options:
                - target_resources: List of resource names to target with -target

        Returns:
            Dict with plan results
        """
        target_resources = kwargs.get("target_resources")
        return self._run_terraform(provider, "plan", target_resources=target_resources)

    def apply(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Apply Terraform configuration.

        Args:
            provider: Provider instance
            **kwargs: Options including auto_approve, target_resources, parallelism

        Returns:
            Dict with apply results
        """
        auto_approve = kwargs.get("auto_approve", False)
        target_resources = kwargs.get("target_resources")
        parallelism = kwargs.get("parallelism")
        return self._run_terraform(
            provider,
            "apply",
            auto_approve=auto_approve,
            target_resources=target_resources,
            parallelism=parallelism,
        )

    def destroy(self, provider: ProviderBase, **kwargs: Any) -> dict[str, Any]:
        """Destroy Terraform-managed infrastructure.

        Args:
            provider: Provider instance
            **kwargs: Options including auto_approve, target_resources, parallelism

        Returns:
            Dict with destroy results
        """
        auto_approve = kwargs.get("auto_approve", False)
        target_resources = kwargs.get("target_resources")
        parallelism = kwargs.get("parallelism")
        return self._run_terraform(
            provider,
            "destroy",
            auto_approve=auto_approve,
            target_resources=target_resources,
            parallelism=parallelism,
        )

    @override
    def get_version(self) -> str | None:
        """Get Terraform version."""
        if not self.is_available():
            return None

        try:
            result = subprocess.run(  # nosec B603
                [self.tool_path, "version", "-json"],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            return cast(str | None, data.get("terraform_version"))
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
            return None

    @override
    def validate_config(self, provider: ProviderBase) -> dict[str, Any]:
        """Validate Terraform configuration."""
        tf_dir = provider.terraform_dir

        if not tf_dir.exists():
            return {"valid": False, "error": "Terraform directory does not exist"}

        try:
            env = self._prepare_environment(provider)
            result = subprocess.run(  # nosec B603
                [self.tool_path, "validate"],
                cwd=tf_dir,
                capture_output=True,
                text=True,
                env=env,
            )
            return {
                "valid": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
            }
        except subprocess.CalledProcessError as e:
            return {"valid": False, "error": str(e)}

    def _run_terraform(
        self,
        provider: ProviderBase,
        command: str,
        auto_approve: bool = False,
        target_resources: list[str] | None = None,
        parallelism: int | None = None,
    ) -> dict[str, Any]:
        """Run Terraform command for a provider.

        For apply and destroy commands, the ``-json`` flag is added so that
        structured, line-delimited JSON is emitted on stdout.  This output
        is captured and parsed into :class:`ResourceOutcome` objects that
        describe what terraform did to each resource.  Human-readable
        progress information is printed to the console from the JSON
        ``message`` fields.

        Args:
            provider: Provider instance
            command: Terraform command (plan, apply, destroy)
            auto_approve: If True, add -auto-approve flag
            target_resources: Optional list of resource names to target with -target
            parallelism: Max number of concurrent terraform operations. When
                ``None`` (the default), terraform's built-in default of 10 is
                used.  Set to 1 to serialize all resource operations — useful
                for providers like Proxmox where parallel clones cause CFS lock
                timeouts on shared storage.

        Returns:
            Dict with command results.  For apply/destroy, includes a
            ``resource_outcomes`` key with a list of :class:`ResourceOutcome`.
        """
        tf_dir = provider.terraform_dir

        # Load credentials and set environment variables
        env = self._prepare_environment(provider)

        # Initialize if needed
        init_result = self.initialize(tf_dir)
        if not init_result.get("success"):
            return init_result

        # Build command using full path to terraform binary
        cmd = [self.tool_path, command]
        if auto_approve and command in {"apply", "destroy"}:
            cmd.append("-auto-approve")

        # Limit concurrent operations when requested (e.g. -parallelism=1
        # to serialize Proxmox VM clones that contend on NFS storage locks).
        if parallelism is not None and command in {"apply", "destroy", "plan"}:
            cmd.append(f"-parallelism={parallelism}")

        # Add -target flags for resource filtering
        if target_resources:
            targets = self._resolve_terraform_targets(tf_dir, target_resources)
            if not targets:
                self.console.print(
                    f"[yellow]Warning: No terraform resources matched filter: "
                    f"{target_resources} — skipping[/yellow]"
                )
                return {
                    "exit_code": 0,
                    "success": True,
                    "output": "",
                    "error": "",
                    "resource_outcomes": [],
                }
            for target in targets:
                cmd.extend(["-target", target])

        use_json = command in {"apply", "destroy"}
        if use_json:
            cmd.append("-json")

        if command == "plan":
            # Plan: capture stdout/stderr for drift parsing
            result = subprocess.run(  # nosec B603
                cmd,
                cwd=tf_dir,
                capture_output=True,
                text=True,
                env=env,
            )
            return {
                "exit_code": result.returncode,
                "success": result.returncode == 0,
                "output": result.stdout or "",
                "error": result.stderr or "",
            }

        # Apply/Destroy: capture JSON stdout, stream progress to console
        stdout_lines: list[str] = []
        process = subprocess.Popen(  # nosec B603
            cmd,
            cwd=tf_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        # Read stderr in background thread to prevent deadlock
        stderr_lines: list[str] = []
        stderr_thread = threading.Thread(
            target=self._collect_stream,
            args=(process.stderr, stderr_lines),
            daemon=True,
        )
        stderr_thread.start()

        # Read stdout (JSON lines) and display progress
        if process.stdout:
            for line in process.stdout:
                stripped = line.rstrip("\n")
                if not stripped:
                    continue
                stdout_lines.append(stripped)
                self._print_json_progress(stripped)

        process.wait()
        stderr_thread.join(timeout=10)

        stderr_text = "\n".join(stderr_lines)
        response: dict[str, Any] = {
            "exit_code": process.returncode,
            "success": process.returncode == 0,
            "stderr": stderr_text,
            "error": self._extract_error_summary(stdout_lines, stderr_text),
        }

        # Parse resource outcomes from JSON output
        outcomes = self._parse_json_output(stdout_lines, tf_dir, target_resources)
        response["resource_outcomes"] = outcomes
        # Store JSON-safe version for audit logging
        response["resource_outcomes_summary"] = [o.to_dict() for o in outcomes]

        return response

    @staticmethod
    def _extract_error_summary(stdout_lines: list[str], stderr_text: str) -> str:
        """Build a short error summary from terraform JSON diagnostics or stderr.

        Scans stdout for JSON ``diagnostic`` events with ``@level == "error"``
        and concatenates their ``summary`` fields. Falls back to a truncated
        stderr when no JSON diagnostics are present.

        Args:
            stdout_lines: Lines of terraform JSON output.
            stderr_text: Joined stderr content.

        Returns:
            Short human-readable error summary (possibly empty).
        """
        summaries: list[str] = []
        for line in stdout_lines:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("type") != "diagnostic":
                continue
            if data.get("@level") != "error":
                continue
            diagnostic = data.get("diagnostic", {})
            summary = diagnostic.get("summary") or data.get("@message", "")
            if summary:
                summaries.append(summary)

        if summaries:
            return "; ".join(summaries)

        # Fallback: truncated stderr
        if stderr_text:
            truncated = stderr_text.strip()
            if len(truncated) > 500:
                truncated = truncated[:500] + "..."
            return truncated
        return ""

    @staticmethod
    def _collect_stream(stream: IO[str] | None, collected: list[str]) -> None:
        """Read all lines from a stream into a list.

        Args:
            stream: The pipe to read
            collected: List to append lines to
        """
        if stream is None:
            return
        for line in stream:
            collected.append(line.rstrip("\n"))

    def _print_json_progress(self, json_line: str) -> None:
        """Extract and print a human-readable progress message from a JSON line.

        Args:
            json_line: A single line of terraform JSON output
        """
        try:
            data = json.loads(json_line)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type", "")
        message = data.get("@message", "")

        if msg_type in {"apply_start", "apply_progress", "apply_complete"}:
            if message:
                self.console.print(f"  [dim]{message}[/dim]")
        elif msg_type == "change_summary":
            if message:
                self.console.print(f"  {message}")
        elif msg_type == "diagnostic" and data.get("@level") == "error":
            detail = data.get("diagnostic", {}).get("summary", message)
            if detail:
                self.console.print(f"  [red]{detail}[/red]")

    def _parse_json_output(
        self,
        stdout_lines: list[str],
        tf_dir: Path,
        resource_names: list[str] | None = None,
    ) -> list[ResourceOutcome]:
        """Parse terraform JSON output lines into resource outcomes.

        Looks for ``apply_complete`` messages which indicate a resource
        action has finished.  Each such message contains the resource
        address and the action performed.

        Args:
            stdout_lines: Lines of JSON output from terraform
            tf_dir: Terraform working directory (for address-to-name mapping)
            resource_names: Optional list of known InfraFoundry resource names
                for suffix-based address mapping

        Returns:
            List of ResourceOutcome objects
        """
        address_to_name = self._build_address_to_name_map(tf_dir, resource_names)
        outcomes: list[ResourceOutcome] = []

        for line in stdout_lines:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if data.get("type") != "apply_complete":
                continue

            hook = data.get("hook", {})
            resource = hook.get("resource", {})
            address = resource.get("addr", "")
            action = hook.get("action", "noop")

            if not address:
                continue

            # Map terraform address back to resource name
            resource_name = address_to_name.get(address, "")
            if not resource_name:
                # Fallback: extract the name part from the address and convert
                # underscores back to dashes
                parts = address.rsplit(".", 1)
                resource_name = parts[-1].replace("_", "-") if parts else address

            outcomes.append(
                ResourceOutcome(
                    address=address,
                    action=action,
                    resource_name=resource_name,
                )
            )

        return outcomes

    def _build_address_to_name_map(
        self, tf_dir: Path, resource_names: list[str] | None = None
    ) -> dict[str, str]:
        """Build a mapping from terraform resource addresses to resource names.

        Scans ``.tf`` files for ``resource`` blocks and maps each
        ``type.tf_name`` address back to the original resource name.
        When *resource_names* is provided, suffix matching is used so that
        prefixed terraform names (e.g. ``ova_vm_ontapcl_01``) are correctly
        mapped back to their InfraFoundry name (``ontapcl-01``).

        Args:
            tf_dir: Terraform working directory
            resource_names: Optional list of known InfraFoundry resource names
                for suffix-based matching

        Returns:
            Dict mapping e.g. ``proxmox_vm.infra_web`` to ``infra-web``
        """
        known_tf_names = (
            {name.replace("-", "_") for name in resource_names} if resource_names else set()
        )
        address_map: dict[str, str] = {}
        resource_pattern = re.compile(r'^resource\s+"([^"]+)"\s+"([^"]+)"')

        for tf_file in tf_dir.glob("*.tf"):
            try:
                with open(tf_file) as f:
                    for file_line in f:
                        match = resource_pattern.match(file_line)
                        if match:
                            resource_type = match.group(1)
                            tf_name = match.group(2)
                            address = f"{resource_type}.{tf_name}"
                            # Resolve resource name using suffix matching
                            resource_name = self._resolve_resource_name(tf_name, known_tf_names)
                            address_map[address] = resource_name
            except OSError:
                continue

        return address_map

    @staticmethod
    def _resolve_resource_name(tf_name: str, known_tf_names: set[str]) -> str:
        """Resolve a terraform resource name back to an InfraFoundry resource name.

        Uses three strategies in order:
        1. Exact match against known resource names
        2. Suffix match for prefixed names (e.g. ``ova_vm_ontapcl_01`` → ``ontapcl-01``)
        3. Fallback: full name conversion (underscores to dashes)

        Args:
            tf_name: Terraform resource name (e.g. ``ova_vm_ontapcl_01``)
            known_tf_names: Known resource names in terraform form (underscores)

        Returns:
            InfraFoundry resource name (with dashes)
        """
        # 1. Exact match
        if tf_name in known_tf_names:
            return tf_name.replace("_", "-")

        # 2. Suffix match (handles prefixed names like ova_vm_ontapcl_01)
        if known_tf_names:
            for known in known_tf_names:
                if tf_name.endswith(f"_{known}"):
                    return known.replace("_", "-")

        # 3. Fallback: full name conversion
        return tf_name.replace("_", "-")

    @staticmethod
    def _name_matches_tf_name(infra_name: str, tf_name: str) -> bool:
        """Return True if *tf_name* corresponds to InfraFoundry *infra_name*.

        Matches either the exact dash-to-underscore conversion or a
        suffix match for templated/prefixed terraform names
        (e.g. ``ovf_ontap_node_01`` corresponds to ``ontap-node-01``).

        Args:
            infra_name: InfraFoundry resource name (dashes allowed).
            tf_name: Terraform resource name as it appears in state/.tf.

        Returns:
            True if ``tf_name`` represents ``infra_name``.
        """
        target = infra_name.replace("-", "_")
        return tf_name == target or tf_name.endswith(f"_{target}")

    def _resolve_terraform_targets(self, tf_dir: Path, resource_names: list[str]) -> list[str]:
        """Resolve resource names to terraform resource addresses.

        Scans generated .tf files for resource blocks matching the given names
        (with dashes converted to underscores).

        Args:
            tf_dir: Terraform working directory
            resource_names: List of resource names (e.g., ["infra-web", "esx-01"])

        Returns:
            List of terraform resource addresses (e.g.,
            ["proxmox_virtual_environment_vm.infra_web"])
        """
        targets: list[str] = []
        # Pattern matches: resource "type" "name" {
        resource_pattern = re.compile(r'^resource\s+"([^"]+)"\s+"([^"]+)"')

        for tf_file in tf_dir.glob("*.tf"):
            with open(tf_file) as f:
                for line in f:
                    match = resource_pattern.match(line)
                    if match:
                        resource_type = match.group(1)
                        resource_name = match.group(2)
                        # Exact match or suffix match for prefixed resources
                        # (e.g., "ovf_ontap_node_01" matches "ontap_node_01")
                        if any(
                            self._name_matches_tf_name(infra_name, resource_name)
                            for infra_name in resource_names
                        ):
                            targets.append(f"{resource_type}.{resource_name}")

        return targets

    def verify_destroyed(
        self, provider: ProviderBase, expected_destroyed_names: list[str]
    ) -> list[str]:
        """Return resource names that are still present in terraform state.

        Used after destroy to detect cases where terraform exited 0 but a
        resource remains in state (e.g. ``lifecycle { prevent_destroy }``
        blocks, partial failures, silent terraform quirks).

        Args:
            provider: Provider whose state to inspect.
            expected_destroyed_names: Names of resources that should no longer
                be in state.

        Returns:
            List of names from ``expected_destroyed_names`` that are still
            present. Empty list means verification passed.
        """
        current = self.get_resource_ids(provider)  # {tf_name: tf_address}
        still_present: list[str] = []
        for infra_name in expected_destroyed_names:
            for tf_name in current:
                if self._name_matches_tf_name(infra_name, tf_name):
                    still_present.append(infra_name)
                    break
        return still_present

    def state_list(self, working_dir: Path) -> list[str]:
        """List all resource addresses in terraform state.

        Runs ``terraform state list`` in the given directory and returns
        the resource addresses. Returns an empty list if no state file
        exists or the command fails.

        Args:
            working_dir: Terraform working directory containing state

        Returns:
            List of terraform resource addresses
        """
        state_file = working_dir / "terraform.tfstate"
        if not state_file.exists():
            return []

        try:
            result = subprocess.run(  # nosec B603
                [self.tool_path, "state", "list"],
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            addresses = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            return addresses
        except subprocess.CalledProcessError as e:
            logger.warning("terraform state list failed in %s: %s", working_dir, e.stderr)
            return []

    def state_rm(self, working_dir: Path, address: str) -> bool:
        """Remove a resource from terraform state without destroying it.

        Runs ``terraform state rm <address>`` in the given directory.

        Args:
            working_dir: Terraform working directory containing state
            address: Terraform resource address to remove

        Returns:
            True if the resource was successfully removed
        """
        try:
            subprocess.run(  # nosec B603
                [self.tool_path, "state", "rm", address],
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("Removed %s from terraform state in %s", address, working_dir)
            return True
        except subprocess.CalledProcessError as e:
            logger.warning("terraform state rm %s failed in %s: %s", address, working_dir, e.stderr)
            return False

    def get_resource_ids(self, provider: ProviderBase) -> dict[str, str]:
        """Extract Terraform resource IDs from state.

        Args:
            provider: Provider instance

        Returns:
            Dict mapping resource names to Terraform resource addresses
        """
        tf_dir = provider.terraform_dir

        try:
            # Run terraform show -json to get state
            result = subprocess.run(  # nosec B603
                [self.tool_path, "show", "-json"],
                cwd=tf_dir,
                capture_output=True,
                text=True,
                check=True,
            )

            state = json.loads(result.stdout)
            resource_ids = {}

            # Extract resource addresses from state
            if "values" in state and "root_module" in state["values"]:
                root = state["values"]["root_module"]
                if "resources" in root:
                    for resource in root["resources"]:
                        # Resource address format: provider_type.resource_name
                        address = resource.get("address")
                        name = resource.get("name")
                        if address and name:
                            resource_ids[name] = address

            return resource_ids

        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            self.console.print(f"[yellow]Warning: Could not extract Terraform IDs: {e}[/yellow]")
            return {}

    @staticmethod
    def extract_plan_summary(output: str) -> str:
        """Extract a one-line human-readable summary from terraform plan output.

        Scans *output* for Terraform's canonical
        ``Plan: N to add, M to change, K to destroy.`` line and returns the
        same shape as :meth:`parse_plan_for_drift`'s ``summary`` field. When
        no plan line is present but the output contains a "no changes"
        marker, ``"No changes"`` is returned. Empty or unparsable output
        falls through to the documented default ``"Unable to parse plan output"``
        so callers can render it verbatim and the operator can disambiguate
        "the runner produced no output" from "no changes were needed".

        Args:
            output: Captured terraform stdout from ``terraform plan``.

        Returns:
            A short summary like ``"21 to add, 0 to change, 0 to destroy"``,
            ``"No changes"``, or ``"Unable to parse plan output"`` when
            neither marker is found.
        """
        plan_pattern = r"Plan: (\d+) to add, (\d+) to change, (\d+) to destroy"
        match = re.search(plan_pattern, output)

        if match:
            to_add = int(match.group(1))
            to_change = int(match.group(2))
            to_destroy = int(match.group(3))

            # Mirror parse_plan_for_drift's summary: omit zero-counts so
            # "Plan: 1 to add, 0 to change, 0 to destroy." renders as
            # "1 to add" rather than the noisier full triple.
            parts = []
            if to_add > 0:
                parts.append(f"{to_add} to add")
            if to_change > 0:
                parts.append(f"{to_change} to change")
            if to_destroy > 0:
                parts.append(f"{to_destroy} to destroy")

            return ", ".join(parts) if parts else "No changes"

        if "No changes" in output or "no changes are needed" in output.lower():
            return "No changes"

        return "Unable to parse plan output"

    def parse_plan_for_drift(self, plan_result: dict[str, Any]) -> dict[str, Any]:
        """Parse Terraform plan output to detect drift.

        Args:
            plan_result: Result dictionary from run() with plan command

        Returns:
            Dict with drift information
        """
        output = plan_result.get("output", "")

        # Look for Terraform's plan summary line
        plan_pattern = r"Plan: (\d+) to add, (\d+) to change, (\d+) to destroy"
        match = re.search(plan_pattern, output)

        if match:
            to_add = int(match.group(1))
            to_change = int(match.group(2))
            to_destroy = int(match.group(3))

            has_changes = (to_add + to_change + to_destroy) > 0
            summary = self.extract_plan_summary(output)

            return {
                "has_changes": has_changes,
                "to_add": to_add,
                "to_change": to_change,
                "to_destroy": to_destroy,
                "summary": summary,
                "raw_output": output,
            }

        # If no plan line found, check for "No changes" message
        if "No changes" in output or "no changes are needed" in output.lower():
            return {
                "has_changes": False,
                "to_add": 0,
                "to_change": 0,
                "to_destroy": 0,
                "summary": "No changes",
                "raw_output": output,
            }

        # Unknown state
        return {
            "has_changes": None,
            "to_add": None,
            "to_change": None,
            "to_destroy": None,
            "summary": "Unable to parse plan output",
            "raw_output": output,
        }

    def _prepare_environment(self, provider: ProviderBase) -> dict[str, str]:
        """Prepare environment variables for Terraform execution.

        Merges provider-specific ``TF_VAR_*`` variables into the process
        environment so that Terraform reads credentials and settings from
        the environment instead of ``.tfvars`` files on disk.

        Args:
            provider: Provider instance

        Returns:
            Environment variables dict with TF_VAR_* entries
        """
        env = os.environ.copy()

        # Merge provider-specific TF_VAR_* env vars (settings + credentials)
        tf_vars = provider.get_terraform_env_vars()
        env.update(tf_vars)

        return env
