"""Interface-assignments controller installer + PHP source bundle (#720, ADR-0014).

Re-exports the public surface of ``installer.py``. The PHP source
``AssignSettingsController.php`` lives next to ``installer.py`` and
is shipped via SCP to the target OPNsense box at
``/usr/local/opnsense/mvc/app/controllers/OPNsense/Interfaces/Api/``.

Provenance and security review notes are in ``PROVENANCE.md``.
"""

from __future__ import annotations

from .installer import (
    DEFAULT_INSTALL_PATH,
    SshTarget,
    compute_local_checksum,
    ensure_installed,
    install_controller,
    load_ssh_target,
    local_controller_path,
    verify_installed_checksum,
)

__all__ = [
    "DEFAULT_INSTALL_PATH",
    "SshTarget",
    "compute_local_checksum",
    "ensure_installed",
    "install_controller",
    "load_ssh_target",
    "local_controller_path",
    "verify_installed_checksum",
]
