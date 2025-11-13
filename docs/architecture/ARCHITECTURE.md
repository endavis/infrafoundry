# Infrastructure Architecture

InfraFoundry's core infrastructure enables advanced features like drift detection, impact analysis, and automated rollback through a robust foundation of state management, event handling, and dependency resolution.

## Core Components

### 1. State Management (`src/infrafoundry/core/state.py`)

Tracks the complete lifecycle of deployments and resources using SQLAlchemy ORM.

**Database Schema:**

- **deployments**: Records of plan/apply/destroy operations
  - Environment, command, status, timestamps
  - User tracking and git commit SHA
  - Error messages for failed deployments

- **resources**: Individual infrastructure resources
  - Full configuration and state tracking
  - Terraform resource IDs
  - Lifecycle states: PLANNED, CREATING, ACTIVE, UPDATING, DELETING, DELETED, ERROR

- **resource_dependencies**: Dependency relationships
  - Tracks what resources depend on others
  - Enables impact analysis

- **deployment_events**: Audit trail
  - Every event during a deployment
  - Resource-specific events
  - Full metadata for debugging

**StateManager API:**

```python
# Create deployment record
deployment_id = state_manager.create_deployment(
    environment="prod",
    command="apply",
    user="alice",
    commit_sha="abc123"
)

# Track resource
resource = state_manager.track_resource(
    deployment_id=deployment_id,
    environment="prod",
    provider="proxmox",
    resource_type="vm",
    name="web-01",
    state=ResourceState.CREATING
)

# Query history
deployments = state_manager.get_deployment_history(
    environment="prod",
    limit=50
)

# Query resources
resources = state_manager.get_resources(
    environment="prod",
    provider="proxmox",
    state=ResourceState.ACTIVE
)
```

**Storage Backends:**

- **SQLite** (default): Local development, single-user
  - Location: `~/.infrafoundry/state.db`
  - Zero configuration

- **PostgreSQL**: Team usage, production
  - Concurrent access
  - Better performance for large deployments
  - Set `INFRAFOUNDRY_STATE_CONNECTION` environment variable

### 2. Event System (`src/infrafoundry/core/events.py`)

Pub/sub pattern for lifecycle hooks and plugin integration.

**Event Types:**

- **Planning**: `BEFORE_PLAN`, `AFTER_PLAN`, `PLAN_FAILED`
- **Apply**: `BEFORE_APPLY`, `AFTER_APPLY`, `APPLY_FAILED`
- **Destroy**: `BEFORE_DESTROY`, `AFTER_DESTROY`, `DESTROY_FAILED`
- **Resource Lifecycle**: `RESOURCE_PLANNED`, `RESOURCE_CREATING`, `RESOURCE_CREATED`, etc.
- **Validation**: `VALIDATION_STARTED`, `VALIDATION_PASSED`, `VALIDATION_FAILED`
- **Drift**: `DRIFT_DETECTED`, `DRIFT_CHECK_STARTED`, `DRIFT_CHECK_COMPLETED`

**Usage:**

```python
from infrafoundry.core.events import EventManager, EventType, Event

event_manager = EventManager()

# Subscribe to specific events
def on_resource_created(event: Event):
    print(f"Resource created: {event.data['name']}")
    # Send notification, update dashboard, etc.

event_manager.subscribe(EventType.RESOURCE_CREATED, on_resource_created)

# Subscribe to all events
def audit_logger(event: Event):
    log.info(f"{event.event_type} in {event.environment}: {event.data}")

event_manager.subscribe_all(audit_logger)

# Emit events
event_manager.emit_event(
    EventType.RESOURCE_CREATED,
    environment="prod",
    data={"name": "web-01", "provider": "proxmox"}
)
```

**Use Cases:**

- Notifications (Slack, email) on deployment events
- Custom validation hooks
- Metrics collection and monitoring
- Audit logging
- Integration with external systems
- Policy enforcement

### 3. Dependency Resolution (`src/infrafoundry/core/dependencies.py`)

Smart dependency graph management with topological sorting.

**Features:**

- **Circular dependency detection**: Identifies cycles with full path
- **Topological sort with batching**: Groups independent resources for parallel execution
- **Impact analysis**: Shows all downstream resources affected by a change
- **Risk scoring**: Automatic risk levels based on dependent count
- **Transitive dependencies**: Get complete dependency chains

**API:**

```python
from infrafoundry.core.dependencies import DependencyGraph

graph = DependencyGraph()

# Add resources with dependencies
graph.add_resource("proxmox", "vm", "web-01", dependencies=["network", "template"])
graph.add_resource("proxmox", "network", "vlan100", dependencies=[])
graph.add_resource("proxmox", "template", "ubuntu-22-04", dependencies=[])

# Get execution order (batches can run in parallel)
batches = graph.topological_sort()
# Result: [
#   ["proxmox:network", "proxmox:template"],  # Batch 1 (parallel)
#   ["proxmox:web-01"]                        # Batch 2 (depends on batch 1)
# ]

# Impact analysis
impact = graph.get_impact_analysis("proxmox:template")
# Result: {
#   "resource": "proxmox:template",
#   "direct_dependents": 1,
#   "total_dependents": 1,
#   "dependent_resources": ["proxmox:web-01"],
#   "risk_level": "LOW"
# }

# Detect circular dependencies
try:
    batches = graph.topological_sort()
except CircularDependencyError as e:
    print(f"Circular dependency: {e}")
```

**Risk Levels:**

- **LOW**: 0 dependents
- **MEDIUM**: 1-5 dependents
- **HIGH**: 6-20 dependents
- **CRITICAL**: 21+ dependents

### 4. Orchestrator Integration

The `Orchestrator` class ties everything together:

```python
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.state import StateManager
from infrafoundry.core.events import EventManager

# Initialize with state and event management
state_manager = StateManager()
event_manager = EventManager()

orchestrator = Orchestrator(
    config_manager,
    secret_manager,
    state_manager=state_manager,
    event_manager=event_manager
)

# All operations now automatically:
# - Create deployment records
# - Track resource state
# - Emit lifecycle events
# - Handle errors gracefully
# - Record complete audit trails
```

## CLI Integration

### Initialize State Database

```bash
infra init
```

Creates SQLite database at `~/.infrafoundry/state.db` with full schema.

### View Deployment History

```bash
# All deployments
infra history

# Filter by environment
infra history --env prod

# Limit results
infra history --limit 20
```

Shows:
- Deployment ID
- Environment
- Command (plan/apply/destroy)
- Status (completed/failed/in_progress)
- Timestamp
- User

## Configuration

### Environment Variables

```bash
# State backend type (default: sqlite)
export INFRAFOUNDRY_STATE_BACKEND=sqlite

# Custom connection string (optional)
export INFRAFOUNDRY_STATE_CONNECTION=sqlite:////custom/path/state.db

# PostgreSQL example
export INFRAFOUNDRY_STATE_BACKEND=postgresql
export INFRAFOUNDRY_STATE_CONNECTION=postgresql://user:pass@localhost/infrafoundry
```

### Default Locations

- SQLite database: `~/.infrafoundry/state.db`
- Auto-created on first `infra init`

## Implemented Advanced Features

These features are fully implemented and available via CLI:

### Drift Detection ✅
Compare actual infrastructure state vs declared configuration:
```bash
infra drift --env prod
# Shows: resources modified outside Terraform, manual changes, missing resources
```

**Implementation:** `core/drift_detector.py` (140 lines)
- Uses Terraform plan to detect changes
- Parses output for add/change/destroy counts
- Rich console output with tables
- Event integration: DRIFT_CHECK_STARTED, DRIFT_DETECTED, DRIFT_CHECK_COMPLETED

### Impact Analysis ✅
Preview downstream effects before making changes:
```bash
infra impact --env prod --resource db-template
# Shows: All VMs using this template, risk level, suggested actions
```

**Implementation:** Built into `core/dependencies/` package
- Dependency graph with topological sorting
- Risk levels: LOW (0), MEDIUM (1-5), HIGH (6-20), CRITICAL (21+)
- Transitive dependency analysis
- CLI command: `cli/commands/impact.py`

### Automated Rollback ✅
Revert to previous known-good state:
```bash
infra rollback --env prod --to-deployment 42
# Reverts infrastructure to deployment #42 state

infra rollback-points --env prod
# Lists available rollback points
```

**Implementation:** `cli/commands/rollback.py` and state management
- Tracks all deployment history in state database
- Can rollback to any previous deployment
- State restoration from deployment records

### Parallel Execution ✅
Optimize deployment time using dependency graph:
```bash
# Parallel execution is built into DeploymentExecutor
# Providers run in parallel by default where safe
```

**Implementation:** `core/deployment_executor.py` (269 lines)
- `apply_parallel()` with ThreadPoolExecutor
- Configurable max workers
- Provider ordering for dependencies (opnsense → proxmox → kubernetes)
- Progress tracking with rich console

### Policy Enforcement ✅
Validate before deployment using policy engine:
```bash
infra policies list
# Lists available policies

infra policies check --env prod
# Checks: resource limits, naming conventions, security policies
```

**Implementation:** `core/policy/` package (complete)
- PolicyEngine with pluggable evaluators
- Policy types: RESOURCE_LIMIT, NAMING_CONVENTION, SECURITY, COMPLIANCE
- Policy levels: ERROR (blocks), WARNING (warns), INFO (logs)
- Event integration throughout orchestrator
- CLI commands: `cli/commands/policies.py`

### Pre-flight Validation ✅
Comprehensive configuration validation:
```bash
infra validate --env test
# Checks: API connectivity, resources exist, no conflicts

infra validate --env test --verbose
# Shows detailed validation output including passing checks
```

**Implementation:** `core/validation_helpers/` package (complete)
- BaseValidator, ConnectivityValidator, CredentialValidator, ResourceValidator
- ValidationReport with error/warning/info levels
- Rich console output
- CLI command: `cli/commands/validate.py`

### Provider Auto-Discovery ✅
Automatic provider registration:

**Implementation:** `core/provider_registry.py` (149 lines)
- Scans `providers/` directory
- Dynamically imports and instantiates providers
- No manual registration needed in CLI

## Design Principles

1. **Separation of Concerns**: State, events, and dependencies are independent modules
2. **Extensibility**: Event system allows plugins without core changes
3. **Backwards Compatibility**: Existing deployments work without state tracking (degrades gracefully)
4. **Performance**: SQLite for speed, PostgreSQL for scale
5. **Developer Experience**: Rich CLI output, clear error messages, helpful defaults

## Implementation Details

### Why SQLAlchemy?

- **Database agnostic**: Same code works with SQLite and PostgreSQL
- **Type safety**: Pydantic-style models with validation
- **Migration support**: Alembic for schema changes
- **ORM benefits**: Relationships, lazy loading, query optimization

### Why Pub/Sub Events?

- **Decoupling**: Core logic doesn't know about plugins
- **Flexibility**: Add/remove handlers without changing orchestrator
- **Testing**: Easy to mock and verify event emissions
- **Error isolation**: One handler failure doesn't break others

### Why Dependency Graphs?

- **Correctness**: Ensures resources created in right order
- **Performance**: Enables parallel execution of independent resources
- **Safety**: Detects circular dependencies before deployment
- **Analysis**: Powers impact analysis and risk assessment

## Testing State Management

```bash
# Initialize database
infra init

# Run a plan (creates deployment record)
infra plan --env dev --dry-run

# View history
infra history

# Check database directly
sqlite3 ~/.infrafoundry/state.db
sqlite> SELECT * FROM deployments;
sqlite> SELECT * FROM resources;
```

## Troubleshooting

### Database locked error

SQLite doesn't handle concurrent writes well. For teams, use PostgreSQL:

```bash
export INFRAFOUNDRY_STATE_BACKEND=postgresql
export INFRAFOUNDRY_STATE_CONNECTION=postgresql://localhost/infrafoundry
```

### State database not found

Run `infra init` to create it:

```bash
infra init
```

### View raw state

```bash
sqlite3 ~/.infrafoundry/state.db ".dump" | less
```

## Contributing

To extend the state management:

1. Add new columns to models in `state.py`
2. Create migration with Alembic
3. Update `StateManager` methods
4. Add tests

To add new event types:

1. Add to `EventType` enum in `events.py`
2. Emit from appropriate locations
3. Document usage in this file
4. Add example handler

## References

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Dependency Resolution Algorithms](https://en.wikipedia.org/wiki/Topological_sorting)
- [Observer Pattern (Pub/Sub)](https://en.wikipedia.org/wiki/Observer_pattern)
