"""OpenTofu runner implementation.

OpenTofu is a CLI-compatible fork of Terraform. This runner extends
TerraformRunner, overriding only the tool_name property to resolve
the ``tofu`` binary instead of ``terraform``.
"""

from typing import override

from infrafoundry.core.runners.terraform_runner import TerraformRunner


class OpenTofuRunner(TerraformRunner):
    """Handles OpenTofu command execution and state management.

    OpenTofu uses the same CLI interface as Terraform (init, plan, apply,
    destroy, show, validate, version) so this runner inherits all behaviour
    and only changes the binary name.
    """

    @property
    @override
    def tool_name(self) -> str:
        """Return the name of the tool binary."""
        return "tofu"
