"""Ansible playbook execution (legacy compatibility).

This module provides backward compatibility. New code should import from:
    from infrafoundry.core.runners import AnsibleRunner
"""

# Import from new location for backward compatibility
from infrafoundry.core.runners.ansible_runner import AnsibleRunner  # noqa: F401

__all__ = ["AnsibleRunner"]
