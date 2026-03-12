# Ansible Roles Directory Structure

This directory contains reusable Ansible roles for configuring infrastructure.

## Structure

```
roles/
├── k3s-server/          # K3s control plane installation
├── k3s-agent/           # K3s worker node installation
├── tailscale-exit-node/ # Tailscale VPN exit node (includes example)
├── common/              # Base configuration for all servers
├── webserver/           # Nginx/Apache web server
├── database/            # Database servers (PostgreSQL, MySQL)
├── docker/              # Docker installation and configuration
├── monitoring/          # Monitoring agents (Prometheus, etc.)
└── custom/              # Your custom roles
```

## Example Roles

This repository includes a complete example role:

### Tailscale Exit Node (`tailscale-exit-node/`)

A production-ready role that configures a Tailscale exit node with:
- ✅ Support for regular Linux (Ubuntu, Debian, RHEL, Fedora)
- ✅ Support for immutable Linux (Ubuntu Core)
- ✅ Automatic distribution detection and package manager selection
- ✅ IP forwarding configuration
- ✅ Firewall configuration (UFW/firewalld)
- ✅ Exit node and subnet route advertisement

**Quick Usage:**
```yaml
vms:
  - name: exit-node-01
    # ... VM config ...
    ansible_roles:
      - tailscale-exit-node
    ansible_vars:
      tailscale_auth_key: "{{ vault_tailscale_auth_key }}"
```

See [tailscale-exit-node/README.md](tailscale-exit-node/README.md) for full documentation or [tailscale-exit-node/QUICKSTART.md](tailscale-exit-node/QUICKSTART.md) for quick deployment guide.

### K3s Cluster (`k3s-server/` and `k3s-agent/`)

Production-ready roles for deploying lightweight Kubernetes (K3s) clusters:

**k3s-server** - Control plane installation:
- ✅ Installs K3s in server mode
- ✅ Configures TLS SANs for remote access (Tailscale)
- ✅ Fetches kubeconfig to local machine
- ✅ Supports custom cluster/service CIDRs

**k3s-agent** - Worker node installation:
- ✅ Automatically fetches join token from control plane
- ✅ Joins existing K3s cluster
- ✅ Supports node labels and taints

**Quick Usage:**
```yaml
instance:
  # Control plane
  - name: k3s-control
    ansible_roles:
      - k3s-server
    ansible_vars:
      kubeconfig_local_path: "~/.kube/my-cluster.yaml"

  # Workers
  - name: k3s-worker-0
    ansible_roles:
      - k3s-agent
    ansible_vars:
      k3s_control_host: "k3s-control"
```

See [k3s-server/README.md](k3s-server/README.md) and [k3s-agent/README.md](k3s-agent/README.md) for full documentation.

For a complete OCI deployment example with Tailscale, see [envs/oci-k3s/](../envs/oci-k3s/).

## Using Roles in Configuration

### In VM Configurations

Add `ansible_roles` to your VM definition:

```yaml
vms:
  - name: web-server-01
    vmid: 100
    # ... VM configuration ...
    ansible_roles:
      - webserver
      - docker
      - monitoring-agent
```

### In Resource Configurations

For other resource types, add `ansible_tasks` for custom configuration:

```yaml
vms:
  - name: app-server-01
    vmid: 101
    # ... VM configuration ...
    ansible_roles:
      - nodejs
    ansible_tasks:
      - name: Install PM2
        module: npm
        params:
          name: pm2
          global: yes
      - name: Deploy application
        module: git
        params:
          repo: https://github.com/myorg/myapp.git
          dest: /opt/myapp
```

## Creating Custom Roles

### Basic Role Structure

```bash
roles/myapp/
├── tasks/
│   └── main.yml       # Main task list
├── handlers/
│   └── main.yml       # Handlers (e.g., restart services)
├── templates/
│   └── config.j2      # Jinja2 templates
├── files/
│   └── script.sh      # Static files to copy
├── vars/
│   └── main.yml       # Variables
├── defaults/
│   └── main.yml       # Default variables
└── meta/
    └── main.yml       # Role dependencies
```

### Example: Web Server Role

`roles/webserver/tasks/main.yml`:

```yaml
---
- name: Install Nginx
  apt:
    name: nginx
    state: present
  when: ansible_os_family == "Debian"

- name: Start and enable Nginx
  systemd:
    name: nginx
    state: started
    enabled: yes

- name: Deploy site configuration
  template:
    src: vhost.conf.j2
    dest: /etc/nginx/sites-available/default
  notify: reload nginx
```

`roles/webserver/handlers/main.yml`:

```yaml
---
- name: reload nginx
  systemd:
    name: nginx
    state: reloaded
```

`roles/webserver/templates/vhost.conf.j2`:

```nginx
server {
    listen 80;
    server_name {{ ansible_fqdn }};

    location / {
        root /var/www/html;
        index index.html;
    }
}
```

### Example: Docker Role

`roles/docker/tasks/main.yml`:

```yaml
---
- name: Install prerequisites
  apt:
    name:
      - apt-transport-https
      - ca-certificates
      - curl
      - gnupg
      - lsb-release
    state: present

- name: Add Docker GPG key
  apt_key:
    url: https://download.docker.com/linux/ubuntu/gpg
    state: present

- name: Add Docker repository
  apt_repository:
    repo: "deb [arch=amd64] https://download.docker.com/linux/ubuntu {{ ansible_distribution_release }} stable"
    state: present

- name: Install Docker
  apt:
    name:
      - docker-ce
      - docker-ce-cli
      - containerd.io
    state: present
    update_cache: yes

- name: Add user to docker group
  user:
    name: "{{ ansible_user }}"
    groups: docker
    append: yes
```

## Role Variables

Roles can accept variables from your configuration:

`roles/webserver/defaults/main.yml`:

```yaml
---
webserver_port: 80
webserver_root: /var/www/html
webserver_worker_processes: auto
```

Use in VM configuration:

```yaml
vms:
  - name: web-01
    # ... VM config ...
    ansible_roles:
      - webserver
    ansible_vars:
      webserver_port: 8080
      webserver_root: /opt/webapp
```

## Role Dependencies

Roles can depend on other roles:

`roles/webapp/meta/main.yml`:

```yaml
---
dependencies:
  - role: common
  - role: webserver
  - role: docker
```

## Best Practices

1. **Idempotent Tasks**: Ensure tasks can run multiple times safely
2. **Use Templates**: For configuration files that need customization
3. **Handle Different OSes**: Use `when` conditions for OS-specific tasks
4. **Tag Tasks**: Allow selective execution
   ```yaml
   - name: Install packages
     apt: ...
     tags: [packages, setup]
   ```
5. **Test Roles**: Use Molecule for role testing
6. **Version Control**: Keep roles in git with semantic versioning
7. **Documentation**: Document role variables and usage

## Example Roles Library

### Common Role

Basic setup for all servers:

```yaml
# roles/common/tasks/main.yml
---
- name: Update package cache
  apt:
    update_cache: yes
    cache_valid_time: 3600

- name: Install essential packages
  apt:
    name:
      - vim
      - curl
      - wget
      - git
      - htop
      - net-tools
    state: present

- name: Configure timezone
  timezone:
    name: "{{ server_timezone | default('UTC') }}"

- name: Configure NTP
  systemd:
    name: systemd-timesyncd
    state: started
    enabled: yes
```

### Monitoring Agent Role

```yaml
# roles/monitoring-agent/tasks/main.yml
---
- name: Install Prometheus Node Exporter
  get_url:
    url: https://github.com/prometheus/node_exporter/releases/download/v1.6.1/node_exporter-1.6.1.linux-amd64.tar.gz
    dest: /tmp/node_exporter.tar.gz

- name: Extract Node Exporter
  unarchive:
    src: /tmp/node_exporter.tar.gz
    dest: /usr/local/bin
    remote_src: yes

- name: Create systemd service
  template:
    src: node_exporter.service.j2
    dest: /etc/systemd/system/node_exporter.service
  notify: restart node exporter
```

## Using Roles from Ansible Galaxy

You can also use roles from Ansible Galaxy:

`requirements.yml` in your config repo:

```yaml
---
roles:
  - name: geerlingguy.docker
    version: 6.1.0
  - name: geerlingguy.nginx
    version: 3.1.4
  - name: geerlingguy.postgresql
    version: 3.4.7
```

Install with:

```bash
ansible-galaxy install -r requirements.yml -p roles/
```

Use in configurations:

```yaml
vms:
  - name: server-01
    # ... VM config ...
    ansible_roles:
      - geerlingguy.docker
      - geerlingguy.nginx
```

## Integration with InfraFoundry

InfraFoundry will:
1. Generate Ansible playbooks with your specified roles
2. Run playbooks in check mode by default (dry run)
3. Apply roles after infrastructure is provisioned
4. Look for roles in standard locations:
   - `roles/` in your config repository
   - `~/.ansible/roles`
   - `/etc/ansible/roles`

## Related Documentation

- [Ansible Roles Documentation](https://docs.ansible.com/ansible/latest/user_guide/playbooks_reuse_roles.html)
- [Ansible Galaxy](https://galaxy.ansible.com/)
- [Molecule Testing](https://molecule.readthedocs.io/)
