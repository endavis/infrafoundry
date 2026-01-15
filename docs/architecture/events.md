# Event System Architecture

## Overview

InfraFoundry implements a synchronous publish-subscribe event system for orchestration lifecycle management, enabling decoupled notifications, auditing, and extensibility throughout the infrastructure automation workflow.

## Design Goals

1. **Decoupling**: Separate event producers from consumers
2. **Extensibility**: Allow plugins and integrations to hook into workflows
3. **Observability**: Provide visibility into orchestration lifecycle
4. **Simplicity**: Lightweight, synchronous design for predictable execution

## Architecture

### Event Flow

```
┌─────────────┐
│  Provider   │
│ / Runner    │──┐
└─────────────┘  │
                 │ emit_event()
┌─────────────┐  │
│Orchestrator │──┤
└─────────────┘  │
                 │
┌─────────────┐  │        ┌──────────────┐
│CLI Commands │──┴───────>│EventManager  │
└─────────────┘           │ (singleton)  │
                          └──────┬───────┘
                                 │ dispatch
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    v            v            v
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │Notification│State     │ Audit    │
              │Manager   │ │Manager   │ │Logger   │
              └──────────┘ └──────────┘ └──────────┘
```

### Core Components

#### EventManager

Central event dispatcher implementing pub-sub pattern.

**Responsibilities:**
- Register event subscribers
- Dispatch events to registered handlers
- Maintain subscription registry
- Ensure synchronous execution

**Key Methods:**
```python
def subscribe(event_type: EventType, handler: Callable[[Event], None]) -> None
def subscribe_all(handler: Callable[[Event], None]) -> None
def emit_event(event_type: EventType, environment: str, data: dict) -> None
```

#### Event

Data structure representing a single event occurrence.

**Structure:**
```python
@dataclass
class Event:
    event_type: EventType           # Type of event
    environment: str                # Environment context
    data: dict[str, Any]           # Event-specific payload
    timestamp: datetime             # When event occurred
```

#### EventType Enum

Categorized event types for different lifecycle phases and operations.

**Categories:**

1. **Lifecycle Events** - Orchestration workflow phases
   - `BEFORE_PLAN`, `AFTER_PLAN`, `PLAN_FAILED`
   - `BEFORE_APPLY`, `AFTER_APPLY`, `APPLY_FAILED`
   - `BEFORE_DESTROY`, `AFTER_DESTROY`, `DESTROY_FAILED`

2. **Resource Events** - Individual resource lifecycle
   - `RESOURCE_CREATED`
   - `RESOURCE_UPDATED`
   - `RESOURCE_DELETED`
   - `RESOURCE_FAILED`

3. **Drift Events** - Configuration drift detection
   - `DRIFT_DETECTED`
   - `DRIFT_REMEDIATION_STARTED`
   - `DRIFT_REMEDIATION_COMPLETED`
   - `DRIFT_REMEDIATION_FAILED`

4. **Policy Events** - Governance validation
   - `POLICY_CHECK_STARTED`
   - `POLICY_VIOLATION`
   - `POLICY_CHECK_PASSED`

5. **Validation Events** - Configuration validation
   - `VALIDATION_STARTED`
   - `VALIDATION_COMPLETED`
   - `VALIDATION_FAILED`

## Event Consumers

### Built-in Consumers

#### NotificationManager

Forwards events to configured notification channels (email, Slack, webhooks).

**Subscription:**
- Subscribes to all events via `subscribe_all()`
- Filters based on notification configuration
- Routes to appropriate channels

#### StateManager

Tracks state changes and resource lifecycle.

**Subscriptions:**
- `RESOURCE_CREATED`, `RESOURCE_UPDATED`, `RESOURCE_DELETED`
- `AFTER_APPLY`, `AFTER_DESTROY`

#### AuditLogger

Logs all events for compliance and debugging.

**Subscription:**
- `subscribe_all()` - Captures complete event history

### Custom Consumers

Plugins and extensions can subscribe to events:

```python
from infrafoundry.core.events import EventManager, EventType, Event

class CustomIntegration:
    def __init__(self, event_manager: EventManager):
        event_manager.subscribe(EventType.AFTER_APPLY, self.on_apply_complete)
        event_manager.subscribe(EventType.DRIFT_DETECTED, self.on_drift)

    def on_apply_complete(self, event: Event) -> None:
        # Custom logic after successful apply
        pass

    def on_drift(self, event: Event) -> None:
        # Custom drift handling
        pass
```

## Event Data Conventions

Each event type includes specific data fields:

### Lifecycle Events

```python
{
    "provider_name": "proxmox-homelab",
    "runner": "terraform",
    "deployment_id": "abc123",
    "duration_seconds": 45.2
}
```

### Resource Events

```python
{
    "resource_type": "vm",
    "resource_name": "web-01",
    "resource_id": "vm-101",
    "provider": "proxmox"
}
```

### Drift Events

```python
{
    "provider": "opnsense-gateway",
    "has_changes": true,
    "resources_added": 0,
    "resources_changed": 2,
    "resources_destroyed": 0,
    "summary": "2 resources drifted"
}
```

### Policy Events

```python
{
    "policy_name": "strict-naming",
    "violation_count": 3,
    "resources": ["vm-01", "vm-02", "vm-03"],
    "severity": "ERROR"
}
```

## Design Patterns

### Synchronous Execution

Events are dispatched synchronously to maintain predictable execution order:

```python
# Events execute in order, blocking until handlers complete
emit_event(EventType.BEFORE_APPLY, env="prod", data={...})
# ... apply operation ...
emit_event(EventType.AFTER_APPLY, env="prod", data={...})
```

**Benefits:**
- Predictable execution order
- Simple debugging and tracing
- No race conditions
- Easy testing

**Trade-offs:**
- Slow handlers block emission
- Not suitable for long-running operations

**Best Practice:** Keep handlers lightweight; offload heavy work to async tasks or queues.

### Error Handling

Event handlers should not raise exceptions:

```python
def safe_handler(event: Event) -> None:
    try:
        # Handler logic
        pass
    except Exception as e:
        logger.error(f"Handler failed: {e}")
        # Don't re-raise; don't block other handlers
```

### Event Bubbling

Events bubble up through architectural layers:

```
Runner (emit) → Provider (emit) → Orchestrator (emit) → EventManager
```

Each layer can emit its own events, enriching context as it goes.

## Integration Points

### CLI Commands

Commands emit events at key points:

```python
# infra apply command
event_manager.emit_event(EventType.BEFORE_APPLY, environment=env, data={...})
orchestrator.apply(environment=env)
event_manager.emit_event(EventType.AFTER_APPLY, environment=env, data={...})
```

### Runners

Runners emit resource-level events:

```python
class TerraformRunner:
    def apply(self, provider, auto_approve=True):
        # Parse terraform output
        for resource in created_resources:
            self.event_manager.emit_event(
                EventType.RESOURCE_CREATED,
                environment=provider.environment,
                data={"resource_name": resource.name}
            )
```

### Providers

Providers emit validation and configuration events:

```python
class ProxmoxProvider:
    def validate(self):
        self.event_manager.emit_event(
            EventType.VALIDATION_STARTED,
            environment=self.environment,
            data={"provider": self.name}
        )
```

## Testing

Event system supports testing via subscription inspection:

```python
def test_apply_emits_events():
    events_received = []

    def capture(event: Event):
        events_received.append(event)

    event_manager.subscribe_all(capture)
    orchestrator.apply(environment="test")

    assert any(e.event_type == EventType.BEFORE_APPLY for e in events_received)
    assert any(e.event_type == EventType.AFTER_APPLY for e in events_received)
```

## Performance Considerations

### Event Volume

Typical event counts per operation:

- **Plan**: 5-10 events (lifecycle + validation)
- **Apply**: 10-50 events (lifecycle + resources)
- **Drift Detection**: 3-15 events (detection + summary)

### Handler Performance

Recommended handler execution times:

- **Logging**: < 1ms
- **State updates**: < 10ms
- **Notifications**: < 100ms
- **Heavy operations**: Offload to background tasks

## Security Considerations

### Event Data Sanitization

Never include secrets in event data:

```python
# ❌ Bad
emit_event(EventType.RESOURCE_CREATED, data={
    "password": "secret123"  # Don't do this!
})

# ✅ Good
emit_event(EventType.RESOURCE_CREATED, data={
    "resource_name": "database",
    "has_credentials": True  # Indicate presence without exposing
})
```

### Handler Trust

All handlers run in-process with full access. Only register trusted handlers.

## Future Enhancements

Potential improvements:

1. **Async Events**: Support for asynchronous event processing
2. **Event Filtering**: More granular subscription filters
3. **Event Replay**: Replay historical events for debugging
4. **Event Persistence**: Durable event log for audit compliance
5. **Priority Handlers**: Execute critical handlers first
6. **Event Batching**: Group related events for efficiency

## Related Documentation

- [Event System Guide](../development/event-system.md) - Developer guide for using events
- [Orchestrator Architecture](orchestrator-architecture.md) - How orchestrator uses events
- [Notifications Configuration](../configuration/notifications.md) - Configuring event-driven notifications
- [State Management](state-management.md) - How state manager consumes events

## See Also

- [Design Principles](principles.md) - Guiding principles for event system design
- [Architectural Patterns](architectural-patterns.md) - Pub-sub and observer patterns

---

**Last Updated:** 2025-12-29
