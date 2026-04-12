# Using InfraFoundry in CI/CD with Separate Configuration Repository

This guide shows how to set up CI/CD when using a separate configuration repository.

## Architecture

- **Framework Repository**: Contains InfraFoundry framework code
- **Config Repository**: Contains your infrastructure configurations (this repo)

CI/CD workflows run in the **config repository** and checkout the framework as a dependency.

## GitHub Actions Example

Create `.github/workflows/deploy-infrastructure.yml` in your **config repository**:

```yaml
name: Deploy Infrastructure

on:
  push:
    branches: [main]
    paths:
      - 'envs/**'
      - 'secrets/**'
  pull_request:
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to deploy'
        required: true
        type: choice
        options:
          - dev
          - staging
          - prod
      action:
        description: 'Action to perform'
        required: true
        type: choice
        options:
          - plan
          - apply
          - destroy

env:
  PYTHON_VERSION: '3.11'
  INFRAFOUNDRY_VERSION: 'v0.1.0'  # Pin to specific framework version

jobs:
  deploy:
    name: Deploy to ${{ github.event.inputs.environment || 'dev' }}
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment || 'dev' }}

    steps:
      - name: Checkout configuration repository
        uses: actions/checkout@v4
        with:
          path: config

      - name: Checkout InfraFoundry framework
        uses: actions/checkout@v4
        with:
          repository: your-org/infrafoundry  # Your framework repo
          ref: ${{ env.INFRAFOUNDRY_VERSION }}
          path: infrafoundry

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: 'pip'

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install InfraFoundry
        run: |
          cd infrafoundry
          uv pip install --system -e .

      - name: Install infrastructure tools
        run: |
          # Terraform
          wget -O- https://apt.releases.hashicorp.com/gpg | \
            sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
          echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
            https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
            sudo tee /etc/apt/sources.list.d/hashicorp.list
          sudo apt update && sudo apt install -y terraform

          # Ansible
          uv pip install --system ansible

          # SOPS
          SOPS_VERSION=v3.8.1
          wget https://github.com/getsops/sops/releases/download/${SOPS_VERSION}/sops-${SOPS_VERSION}.linux.amd64
          sudo mv sops-${SOPS_VERSION}.linux.amd64 /usr/local/bin/sops
          sudo chmod +x /usr/local/bin/sops

      - name: Set up age encryption key
        run: |
          cd config
          mkdir -p secrets
          echo "${{ secrets.SOPS_AGE_KEY }}" | base64 -d > envs/dev/age.key
          chmod 600 envs/dev/age.key

      - name: Set environment variables
        run: |
          cd config
          echo "INFRAFOUNDRY_CONFIG_REPO=$(pwd)" >> $GITHUB_ENV
          echo "SOPS_AGE_KEY_FILE=$(pwd)/envs/dev/age.key" >> $GITHUB_ENV
          echo "INFRAFOUNDRY_LOG_LEVEL=INFO" >> $GITHUB_ENV

      - name: Validate configuration
        run: |
          infra envs
          echo "Deploying to: ${{ github.event.inputs.environment || 'dev' }}"

      - name: Plan infrastructure
        if: github.event.inputs.action != 'apply' && github.event.inputs.action != 'destroy'
        run: |
          infra plan --env ${{ github.event.inputs.environment || 'dev' }}

      - name: Apply infrastructure
        if: github.event.inputs.action == 'apply'
        run: |
          infra apply --env ${{ github.event.inputs.environment || 'dev' }} --auto-approve

      - name: Destroy infrastructure
        if: github.event.inputs.action == 'destroy'
        run: |
          infra destroy --env ${{ github.event.inputs.environment || 'dev' }} --auto-approve

      - name: Show status
        if: always()
        run: |
          infra status --env ${{ github.event.inputs.environment || 'dev' }} || true

      - name: Upload generated files
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: generated-${{ github.event.inputs.environment || 'dev' }}
          path: config/generated/
          retention-days: 7
```

## GitLab CI Example

Create `.gitlab-ci.yml` in your **config repository**:

```yaml
stages:
  - validate
  - plan
  - apply

variables:
  INFRAFOUNDRY_VERSION: "v0.1.0"
  PYTHON_VERSION: "3.11"
  GIT_STRATEGY: clone
  GIT_SUBMODULE_STRATEGY: none

.setup_template: &setup
  before_script:
    # Install system dependencies
    - apt-get update && apt-get install -y python3-pip git curl wget

    # Install Python tools
    - curl -LsSf https://astral.sh/uv/install.sh | sh
    - export PATH="$HOME/.cargo/bin:$PATH"

    # Clone and install InfraFoundry framework
    - git clone --depth 1 --branch ${INFRAFOUNDRY_VERSION} https://github.com/your-org/infrafoundry.git
    - cd infrafoundry && uv pip install --system -e . && cd ..

    # Install Terraform
    - |
      wget -O- https://apt.releases.hashicorp.com/gpg | \
        gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
      echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
        https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
        tee /etc/apt/sources.list.d/hashicorp.list
      apt update && apt install -y terraform

    # Install Ansible
    - uv pip install --system ansible

    # Install SOPS
    - |
      SOPS_VERSION=v3.8.1
      wget https://github.com/getsops/sops/releases/download/${SOPS_VERSION}/sops-${SOPS_VERSION}.linux.amd64
      mv sops-${SOPS_VERSION}.linux.amd64 /usr/local/bin/sops
      chmod +x /usr/local/bin/sops

    # Set up age key
    - mkdir -p secrets
    - echo "$SOPS_AGE_KEY" | base64 -d > envs/dev/age.key
    - chmod 600 envs/dev/age.key

    # Set environment variables
    - export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
    - export SOPS_AGE_KEY_FILE="$(pwd)/envs/dev/age.key"
    - export INFRAFOUNDRY_LOG_LEVEL=INFO

validate:
  stage: validate
  <<: *setup
  script:
    - infra envs
    - echo "Configuration validated"
  only:
    - merge_requests
    - main
    - develop

.plan_template: &plan
  stage: plan
  <<: *setup
  artifacts:
    paths:
      - generated/
    expire_in: 1 day
  only:
    - merge_requests
    - main

plan:dev:
  <<: *plan
  script:
    - infra plan --env dev

plan:staging:
  <<: *plan
  script:
    - infra plan --env staging
  only:
    - main

plan:prod:
  <<: *plan
  script:
    - infra plan --env prod
  only:
    - main

.apply_template: &apply
  stage: apply
  <<: *setup
  only:
    - main

apply:dev:
  <<: *apply
  script:
    - infra apply --env dev --auto-approve
  when: manual
  environment:
    name: dev
    on_stop: destroy:dev

apply:staging:
  <<: *apply
  script:
    - infra apply --env staging --auto-approve
  when: manual
  environment:
    name: staging
  needs:
    - plan:staging

apply:prod:
  <<: *apply
  script:
    - infra apply --env prod --auto-approve
  when: manual
  environment:
    name: production
  needs:
    - plan:prod

destroy:dev:
  <<: *apply
  script:
    - infra destroy --env dev --auto-approve
  when: manual
  environment:
    name: dev
    action: stop
```

## Required Secrets

### GitHub Secrets

In your **config repository** settings, add:

**Encryption:**
- `SOPS_AGE_KEY` - Base64-encoded age key
  ```bash
  cat envs/dev/age.key | base64 -w0
  ```

**Kubernetes:**
- `KUBECONFIG` - Base64-encoded kubeconfig file (if needed)

### GitLab CI/CD Variables

In your **config repository** Settings > CI/CD > Variables, add:

- `SOPS_AGE_KEY` - Base64-encoded age key (Masked, Protected)
- `KUBECONFIG` - Kubernetes configuration (Masked, if needed)

## Framework Repository CI/CD

The **framework repository** should have different CI/CD focused on code quality:

```yaml
# .github/workflows/test.yml in framework repo
name: Test Framework

on:
  push:
    branches: [main, develop]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install uv
      - run: uv pip install --system -e .[dev]
      - run: doit test
      - run: doit lint
      - run: doit format
```

## Best Practices

1. **Pin Framework Version**: Always specify exact framework version in CI
   ```yaml
   INFRAFOUNDRY_VERSION: "v0.1.0"  # Not "latest" or "main"
   ```

2. **Separate Environments**: Use GitLab environments or GitHub environments for dev/staging/prod

3. **Manual Production Deploys**: Require manual approval for production
   ```yaml
   when: manual
   environment: production
   ```

4. **Artifact Retention**: Save generated files for debugging
   ```yaml
   artifacts:
     paths: [generated/]
     expire_in: 7 days
   ```

5. **Status Checks**: Always run status even if deploy fails
   ```yaml
   if: always()
   ```

6. **Branch Protection**: Protect main branch, require reviews

7. **Test on Branches**: Run plan on feature branches, apply only on main

## Troubleshooting

### Framework not found

Ensure correct repository URL:
```yaml
repository: your-org/infrafoundry  # Update to your org/repo
ref: ${{ env.INFRAFOUNDRY_VERSION }}
```

### Secrets decryption fails

Check `SOPS_AGE_KEY` secret:
```bash
# Encode correctly
cat envs/dev/age.key | base64 -w0

# Add as secret without newlines
```

### Config repo not found

Verify `INFRAFOUNDRY_CONFIG_REPO` is set:
```yaml
- name: Set environment variables
  run: |
    cd config
    echo "INFRAFOUNDRY_CONFIG_REPO=$(pwd)" >> $GITHUB_ENV
```

### Commands run in wrong directory

Always ensure you're in the config repo:
```yaml
- name: Run command
  working-directory: config  # or use 'cd config' in script
  run: infra plan --env dev
```

## Related Documentation

- [Separate Config Repo Pattern](../configuration/separate-config-repo.md)
- [CI/CD Deployment Guide](../development/ci-cd-deployment.md)
- [Age Key Management](age-key-management.md)
- [GitHub Actions Documentation](https://docs.github.com/actions)
- [GitLab CI/CD Documentation](https://docs.gitlab.com/ee/ci/)

---

Last updated: 2026-01-25

---
[Back to Table of Contents](../index.md)
