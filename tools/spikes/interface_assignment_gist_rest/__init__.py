"""Gist-based REST spike for OPNsense interface_assignments — informs ADR-0014 (#715).

See ``interface_assignment_gist_rest.py`` for the spike entry point and
``AssignSettingsController.php`` for the patched + extended community
controller (originally from
https://gist.github.com/szymczag/df152a82e86aff67b984ed3786b027ba).

The findings document at
``docs/development/opnsense-spike-interface-assignment-gist-findings.md``
captures empirical results from the live run.
"""
