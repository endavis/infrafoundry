"""OPNsense provider extensions sub-package (ADR-0014 amendment, #720).

Houses out-of-band controllers and helper artifacts that have no Python
parallel inside the standard ``services/`` + ``components/`` layering. The
first inhabitant is the gist-derived ``interface_assignments`` PHP
controller plus its idempotent installer; subsequent gist-controller
components (port_forward → #725) follow the same pattern.
"""

from __future__ import annotations
