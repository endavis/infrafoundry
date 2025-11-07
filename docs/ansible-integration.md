# Ansible Integration Guide

InfraFoundry integrates Ansible for post-deployment configuration management. This guide explains how to use Ansible roles and tasks with your infrastructure resources.

## Overview

After InfraFoundry provisions infrastructure with Terraform, it can automatically configure VMs and services using Ansible. This enables a complete infrastructure-as-code workflow:

1. **Terraform**: Provisions infrastructure (VMs, networks, storage)
2. **Ansible**: Configures software, deploys applications, manages services

## Configuration Structure

### Resource-Level Configuration

Define Ansible roles and tasks directly in your resource YAML files:

```yaml
vms:
  - name: web-server-01
    # ... VM configuration ...

    # Reusable roles to apply
    ansible_roles:
      - common
      - webserver
      - docker

    # Custom tasks for this specific VM
    ansible_tasks:
      - name: Deploy custom configuration
        module: template
        params:
          src: config.j2
          dest: /etc/myapp/config.yml

    # Variables passed to roles and tasks
    ansible_vars:
      webserver_port: 8080
      enable_ssl: true
```

## Using Ansible Roles

### Standard Roles

Roles are reusable units of Ansible configuration. Place them in your config repository:

```
my-infra-config/
├── roles/
│   ├── common/
│   │   └── tasks/
│   │       └── main.yml
│   ├── webserver/
│   │   ├── tasks/
│   │   ├── templates/
│   │   └── handlers/
│   └── docker/
│       └── tasks/
│           └── main.yml
└── envs/
    └── dev/
        └── proxmox/
            └── vms.yaml
```

### Role Application

Specify roles in the `ansible_roles` list:

```yaml
vms:
  - name: app-server-01
    # ... VM config ...
    ansible_roles:
      - common            # Applied first
      - webserver         # Applied second
      - monitoring-agent  # Applied third
```

Roles are applied in the order listed. Use role dependencies for complex setups:

```yaml
# roles/webapp/meta/main.yml
dependencies:
  - role: common
  - role: webserver
```

### Galaxy Roles

Use roles from Ansible Galaxy:

```yaml
# requirements.yml in your config repo
roles:
  - name: geerlingguy.docker
    version: 6.1.0
  - name: geerlingguy.nginx
    version: 3.1.4
```

Install with:

```bash
ansible-galaxy install -r requirements.yml -p roles/
```

Reference in configurations:

```yaml
ansible_roles:
  - geerlingguy.docker
  - geerlingguy.nginx
```

## Custom Tasks

### Inline Tasks

Define tasks directly in resource configurations for VM-specific actions:

```yaml
vms:
  - name: db-server-01
    # ... VM config ...
    ansible_tasks:
      - name: Create application database
        module: postgresql_db
        params:
          name: myapp_db
          state: present

      - name: Create database user
        module: postgresql_user
        params:
          name: myapp_user
          password: "{{ vault_db_password }}"
          priv: "myapp_db:ALL"

      - name: Configure connection limits
        module: lineinfile
        params:
          path: /etc/postgresql/14/main/postgresql.conf
          regexp: "^max_connections"
          line: "max_connections = 200"
        notify: restart postgresql
```

### Task Structure

Each task has:
- `name`: Description of the task
- `module`: Ansible module to use
- `params`: Module parameters as key-value pairs
- `notify` (optional): Handler to trigger on change

Common modules:
- `apt`, `yum`: Package management
- `copy`, `template`: File management
- `lineinfile`, `blockinfile`: File editing
- `service`, `systemd`: Service management
- `command`, `shell`: Execute commands
- `git`: Version control
- `docker_container`: Container management

### Handlers

Handlers are triggered by tasks when changes occur:

```yaml
# In a role's handlers/main.yml
handlers:
  - name: restart nginx
    systemd:
      name: nginx
      state: restarted

  - name: reload nginx
    systemd:
      name: nginx
      state: reloaded
```

Reference in tasks:

```yaml
ansible_tasks:
  - name: Update nginx config
    module: template
    params:
      src: nginx.conf.j2
      dest: /etc/nginx/nginx.conf
    notify: reload nginx
```

## Variables

### Passing Variables to Roles

Use `ansible_vars` to pass variables:

```yaml
vms:
  - name: web-server-01
    # ... VM config ...
    ansible_roles:
      - webserver
    ansible_vars:
      webserver_port: 8080
      webserver_worker_processes: 4
      webserver_ssl: true
      webserver_domains:
        - example.com
        - www.example.com
```

Variables are available in role templates and tasks:

```jinja2
# roles/webserver/templates/nginx.conf.j2
worker_processes {{ webserver_worker_processes }};

server {
    listen {{ webserver_port }};
    {% for domain in webserver_domains %}
    server_name {{ domain }};
    {% endfor %}
}
```

### Variable Precedence

Ansible variable precedence (lowest to highest):
1. Role defaults (`roles/*/defaults/main.yml`)
2. Inventory variables
3. Playbook variables
4. `ansible_vars` from resource config (highest)

### Secret Variables

Use SOPS-encrypted secrets:

```yaml
# secrets/ansible.yaml (encrypted)
vault_db_password: "super_secret"
vault_api_key: "api_key_here"
```

Reference in tasks:

```yaml
ansible_tasks:
  - name: Create user with password
    module: user
    params:
      name: appuser
      password: "{{ vault_db_password | password_hash('sha512') }}"
```

## Example Configurations

### Web Server with SSL

```yaml
vms:
  - name: web-prod-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 2
    memory: 4096
    ipconfig: ip=192.168.100.10/24,gw=192.168.100.1

    ansible_roles:
      - common
      - webserver
      - certbot
      - monitoring-agent

    ansible_vars:
      webserver_port: 443
      webserver_ssl: true
      certbot_email: admin@example.com
      certbot_domains:
        - example.com
        - www.example.com
```

### Database Server

```yaml
vms:
  - name: db-prod-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 4
    memory: 16384

    ansible_roles:
      - common
      - database
      - backup-agent

    ansible_tasks:
      - name: Create application databases
        module: postgresql_db
        params:
          name: "{{ item }}"
          state: present
        loop:
          - appdb_prod
          - appdb_staging

      - name: Configure backup schedule
        module: cron
        params:
          name: "Database backup"
          minute: "0"
          hour: "2"
          job: "/usr/local/bin/backup-db.sh"

    ansible_vars:
      postgresql_version: 14
      postgresql_max_connections: 300
      postgresql_shared_buffers: "4GB"
```

### Application Server

```yaml
vms:
  - name: app-prod-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 4
    memory: 8192

    ansible_roles:
      - common
      - docker
      - monitoring-agent

    ansible_tasks:
      - name: Deploy application container
        module: docker_container
        params:
          name: myapp
          image: "myorg/myapp:latest"
          state: started
          restart_policy: unless-stopped
          ports:
            - "3000:3000"
          env:
            DATABASE_URL: "postgresql://db-prod-01/appdb_prod"
            API_KEY: "{{ vault_api_key }}"

      - name: Configure log rotation
        module: copy
        params:
          src: logrotate.conf
          dest: /etc/logrotate.d/myapp

    ansible_vars:
      docker_users:
        - ubuntu
        - appuser
```

### Kubernetes Node

```yaml
vms:
  - name: k8s-worker-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 4
    memory: 16384

    ansible_roles:
      - common
      - kubernetes-node
      - cni-calico

    ansible_tasks:
      - name: Label node for workload type
        module: command
        params:
          cmd: "kubectl label node k8s-worker-01 workload=general"

      - name: Taint node for specific workloads
        module: command
        params:
          cmd: "kubectl taint nodes k8s-worker-01 dedicated=compute:NoSchedule"

    ansible_vars:
      kubernetes_version: "1.28"
      kubernetes_pod_network: "10.244.0.0/16"
      kubelet_max_pods: 200
```

## Execution Workflow

### InfraFoundry Execution

When you run `infra apply`:

1. **Generate Phase**:
   - Reads resource configurations
   - Generates Terraform files for infrastructure
   - Generates Ansible inventory from VM definitions
   - Generates Ansible playbooks with roles and tasks

2. **Terraform Phase**:
   - Runs `terraform init`
   - Runs `terraform plan`
   - Runs `terraform apply` (creates infrastructure)
   - Captures outputs (IPs, IDs)

3. **Ansible Phase** (after Terraform succeeds):
   - Waits for VMs to be SSH-accessible
   - Runs `ansible-playbook` with generated inventory
   - Applies roles and tasks to each VM
   - Reports configuration status

### Dry Run Mode

Test configuration without making changes:

```bash
# Generate files and run terraform plan only
infra plan --env dev

# Run Ansible in check mode (no changes)
infra apply --env dev --dry-run
```

Check mode shows what would be changed without applying:

```
TASK [Install Nginx] ****************************
changed: [web-server-01]  # Would install nginx

TASK [Deploy config] ****************************
changed: [web-server-01]  # Would update config file
```

### Manual Execution

Run Ansible playbooks directly:

```bash
cd generated/ansible/proxmox/

# Check mode (dry run)
ansible-playbook -i inventory.yml playbook.yml --check

# Apply configuration
ansible-playbook -i inventory.yml playbook.yml

# Run specific tags
ansible-playbook -i inventory.yml playbook.yml --tags "setup,config"

# Limit to specific hosts
ansible-playbook -i inventory.yml playbook.yml --limit "web-server-01"
```

## Best Practices

### Role Organization

1. **Separation of Concerns**: One role per service/component
2. **Reusability**: Make roles generic with variables
3. **Dependencies**: Use `meta/main.yml` for role dependencies
4. **Testing**: Test roles independently before integration

### Task Design

1. **Idempotency**: Tasks should be safe to run multiple times
   ```yaml
   # Good: Creates only if doesn't exist
   - name: Create directory
     module: file
     params:
       path: /opt/myapp
       state: directory

   # Bad: Fails if directory exists
   - name: Create directory
     module: command
     params:
       cmd: mkdir /opt/myapp
   ```

2. **Descriptive Names**: Clear task descriptions
3. **Error Handling**: Use `failed_when`, `ignore_errors`
4. **Change Detection**: Use handlers for service restarts

### Security

1. **Secrets**: Always encrypt with SOPS
2. **Passwords**: Hash passwords in tasks
   ```yaml
   password: "{{ vault_password | password_hash('sha512') }}"
   ```
3. **File Permissions**: Set explicitly
   ```yaml
   params:
     path: /etc/myapp/config.yml
     mode: '0600'
     owner: myapp
   ```
4. **SSH Keys**: Use ansible_ssh_private_key_file

### Performance

1. **Parallelism**: Ansible runs tasks in parallel across hosts
2. **Tags**: Use tags for selective execution
   ```yaml
   ansible_tasks:
     - name: Install packages
       module: apt
       params: ...
       tags: [packages]
   ```
3. **Gather Facts**: Disable if not needed
   ```yaml
   # In custom playbook
   gather_facts: no
   ```

## Troubleshooting

### Connection Issues

If Ansible can't connect to VMs:

1. **Check SSH access**:
   ```bash
   ssh ubuntu@192.168.100.10
   ```

2. **Verify inventory**:
   ```bash
   ansible-inventory -i generated/ansible/proxmox/inventory.yml --list
   ```

3. **Test connectivity**:
   ```bash
   ansible all -i generated/ansible/proxmox/inventory.yml -m ping
   ```

### Task Failures

If tasks fail:

1. **Run with verbosity**:
   ```bash
   ansible-playbook -i inventory.yml playbook.yml -v   # Verbose
   ansible-playbook -i inventory.yml playbook.yml -vvv # Very verbose
   ```

2. **Check module syntax**:
   ```bash
   ansible-doc <module_name>
   ```

3. **Test task individually**:
   ```bash
   ansible web-server-01 -i inventory.yml -m apt -a "name=nginx state=present"
   ```

### Role Issues

If roles don't work:

1. **Check role paths**:
   ```bash
   ansible-config dump | grep ROLE
   ```

2. **List available roles**:
   ```bash
   ansible-galaxy list
   ```

3. **Verify role structure**:
   ```bash
   tree roles/webserver/
   ```

### Variable Problems

If variables aren't available:

1. **Debug variables**:
   ```yaml
   ansible_tasks:
     - name: Show all variables
       module: debug
       params:
         var: hostvars[inventory_hostname]
   ```

2. **Check precedence**: Higher precedence overrides lower
3. **Verify encryption**: Ensure secrets are decrypted

## Advanced Features

### Conditional Execution

Run tasks based on conditions:

```yaml
ansible_tasks:
  - name: Install Docker (Ubuntu)
    module: apt
    params:
      name: docker.io
    when: ansible_distribution == "Ubuntu"

  - name: Install Docker (CentOS)
    module: yum
    params:
      name: docker
    when: ansible_distribution == "CentOS"
```

### Loops

Iterate over items:

```yaml
ansible_tasks:
  - name: Create multiple users
    module: user
    params:
      name: "{{ item }}"
      state: present
    loop:
      - alice
      - bob
      - charlie
```

### Blocks and Error Handling

Group tasks with error handling:

```yaml
ansible_tasks:
  - name: Database setup block
    block:
      - name: Create database
        module: postgresql_db
        params:
          name: myapp
      - name: Create user
        module: postgresql_user
        params:
          name: myapp_user
    rescue:
      - name: Log error
        module: debug
        params:
          msg: "Database setup failed"
    always:
      - name: Ensure service is running
        module: systemd
        params:
          name: postgresql
          state: started
```

### Templates

Use Jinja2 templates for configuration files:

```yaml
ansible_tasks:
  - name: Deploy application config
    module: template
    params:
      src: app.conf.j2
      dest: /etc/myapp/config.yml
      owner: myapp
      mode: '0644'
```

Template file (`templates/app.conf.j2`):

```jinja2
# Application Configuration
database:
  host: {{ database_host }}
  port: {{ database_port }}
  name: {{ database_name }}

api:
  port: {{ app_port }}
  workers: {{ ansible_processor_vcpus }}

{% if enable_ssl %}
ssl:
  enabled: true
  cert: /etc/ssl/certs/app.crt
  key: /etc/ssl/private/app.key
{% endif %}
```

## Integration with Other Tools

### Terraform Outputs

Use Terraform outputs in Ansible:

```hcl
# Terraform outputs
output "vm_ips" {
  value = {
    for vm in proxmox_vm_qemu.vms :
    vm.name => vm.default_ipv4_address
  }
}
```

Reference in Ansible:

```yaml
ansible_vars:
  database_host: "{{ terraform.outputs.vm_ips['db-server-01'] }}"
```

### CI/CD Integration

In GitHub Actions:

```yaml
- name: Apply infrastructure
  run: infra apply --env prod --auto-approve

- name: Run Ansible playbooks
  run: |
    cd generated/ansible/proxmox/
    ansible-playbook -i inventory.yml playbook.yml
```

### Monitoring Integration

Deploy monitoring with Ansible:

```yaml
ansible_roles:
  - prometheus-node-exporter
  - filebeat
  - telegraf

ansible_vars:
  prometheus_server: monitoring.example.com:9090
  elasticsearch_host: logs.example.com:9200
```

## Related Documentation

- [Ansible Documentation](https://docs.ansible.com/)
- [Ansible Galaxy](https://galaxy.ansible.com/)
- [InfraFoundry Separate Config Repository Guide](separate-config-repo.md)
- [Provider Plugin Development](plugin-development.md)
- [CI/CD Integration](../ci/separate-config-ci.md)
