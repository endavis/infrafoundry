"""Kubeconfig validation for Kubernetes provider."""

from __future__ import annotations

import base64
import binascii
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, override

import yaml

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.kubernetes.validators.context import KubeconfigContext


@dataclass
class KubeConnectionInfo:
    """Connection information extracted from kubeconfig."""

    server_url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True
    connected: bool = False
    client_cert: tuple[str, str] | None = None
    ca_bundle: str | None = None


class KubeconfigValidator(SpecializedValidator[KubeconfigContext]):
    """Validates kubeconfig file and establishes connection info.

    Parses the kubeconfig to extract server URL, bearer token or client
    certificate, and CA certificate info. Tests API connectivity and stores
    connection state for other validators.

    Inline certificate and key data is written to files in a private temporary
    directory (mode 0700, files 0600). Call :meth:`cleanup` when the connection
    is no longer needed; it removes the directory.
    """

    def __init__(self, api_validator: BaseAPIValidator, report: ValidationReport) -> None:
        """Initialize kubeconfig validator.

        Args:
            api_validator: Shared API validator helper
            report: ValidationReport to add results to
        """
        self.api_validator = api_validator
        self.report = report
        self._connection_info = KubeConnectionInfo()
        self._temp_dir: Path | None = None
        self._client_cert: tuple[str, str] | None = None

    @property
    def is_connected(self) -> bool:
        """Whether API connectivity was successfully established."""
        return self._connection_info.connected

    @property
    def connection_info(self) -> KubeConnectionInfo:
        """Connection info extracted from kubeconfig."""
        return self._connection_info

    def cleanup(self) -> None:
        """Remove the temporary credential files and drop the connection.

        Safe to call more than once. When files had been written, the connection is
        marked as not connected, since its certificate paths no longer exist.
        """
        if self._temp_dir is None:
            return
        shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir = None
        self._client_cert = None
        self._connection_info = KubeConnectionInfo(
            server_url=self._connection_info.server_url,
            headers=self._connection_info.headers,
            verify_ssl=self._connection_info.verify_ssl,
        )

    def _write_secret_file(self, name: str, content: bytes) -> str:
        """Write credential bytes to a 0600 file in the private temp directory.

        Args:
            name: File name inside the temporary directory.
            content: Bytes to write.

        Returns:
            Path of the written file.
        """
        if self._temp_dir is None:
            self._temp_dir = Path(tempfile.mkdtemp(prefix="infrafoundry-kube-"))
            self._temp_dir.chmod(0o700)
        path = self._temp_dir / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        return str(path)

    @override
    def validate(self, context: KubeconfigContext) -> None:
        """Validate kubeconfig and test API connectivity.

        Args:
            context: Kubeconfig path and optional context override.
        """
        self.cleanup()
        kubeconfig_path = context.kubeconfig_path
        context_override = context.context_override
        resolved_path = self._resolve_kubeconfig_path(kubeconfig_path)
        if resolved_path is None:
            return

        kubeconfig_data = self._load_kubeconfig(resolved_path)
        if kubeconfig_data is None:
            return

        context_name = self._resolve_context(kubeconfig_data, context_override)
        if context_name is None:
            return

        context_entry = self._get_context_entry(kubeconfig_data, context_name)
        if context_entry is None:
            return

        cluster_name = context_entry.get("context", {}).get("cluster")
        user_name = context_entry.get("context", {}).get("user")

        cluster_info = self._get_cluster_info(kubeconfig_data, cluster_name)
        if cluster_info is None:
            return

        server_url = cluster_info.get("server", "")
        if not server_url:
            self.report.add_check(
                check_name="kubernetes_kubeconfig",
                passed=False,
                message=f"Cluster '{cluster_name}' has no server URL",
                level=ValidationLevel.ERROR,
            )
            return

        # Extract auth info
        headers = self._extract_auth_headers(kubeconfig_data, user_name)
        verify_ssl = self._resolve_ca_cert(cluster_info)

        self._connection_info = KubeConnectionInfo(
            server_url=server_url.rstrip("/"),
            headers=headers,
            verify_ssl=verify_ssl,
            client_cert=self._client_cert,
            ca_bundle=self._resolve_ca_bundle(cluster_info) if verify_ssl else None,
        )

        # Test connectivity
        self._test_connectivity()

    def _resolve_kubeconfig_path(self, kubeconfig_path: str | None) -> Path | None:
        """Resolve and validate the kubeconfig file path."""
        if not kubeconfig_path:
            default_path = Path.home() / ".kube" / "config"
            if default_path.exists():
                self.report.add_check(
                    check_name="kubernetes_kubeconfig",
                    passed=True,
                    message=f"Using default kubeconfig at {default_path}",
                    level=ValidationLevel.INFO,
                )
                return default_path
            self.report.add_check(
                check_name="kubernetes_kubeconfig",
                passed=False,
                message=(
                    "No kubeconfig found (KUBECONFIG, kubeconfig_path, ~/.kube/config); "
                    "cluster checks skipped"
                ),
                level=ValidationLevel.WARNING,
            )
            return None

        path = Path(kubeconfig_path).expanduser()
        if not path.exists():
            self.report.add_check(
                check_name="kubernetes_kubeconfig",
                passed=False,
                message=(
                    f"Kubeconfig not found at {path}; cluster checks skipped (the cluster "
                    "may not exist yet, for example one created earlier in the same apply)"
                ),
                level=ValidationLevel.WARNING,
            )
            return None

        self.report.add_check(
            check_name="kubernetes_kubeconfig",
            passed=True,
            message=f"Kubeconfig found at {path}",
        )
        return path

    def _load_kubeconfig(self, path: Path) -> dict[str, Any] | None:
        """Load and parse the kubeconfig YAML file."""
        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                self.report.add_check(
                    check_name="kubernetes_kubeconfig_parse",
                    passed=False,
                    message=f"Kubeconfig at {path} is not valid YAML mapping",
                    level=ValidationLevel.ERROR,
                )
                return None
            return data
        except yaml.YAMLError as exc:
            self.report.add_check(
                check_name="kubernetes_kubeconfig_parse",
                passed=False,
                message=f"Failed to parse kubeconfig at {path}: {exc}",
                level=ValidationLevel.ERROR,
            )
            return None
        except OSError as exc:
            self.report.add_check(
                check_name="kubernetes_kubeconfig_parse",
                passed=False,
                message=f"Failed to read kubeconfig at {path}: {exc}",
                level=ValidationLevel.ERROR,
            )
            return None

    def _resolve_context(
        self, kubeconfig: dict[str, Any], context_override: str | None
    ) -> str | None:
        """Resolve which context to use."""
        if context_override:
            return context_override

        current_context = kubeconfig.get("current-context")
        if not current_context:
            self.report.add_check(
                check_name="kubernetes_kubeconfig_context",
                passed=False,
                message="Kubeconfig has no current-context set",
                level=ValidationLevel.ERROR,
            )
            return None
        return str(current_context)

    def _get_context_entry(
        self, kubeconfig: dict[str, Any], context_name: str
    ) -> dict[str, Any] | None:
        """Find a context entry by name in kubeconfig."""
        contexts = kubeconfig.get("contexts", [])
        for ctx in contexts:
            if ctx.get("name") == context_name:
                return dict(ctx)

        self.report.add_check(
            check_name="kubernetes_kubeconfig_context",
            passed=False,
            message=f"Context '{context_name}' not found in kubeconfig",
            level=ValidationLevel.ERROR,
        )
        return None

    def _get_cluster_info(
        self, kubeconfig: dict[str, Any], cluster_name: str | None
    ) -> dict[str, Any] | None:
        """Find cluster info by name in kubeconfig."""
        if not cluster_name:
            self.report.add_check(
                check_name="kubernetes_kubeconfig_cluster",
                passed=False,
                message="Context has no cluster reference",
                level=ValidationLevel.ERROR,
            )
            return None

        clusters = kubeconfig.get("clusters", [])
        for cluster in clusters:
            if cluster.get("name") == cluster_name:
                cluster_data = cluster.get("cluster", {})
                return dict(cluster_data) if isinstance(cluster_data, dict) else {}

        self.report.add_check(
            check_name="kubernetes_kubeconfig_cluster",
            passed=False,
            message=f"Cluster '{cluster_name}' not found in kubeconfig",
            level=ValidationLevel.ERROR,
        )
        return None

    def _extract_auth_headers(
        self, kubeconfig: dict[str, Any], user_name: str | None
    ) -> dict[str, str]:
        """Extract authentication headers from kubeconfig user entry."""
        headers: dict[str, str] = {}
        if not user_name:
            return headers

        users = kubeconfig.get("users", [])
        for user_entry in users:
            if user_entry.get("name") != user_name:
                continue
            user_info = user_entry.get("user", {})

            # Check for exec-based auth (unsupported)
            if user_info.get("exec"):
                self.report.add_check(
                    check_name="kubernetes_kubeconfig_auth",
                    passed=True,
                    message=(
                        f"User '{user_name}' uses exec-based auth "
                        "(not supported for API validation)"
                    ),
                    level=ValidationLevel.WARNING,
                )
                return headers

            # Try bearer token
            token = user_info.get("token")
            if token:
                headers["Authorization"] = f"Bearer {token}"
                return headers

            # Try token file
            token_file = user_info.get("tokenFile")
            if token_file:
                try:
                    token = Path(token_file).read_text(encoding="utf-8").strip()
                    headers["Authorization"] = f"Bearer {token}"
                except OSError:
                    self.report.add_check(
                        check_name="kubernetes_kubeconfig_auth",
                        passed=False,
                        message=f"Cannot read token file: {token_file}",
                        level=ValidationLevel.WARNING,
                    )
                return headers

            # Try client certificate
            if self._resolve_client_cert(user_info, user_name):
                return headers

            # No supported auth found
            self.report.add_check(
                check_name="kubernetes_kubeconfig_auth",
                passed=True,
                message=(
                    f"User '{user_name}' has no supported auth method "
                    "(token, tokenFile or client certificate expected)"
                ),
                level=ValidationLevel.WARNING,
            )
            return headers

        return headers

    def _read_credential(
        self, user_info: dict[str, Any], data_key: str, path_key: str, name: str
    ) -> str | None:
        """Resolve a certificate or key from inline base64 data or a file path.

        Args:
            user_info: The kubeconfig user entry.
            data_key: Key holding base64 data (e.g. ``client-certificate-data``).
            path_key: Key holding a file path (e.g. ``client-certificate``).
            name: File name used when the data is written to the temp directory.

        Returns:
            Path of a readable file, or None when absent or unusable.
        """
        data = user_info.get(data_key)
        if data:
            try:
                return self._write_secret_file(name, base64.b64decode(str(data), validate=True))
            except (binascii.Error, ValueError, OSError):
                return None
        path = user_info.get(path_key)
        if path and Path(str(path)).expanduser().is_file():
            return str(Path(str(path)).expanduser())
        return None

    def _resolve_client_cert(self, user_info: dict[str, Any], user_name: str) -> bool:
        """Resolve client-certificate auth for a user entry.

        Args:
            user_info: The kubeconfig user entry.
            user_name: User name, used in messages (never the certificate contents).

        Returns:
            True when a usable certificate and key were found.
        """
        has_any = any(
            user_info.get(k)
            for k in (
                "client-certificate-data",
                "client-certificate",
                "client-key-data",
                "client-key",
            )
        )
        if not has_any:
            return False
        cert = self._read_credential(
            user_info, "client-certificate-data", "client-certificate", "client.crt"
        )
        key = self._read_credential(user_info, "client-key-data", "client-key", "client.key")
        if cert and key:
            self._client_cert = (cert, key)
            return True
        self.report.add_check(
            check_name="kubernetes_kubeconfig_auth",
            passed=False,
            message=(
                f"User '{user_name}' has an unusable client certificate or key "
                "(missing, unreadable or not valid base64)"
            ),
            level=ValidationLevel.WARNING,
        )
        return True

    def _resolve_ca_bundle(self, cluster_info: dict[str, Any]) -> str | None:
        """Resolve the CA bundle file for verifying the server certificate.

        Args:
            cluster_info: The kubeconfig cluster entry.

        Returns:
            Path of a CA file (inline data is written to the temp directory), or None.
        """
        ca_path = cluster_info.get("certificate-authority")
        if ca_path and Path(ca_path).expanduser().exists():
            return str(Path(ca_path).expanduser())
        ca_data = cluster_info.get("certificate-authority-data")
        if ca_data:
            try:
                return self._write_secret_file(
                    "ca.crt", base64.b64decode(str(ca_data), validate=True)
                )
            except (binascii.Error, ValueError, OSError):
                return None
        return None

    def _resolve_ca_cert(self, cluster_info: dict[str, Any]) -> bool:
        """Resolve CA certificate configuration.

        Returns:
            True to verify SSL (against the CA bundle or the system store), False to
            skip verification.
        """
        if cluster_info.get("insecure-skip-tls-verify"):
            return False

        # No CA configured - skip verification
        return self._resolve_ca_bundle(cluster_info) is not None

    def _test_connectivity(self) -> None:
        """Test API connectivity using the extracted connection info."""
        info = self._connection_info
        if not info.server_url:
            return

        if not info.headers.get("Authorization") and not info.client_cert:
            self.report.add_check(
                check_name="kubernetes_connectivity",
                passed=True,
                message="No auth credentials available; skipping API connectivity test",
                level=ValidationLevel.INFO,
            )
            return

        url = f"{info.server_url}/api"
        connected = self.api_validator.check_api_connectivity(
            url=url,
            headers=info.headers,
            verify_ssl=info.ca_bundle or info.verify_ssl,
            cert=info.client_cert,
        )

        if connected:
            self._connection_info.connected = True
            # Try to get version info
            version_data = self.api_validator.fetch_json(
                url=f"{info.server_url}/version",
                headers=info.headers,
                verify_ssl=info.ca_bundle or info.verify_ssl,
                timeout=10,
                check_name="kubernetes_version",
                error_level=ValidationLevel.INFO,
                optional=True,
                cert=info.client_cert,
            )
            if version_data:
                version = version_data.get("gitVersion", "unknown")
                self.api_validator.add_success(
                    check_name="kubernetes_version",
                    message=f"Kubernetes version: {version}",
                )
        else:
            self.report.add_check(
                check_name="kubernetes_connectivity",
                passed=True,
                message="Could not connect to Kubernetes API; API checks will be skipped",
                level=ValidationLevel.WARNING,
            )
