# Event System Guide

InfraFoundry includes a lightweight, synchronous event system that allows components to communicate without tight coupling. This system is primarily used for:
- Notifications (sending Slack/Discord alerts on deployment status).
- Audit logging.
- Triggering side effects during the orchestration lifecycle.

## Core Concepts

The event system is implemented in `src/infrafoundry/core/events.py`.

### Event Types

Events are typed using the `EventType` enum. Available events include:

**Lifecycle Events:**
- `BEFORE_PLAN`, `AFTER_PLAN`, `PLAN_FAILED`
- `BEFORE_APPLY`, `AFTER_APPLY`, `APPLY_FAILED`
- `BEFORE_DESTROY`, `AFTER_DESTROY`, `DESTROY_FAILED`

**Resource Events:**
- `RESOURCE_PLANNED`
- `RESOURCE_CREATING`, `RESOURCE_CREATED`
- `RESOURCE_DELETING`, `RESOURCE_DELETED`

**Advanced Events:**
- `DRIFT_CHECK_STARTED`, `DRIFT_DETECTED`, `DRIFT_CHECK_COMPLETED`
- `POLICY_CHECK_STARTED`, `POLICY_VIOLATION`, `POLICY_CHECK_COMPLETED`

### Event Object

Handlers receive an `Event` object containing:
- `event_type`: The `EventType`.
- `environment`: The name of the environment (e.g., "dev").
- `data`: A dictionary containing context-specific data (e.g., `deployment_id`, `resource_name`, error details).
- `timestamp`: When the event occurred.

## Usage for Developers

### Subscribing to Events

If you are developing a plugin or extending the orchestrator, you can subscribe to events using the global `EventManager`.

```python
from infrafoundry.core.events import Event, EventType, EventManager

def on_apply_complete(event: Event):
    deploy_id = event.data.get("deployment_id")
    print(f"Deployment {deploy_id} finished in {event.environment}!")

# Get the event manager (usually passed into your component)
event_manager = EventManager()

# Subscribe to a specific event
event_manager.subscribe(EventType.AFTER_APPLY, on_apply_complete)

# Subscribe to ALL events (useful for logging)
event_manager.subscribe_all(lambda e: print(f"Event: {e.event_type}"))
```

### Emitting Events

To emit an event from your component:

```python
event_manager.emit_event(
    event_type=EventType.RESOURCE_CREATED,
    environment="prod",
    data={
        "resource_name": "web-server-01",
        "provider": "proxmox",
        "ip": "10.0.0.5"
    }
)
```

## Notification Integration

The `NotificationManager` (`src/infrafoundry/core/notifications/`) subscribes to all events and forwards them to configured channels (e.g., Webhooks, Slack) based on `notifications.yaml`.

This allows users to receive real-time updates on their deployments without modifying the core orchestration code.
