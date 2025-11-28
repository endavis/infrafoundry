"""Example PyInfra deploy functions for InfraFoundry."""

from pyinfra.operations import apt, server


def setup_webserver():
    """Install and configure Nginx using PyInfra."""

    apt.packages(
        name="Install Nginx",
        packages=["nginx"],
        update=True,
        _sudo=True,
    )

    server.service(
        name="Ensure Nginx is running",
        service="nginx",
        running=True,
        enabled=True,
        _sudo=True,
    )

    # Example of conditional logic in Python
    # if host.fact.linux_distribution['name'] == 'Ubuntu':
    #     ...


def setup_monitoring():
    """Install monitoring agent."""
    apt.packages(
        name="Install htop",
        packages=["htop"],
        update=True,
        _sudo=True,
    )
