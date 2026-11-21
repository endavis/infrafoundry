"""Bitwarden / Vaultwarden secret backend, driven through the ``bw`` CLI.

Resolves ``secret://bitwarden/<item>/<field>`` read-only. ``<item>`` is an item ID (UUID) or an
exact item name (it may itself contain ``/``); ``<field>`` is ``username``, ``password``,
``notes``, ``uri``, ``totp`` or the name of a custom field. The split is on the last ``/``.

Design (ADR-0034):

* Each process keeps its own ``bw`` state in a private 0700 directory passed as
  ``BITWARDENCLI_APPDATA_DIR``. The operator's own ``bw`` login, server and ``BW_SESSION`` are
  never read, repointed or logged out. Inherited ``BW_*`` variables are stripped from every
  subprocess environment; each command receives only the variables it needs.
* One session per process (module-level registry). Backends built by different call sites share
  it; ``close_bitwarden_sessions()`` (also registered with ``atexit``) locks, logs out and removes
  the directory.
* Credentials reach ``bw`` only through the subprocess environment, never argv. They are
  ``secret://env/...`` or ``secret://env_secrets/...`` URIs, so they cannot point into the vault.
* Exceptions carry at most the ``bw`` subcommand name, the item or field reference and a reason.
  Never stderr (a failed fetch makes ``bw`` print a stack trace), values or credentials.

``bw`` behaviour measured against an installed ``bw`` 2026.10.1 (offline):

* ``BITWARDENCLI_APPDATA_DIR=<dir>`` makes ``bw`` create and use ``<dir>/data.json``.
* ``bw status --nointeraction`` exits 0 and prints JSON, e.g.
  ``{"serverUrl":null,"lastSync":null,"status":"unauthenticated"}`` on a fresh directory.
* ``bw config server <url> --nointeraction`` exits 0; ``bw status`` then shows that ``serverUrl``.
* With an unreachable server every command prints a multi-line FetchError stack trace to stderr.
* ``bw list items --nointeraction`` while unauthenticated exits 1 (``You are not logged in.``).
* Flags that exist: ``unlock --passwordenv``, ``unlock --passwordfile``, ``unlock --raw``,
  ``login --apikey``, ``list --search``, ``--organizationid``, ``--collectionid``.
* ``bw list items`` with both ``--organizationid`` and ``--collectionid`` (with or without
  ``--search``) filters by organization only; ``--collectionid`` alone filters by collection.
  The backend therefore re-applies both scope filters to every listed item.
* A live test against a self-hosted Vaultwarden confirmed ``login --apikey`` with
  ``BW_CLIENTID``/``BW_CLIENTSECRET``, ``unlock --passwordenv --raw``, ``sync``, the item JSON
  shape for logins and custom fields, ``list collections``, and exact-name filtering.

Everything else relied on below is from bw documentation, unverified against an installed ``bw``
(the live test confirms or corrects it): ``login --apikey`` reading ``BW_CLIENTID`` and
``BW_CLIENTSECRET``; ``unlock --raw`` printing only the session key; ``bw sync``, ``bw lock``,
``bw logout``; ``--search`` being fuzzy (so names are re-filtered for an exact match); the item
JSON shape (``id``, ``name``, ``organizationId``, ``collectionIds``, ``login``, ``notes``,
``fields``); ``bw get totp <id>`` printing the current code; ``bw list organizations`` and
``bw list collections`` returning ``id``/``name`` arrays; ``Not found.`` on stderr for a missing
item.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import subprocess  # nosec B404  # required for running the bitwarden CLI
import tempfile
import threading
from typing import TYPE_CHECKING, Any

from infrafoundry.secrets.protocol import SecretBackendError, SecretNotFoundError

if TYPE_CHECKING:
    from infrafoundry.secrets.plugin_type import SecretBackendMetadata

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_BW_TIMEOUT_SECONDS = 120
_ALLOWED_CREDENTIAL_BACKENDS = ("env", "env_secrets")
_CREDENTIAL_SETTINGS = ("client_id", "client_secret", "master_password")
# Each setting defaults to the env var the bw CLI itself reads (BW_CLIENTID, ...).
_DEFAULT_CREDENTIAL_URIS = dict(
    zip(
        _CREDENTIAL_SETTINGS,
        (f"secret://env/bw_{name}" for name in ("clientid", "clientsecret", "password")),
        strict=True,
    )
)


class _BwError(Exception):
    """A ``bw`` call failed. Carries only the subcommand, exit code and a not-found flag."""

    def __init__(self, subcommand: str, code: int | None, not_found: bool) -> None:
        super().__init__(f"bw {subcommand} failed")
        self.subcommand = subcommand
        self.code = code
        self.not_found = not_found


def _clean_env() -> dict[str, str]:
    """Return ``os.environ`` without any inherited ``BW_*`` or app-data variables."""
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("BW_") and k != "BITWARDENCLI_APPDATA_DIR"
    }


class _BitwardenSession:
    """One logged-in, unlocked ``bw`` state in a private directory, shared per process."""

    def __init__(
        self,
        server: str,
        organization: str | None,
        collection: str | None,
        credentials: dict[str, str],
    ) -> None:
        self.server = server.rstrip("/")
        self.organization = organization
        self.collection = collection
        self._credentials = credentials
        self.app_dir: str | None = None
        self.session_key: str | None = None
        self.ready = False
        self._organization_id: str | None = None
        self._collection_id: str | None = None
        self.lock = threading.RLock()

    # -- process plumbing -------------------------------------------------------------------

    def run(self, args: list[str], extra_env: dict[str, str] | None = None) -> str:
        """Run ``bw <args> --nointeraction`` against the private state, returning stdout.

        Raises:
            SecretBackendError: ``bw`` is missing, timed out, or could not be started.
            _BwError: ``bw`` exited non-zero.
        """
        bw_path = shutil.which("bw")
        if bw_path is None:
            raise SecretBackendError("Bitwarden CLI (bw) not found on PATH")
        subcommand = args[0] if args else ""
        env = _clean_env()
        if self.app_dir is not None:
            env["BITWARDENCLI_APPDATA_DIR"] = self.app_dir
        if self.session_key and "BW_SESSION" not in (extra_env or {}):
            env["BW_SESSION"] = self.session_key
        env.update(extra_env or {})
        try:
            result = subprocess.run(  # fixed bw argv, no shell
                [bw_path, *args, "--nointeraction"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=_BW_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise SecretBackendError(f"bw {subcommand} timed out") from exc
        except OSError as exc:
            raise SecretBackendError(f"bw {subcommand} could not be started") from exc
        if result.returncode != 0:
            stderr = result.stderr or ""
            # stderr is never logged: it can carry item values the backend cannot know to redact.
            logger.debug("bw %s exited %s", subcommand, result.returncode)
            lines = [ln.strip().lower().rstrip(".") for ln in stderr.splitlines()]
            raise _BwError(subcommand, result.returncode, "not found" in lines)
        return result.stdout

    def run_json(self, args: list[str]) -> Any:
        """Run ``bw`` and parse stdout as JSON."""
        out = self.run(args)
        try:
            return json.loads(out)
        except json.JSONDecodeError as exc:
            raise SecretBackendError(f"bw {args[0]} returned output that is not JSON") from exc

    # -- lifecycle --------------------------------------------------------------------------

    def ensure_ready(self) -> None:
        """Configure the server, log in, unlock and sync, once."""
        with self.lock:
            if self.ready:
                return
            try:
                self._setup()
            except _BwError as exc:
                self.teardown()
                raise SecretBackendError(f"bw {exc.subcommand} failed (exit {exc.code})") from None
            except Exception:
                self.teardown()
                raise
            self.ready = True

    def _setup(self) -> None:
        app_dir = tempfile.mkdtemp(prefix="infrafoundry-bw-")
        os.chmod(app_dir, 0o700)
        if stat.S_IMODE(os.stat(app_dir).st_mode) != 0o700:
            raise SecretBackendError("bw state directory is not private (0700)")
        self.app_dir = app_dir

        self.run(["config", "server", self.server])
        status = self.run_json(["status"])
        if not isinstance(status, dict):
            raise SecretBackendError("bw status returned an unexpected shape")
        reported = str(status.get("serverUrl") or "").rstrip("/")
        if reported != self.server:
            raise SecretBackendError("bw did not apply the configured server URL")
        state = status.get("status")

        if state == "unauthenticated":
            self.run(
                ["login", "--apikey"],
                {
                    "BW_CLIENTID": self._credentials["client_id"],
                    "BW_CLIENTSECRET": self._credentials["client_secret"],
                },
            )
            state = "locked"
        if state != "unlocked":
            key = self.run(
                ["unlock", "--passwordenv", "BW_PASSWORD", "--raw"],
                {"BW_PASSWORD": self._credentials["master_password"]},
            ).strip()
            if not key:
                raise SecretBackendError("bw unlock returned no session key")
            self.session_key = key
        self.run(["sync"])

    def teardown(self) -> None:
        """Lock, log out and remove the private directory. Never raises."""
        with self.lock:
            if self.app_dir is None:
                return
            for sub in ("lock", "logout"):
                try:
                    self.run([sub])
                except (_BwError, SecretBackendError) as exc:
                    logger.debug("bw %s during teardown failed: %s", sub, type(exc).__name__)
            shutil.rmtree(self.app_dir, ignore_errors=True)
            self.app_dir = None
            self.session_key = None
            self.ready = False

    # -- scope ------------------------------------------------------------------------------

    def _resolve_named(self, label: str, value: str, args: list[str]) -> str:
        if _UUID_RE.match(value):
            return value
        try:
            rows = self.run_json(args)
        except _BwError as exc:
            raise SecretBackendError(f"bw {exc.subcommand} failed (exit {exc.code})") from None
        matches = [
            r["id"]
            for r in (rows if isinstance(rows, list) else [])
            if isinstance(r, dict) and r.get("name") == value and r.get("id")
        ]
        if len(matches) != 1:
            raise SecretBackendError(
                f"bitwarden {label} '{value}' matched {len(matches)} entries, expected exactly 1"
            )
        return str(matches[0])

    def scope_ids(self) -> tuple[str | None, str | None]:
        """Return the (organization id, collection id) the backend is scoped to."""
        if self.organization and self._organization_id is None:
            self._organization_id = self._resolve_named(
                "organization", self.organization, ["list", "organizations"]
            )
        if self.collection and self._collection_id is None:
            args = ["list", "collections"]
            if self._organization_id:
                args += ["--organizationid", self._organization_id]
            self._collection_id = self._resolve_named("collection", self.collection, args)
        return self._organization_id, self._collection_id


_SESSIONS: dict[tuple[str, str | None, str | None, str], _BitwardenSession] = {}
_REGISTRY_LOCK = threading.RLock()
_ATEXIT_REGISTERED = False


def close_bitwarden_sessions() -> None:
    """Lock, log out and clean up every ``bw`` session this process opened."""
    with _REGISTRY_LOCK:
        sessions = list(_SESSIONS.values())
        _SESSIONS.clear()
    for session in sessions:
        session.teardown()


def _get_session(
    key: tuple[str, str | None, str | None, str], credentials: dict[str, str]
) -> _BitwardenSession:
    global _ATEXIT_REGISTERED
    with _REGISTRY_LOCK:
        session = _SESSIONS.get(key)
        if session is None:
            session = _BitwardenSession(key[0], key[1], key[2], credentials)
            _SESSIONS[key] = session
        if not _ATEXIT_REGISTERED:
            atexit.register(close_bitwarden_sessions)
            _ATEXIT_REGISTERED = True
    try:
        session.ensure_ready()
    except Exception:
        with _REGISTRY_LOCK:
            if _SESSIONS.get(key) is session:
                del _SESSIONS[key]
        raise
    return session


class BitwardenSecretBackend:
    """Read-only secret backend over the ``bw`` CLI.

    Args:
        config: Keys ``server`` (https URL), optional ``organization`` and ``collection``
            (UUID or exact name), ``client_id`` / ``client_secret`` / ``master_password``
            (``secret://env/...`` or ``secret://env_secrets/...`` URIs) and ``env_secrets``
            (the decrypted secrets dict backing ``secret://env_secrets/...``).

    Raises:
        SecretBackendError: On a bad config or an unresolvable credential.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Validate the config and resolve the bootstrap credentials (no ``bw`` call)."""
        server = config.get("server")
        if not isinstance(server, str) or not server.startswith("https://"):
            raise SecretBackendError("bitwarden backend requires an https:// 'server'")
        self._server = server
        self._organization: str | None = config.get("organization") or None
        self._collection: str | None = config.get("collection") or None
        self._credentials = self._resolve_credentials(config)
        self._key = (
            server.rstrip("/"),
            self._organization,
            self._collection,
            hashlib.sha256(self._credentials["client_id"].encode()).hexdigest(),
        )

    @staticmethod
    def _resolve_credentials(config: dict[str, Any]) -> dict[str, str]:
        from infrafoundry.secrets.resolver import SecretResolutionError, SecretResolver

        resolver = SecretResolver()
        resolver.configure_backend("env", {"prefix": ""})
        resolver.configure_backend("env_secrets", {"secrets": config.get("env_secrets") or {}})
        out: dict[str, str] = {}
        try:
            for setting in _CREDENTIAL_SETTINGS:
                uri = config.get(setting) or _DEFAULT_CREDENTIAL_URIS[setting]
                try:
                    backend_name, _ = resolver.parse_secret_uri(str(uri))
                except SecretResolutionError:
                    raise SecretBackendError(
                        f"bitwarden '{setting}' must be a secret:// URI"
                    ) from None
                if backend_name not in _ALLOWED_CREDENTIAL_BACKENDS:
                    raise SecretBackendError(
                        f"bitwarden '{setting}' must use the env or env_secrets backend"
                    )
                try:
                    value = resolver.resolve(str(uri))
                except SecretResolutionError:
                    raise SecretBackendError(
                        f"bitwarden '{setting}' could not be resolved from {uri}"
                    ) from None
                if not value:
                    raise SecretBackendError(f"bitwarden '{setting}' resolved to an empty value")
                out[setting] = value
        finally:
            resolver.close()
        return out

    def _session(self) -> _BitwardenSession:
        return _get_session(self._key, self._credentials)

    # -- lookup -----------------------------------------------------------------------------

    def _find_item(self, session: _BitwardenSession, name: str) -> dict[str, Any]:
        org_id, col_id = session.scope_ids()
        if _UUID_RE.match(name):
            try:
                item = session.run_json(["get", "item", name])
            except _BwError as exc:
                if exc.not_found:
                    raise SecretNotFoundError(f"Bitwarden item '{name}' not found") from None
                raise SecretBackendError(f"bw get failed (exit {exc.code})") from None
            if not isinstance(item, dict):
                raise SecretBackendError("bw get returned an unexpected shape")
            if org_id and item.get("organizationId") != org_id:
                raise SecretNotFoundError(f"Bitwarden item '{name}' not found in scope")
            if col_id and col_id not in (item.get("collectionIds") or []):
                raise SecretNotFoundError(f"Bitwarden item '{name}' not found in scope")
            return item
        items = self._list_items(session, name)
        matches = [i for i in items if i.get("name") == name]
        if not matches:
            raise SecretNotFoundError(f"Bitwarden item '{name}' not found")
        if len(matches) > 1:
            raise SecretBackendError(
                f"Bitwarden item '{name}' is ambiguous ({len(matches)} items share that name)"
            )
        return matches[0]

    @staticmethod
    def _list_items(session: _BitwardenSession, search: str | None) -> list[dict[str, Any]]:
        org_id, col_id = session.scope_ids()
        args = ["list", "items"]
        if search is not None:
            args += ["--search", search]
        if org_id:
            args += ["--organizationid", org_id]
        if col_id:
            args += ["--collectionid", col_id]
        try:
            rows = session.run_json(args)
        except _BwError as exc:
            raise SecretBackendError(f"bw list failed (exit {exc.code})") from None
        if not isinstance(rows, list):
            raise SecretBackendError("bw list returned an unexpected shape")
        # bw ignores --collectionid when --organizationid is also given, so the scope is
        # re-applied here rather than trusted to the flags.
        return [
            r
            for r in rows
            if isinstance(r, dict)
            and (not org_id or r.get("organizationId") == org_id)
            and (not col_id or col_id in (r.get("collectionIds") or []))
        ]

    def get_secret(self, key: str) -> str:
        """Return one field of one vault item.

        Args:
            key: ``<item>/<field>``; split on the last ``/``.

        Raises:
            SecretNotFoundError: Item, field or value is missing.
            SecretBackendError: Ambiguous name, bw failure, or a bad key.
        """
        if "/" not in key:
            raise SecretBackendError(
                "bitwarden secret key must be <item>/<field> (e.g. secret://bitwarden/name/password)"
            )
        name, field = key.rsplit("/", 1)
        if not name or not field:
            raise SecretBackendError("bitwarden secret key must be <item>/<field>")
        session = self._session()
        try:
            item = self._find_item(session, name)
            value = self._extract(session, item, name, field)
        except _BwError as exc:
            raise SecretBackendError(f"bw {exc.subcommand} failed (exit {exc.code})") from None
        if value is None or value == "":
            raise SecretNotFoundError(f"Bitwarden item '{name}' has no value for field '{field}'")
        return value

    @staticmethod
    def _extract(
        session: _BitwardenSession, item: dict[str, Any], name: str, field: str
    ) -> str | None:
        login = item.get("login") or {}
        if field == "username":
            return _as_str(login.get("username"))
        if field == "password":
            return _as_str(login.get("password"))
        if field == "notes":
            return _as_str(item.get("notes"))
        if field == "uri":
            uris = login.get("uris") or []
            return _as_str(uris[0].get("uri")) if uris and isinstance(uris[0], dict) else None
        if field == "totp":
            try:
                return session.run(["get", "totp", str(item.get("id"))]).strip()
            except _BwError as exc:
                raise SecretNotFoundError(
                    f"Bitwarden item '{name}' has no totp (bw get failed, exit {exc.code})"
                ) from None
        matches = [
            f for f in (item.get("fields") or []) if isinstance(f, dict) and f.get("name") == field
        ]
        if not matches:
            raise SecretNotFoundError(f"Bitwarden item '{name}' has no field '{field}'")
        if len(matches) > 1:
            raise SecretBackendError(
                f"Bitwarden item '{name}' has {len(matches)} custom fields named '{field}'"
            )
        return _as_str(matches[0].get("value"))

    def list_secrets(self, prefix: str = "") -> list[str]:
        """List exact item names in scope (never values), optionally by name prefix."""
        session = self._session()
        names = sorted({str(i["name"]) for i in self._list_items(session, None) if i.get("name")})
        return [n for n in names if n.startswith(prefix)] if prefix else names

    def health_check(self) -> bool:
        """Return True when a session can be established."""
        try:
            self._session()
        except SecretBackendError:
            return False
        return True

    def close(self) -> None:
        """No-op: the session is shared per process and closed at exit."""


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value)


def register() -> SecretBackendMetadata:
    """Register the bitwarden secret backend.

    Returns:
        ``SecretBackendMetadata`` for the bitwarden backend.
    """
    from infrafoundry.secrets.plugin_type import SecretBackendMetadata

    return SecretBackendMetadata(
        name="bitwarden",
        version="1.0.0",
        description="Read secrets from a Bitwarden or Vaultwarden vault through the bw CLI",
        backend_class=BitwardenSecretBackend,
        read_only=True,
        author="InfraFoundry Team",
        url="https://github.com/infrascloudy/infrafoundry",
    )
