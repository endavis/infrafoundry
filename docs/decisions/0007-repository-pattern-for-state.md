# 1. Use Repository Pattern for State Management

**Date:** 2025-12-01
**Status:** Accepted

## Context
The state management system needs to handle complex CRUD operations for deployments, resources, and events. We need to support multiple backend databases (SQLite for local dev, PostgreSQL for production teams) and ensure that the core business logic is decoupled from specific database implementation details (SQLAlchemy sessions, queries).

## Decision
We will use the **Repository Pattern** to abstract data access logic.

- **`DeploymentRepository`**: Handles all deployment-related queries.
- **`ResourceRepository`**: Handles all resource state tracking queries.
- **`StateManager`**: Acts as the Unit of Work / Facade over these repositories.

## Consequences
**Positive:**
- **Testability:** Repositories can be easily mocked for unit tests without spinning up a real database.
- **Decoupling:** Business logic (Orchestrators) doesn't need to import SQLAlchemy models or know about session management.
- **Flexibility:** Switching ORMs or database backends in the future is confined to the repository layer.

**Negative:**
- **Boilerplate:** Requires writing wrapper methods for every query instead of using the ORM directly in business logic.

## Alternatives Considered
- **Active Record Pattern:** Rejected because it couples business logic tightly to the database schema.
- **Direct SQLAlchemy Usage:** Rejected because it makes unit testing difficult and leaks database concerns into the Orchestrator layer.
