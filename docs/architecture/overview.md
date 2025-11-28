# InfraFoundry Architecture Overview

## System Architecture

InfraFoundry is built around a clear separation of concerns:

**Code Generation Layer:**
- **Providers**: Pluggable modules (Proxmox, OPNsense, Kubernetes) that implement `ProviderBase`
- **Templates**: Jinja2 templates for generating Terraform `.tf` files and Ansible playbooks
- **Config Manager**: Loads and validates YAML configurations
- **Secret Manager**: Handles SOPS encryption/decryption, exports secrets to Terraform/Ansible

**Orchestration Layer:**
- **Orchestrator**: Coordinates multi-provider deployments, manages dependencies, optionally executes tools
- **CLI**: Click-based command-line interface with rich console output
- **State Manager**: SQLite database tracking deployment history and resource lifecycle
- **Event System**: Hooks for notifications and custom integrations
- **Policy Engine**: Validates resources against organizational policies

## Data Flow

```
YAML Configs → ConfigManager → Providers → Jinja2 Templates → Generated Files
                                    ↓
                              Orchestrator (optional)
                                    ↓
                    terraform init/apply  +  ansible-playbook
                                    ↓
                              Infrastructure
```

## Key Design Principles

1. **Generation before execution** - Always generate configs first, optionally execute
2. **Provider plugins** - Easy to add new providers (ESXi, AWS, Azure, etc.)
3. **Tool agnostic** - Generated files are standard Terraform/Ansible, work without InfraFoundry
4. **Separate configs** - Framework code separate from infrastructure definitions

## How It Works

InfraFoundry follows a clear workflow that separates code generation from execution:

### 1. Plan (Generate Only)

```bash
infra plan --env dev
```

**What happens:**
- ✅ Reads YAML configs from `envs/dev/`
- ✅ Validates resources and dependencies
- ✅ Generates Terraform files → `generated/{env}/terraform/{provider}/`
- ✅ Generates Ansible playbooks → `generated/{env}/ansible/{provider}/`
- ❌ Does NOT execute terraform or ansible
- ❌ Does NOT create any infrastructure

**Output:** Generated `.tf` files and playbooks ready for review

### 2. Apply (Generate + Execute)

```bash
infra apply --env dev
```

**What happens:**
- ✅ Generates configs (same as plan)
- ✅ Runs `terraform init` (first time only)
- ✅ Runs `terraform apply` for each provider
- ✅ Runs `ansible-playbook` (if playbooks exist)
- ✅ Tracks deployment in state database

**Result:** Infrastructure is provisioned and configured

### 3. Destroy (Execute Removal)

```bash
infra destroy --env dev
```

**What happens:**
- ✅ Runs `terraform destroy` for each provider
- ✅ Updates state database

## Generated Files Structure

```
generated/
├── dev/                         # Environment: dev
│   ├── terraform/
│   │   ├── proxmox/
│   │   │   ├── main.tf          # Generated from YAML
│   │   │   ├── variables.tf     # Generated from YAML
│   │   │   ├── outputs.tf       # Generated from YAML
│   │   │   └── .terraform/      # Created by terraform init
│   │   ├── opnsense/
│   │   │   └── ...
│   │   └── kubernetes/
│   │       └── ...
│   └── ansible/
│       ├── proxmox/
│       │   ├── playbook.yml     # Generated from YAML
│       │   ├── inventory.yml    # Generated from YAML
│       │   └── roles/           # Your custom roles
│       └── ...
├── staging/                     # Environment: staging
│   ├── terraform/
│   └── ansible/
└── prod/                        # Environment: prod
    ├── terraform/
    └── ansible/
```

**Key Point:** Each environment has its own directory with separate Terraform state!

- ✅ Can work on dev and prod simultaneously
- ✅ Terraform state isolated per environment
- ✅ No risk of overwriting one environment with another
- ✅ Clear separation for team collaboration

**You can review and manually execute the generated files if you prefer:**

```bash
# Generate configs only
infra plan --env dev

# Manually review generated files
cd generated/dev/terraform/proxmox
cat main.tf

# Manually execute (instead of infra apply)
terraform init
terraform plan
terraform apply

# Run Ansible separately
cd ../../ansible/proxmox
ansible-playbook -i inventory.yml playbook.yml
```

**For production:** Configure remote Terraform backend in your generated files to share state with your team.
