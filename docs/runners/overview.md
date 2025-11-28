# Runner Execution Overview

InfraFoundry supports multiple "runners" (Terraform, Ansible, PyInfra) that automatically execute based on your resource configurations. Understanding their execution order is crucial for designing robust infrastructure workflows.

## Fixed Execution Order

Runners are always executed in a fixed, predefined sequence to ensure dependencies are met:

1.  **Terraform Runner**: Always runs first. Its primary role is to **provision** the underlying infrastructure (e.g., creating virtual machines, networks, storage). This ensures that the target resources exist and are accessible before any configuration management tools attempt to connect to them.
2.  **Ansible Runner**: Runs second. Once Terraform has provisioned the resources, Ansible can begin its work. Its role is typically for **system-level configuration** and initial setup (e.g., installing operating system packages, configuring users, setting up services).
3.  **PyInfra Runner**: Runs third. Following Ansible, PyInfra can execute its operations. This order allows PyInfra to handle tasks like **application deployment**, further fine-tuning of services, or any other Python-based configuration that might rely on initial setup performed by Ansible.

**Order:** `Terraform` &rarr; `Ansible` &rarr; `PyInfra`

This default order reflects a logical progression from infrastructure provisioning to system configuration and finally to application-level deployment.

## Customizing Execution Order

While the default order covers most use cases, you can customize the execution order by setting `runner_priorities` in your environment's `settings.yaml`.

Runners are executed in ascending order of priority (lowest number first).

**Default Priorities:**
*   Terraform: 0
*   Ansible: 50
*   PyInfra: 50

If two runners have the same priority, they execute in their registration order (Ansible before PyInfra).

### Example: Running PyInfra before Ansible

To run PyInfra before Ansible (e.g., to bootstrap Python required by Ansible), give it a lower priority:

```yaml
# envs/dev/settings.yaml
name: dev

runner_priorities:
  pyinfra: 40
  ansible: 60
```

**New Order:** `Terraform (0)` &rarr; `PyInfra (40)` &rarr; `Ansible (60)`

## Interaction with Resource Definitions

When you define a resource (e.g., a VM) in your YAML, InfraFoundry automatically determines which runners are applicable based on the keys present in your resource's configuration:
*   Presence of VM/network definition triggers Terraform.
*   Presence of `ansible_roles`, `ansible_tasks`, `ansible_vars` triggers Ansible.
*   Presence of `pyinfra_ops`, `pyinfra_deploy_funcs` triggers PyInfra.

You can mix and match configuration options for different runners within the same resource definition. InfraFoundry will ensure that the applicable runners execute in the correct fixed order.

For example, a single VM definition can specify both Ansible roles for base system setup and PyInfra functions for application deployment. InfraFoundry will ensure Terraform provisions the VM, then Ansible configures it, and finally PyInfra deploys the application.

## Best Practices for Mixed Runner Usage

*   **Layer Responsibilities**: Design your configuration so each runner handles its primary responsibility. Terraform for provisioning, Ansible for system setup, PyInfra for application logic.
*   **Idempotency**: Ensure all your runner configurations (Ansible playbooks, PyInfra scripts) are idempotent, meaning they can be run multiple times without causing unintended side effects.
*   **Debugging**: If issues arise, inspect the generated files in `generated/{env}/{runner_name}/{provider}/` for each runner, as well as the logs from their respective executions.
