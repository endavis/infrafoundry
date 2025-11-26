# Infrafoundry Codebase Refactoring Suggestions (Run 2)

This document outlines potential refactoring and improvement areas identified during an automated scan of the codebase. The focus is on architectural patterns, decoupling, and maintainability.

## 1. High Priority: Decouple Runners from Orchestration Logic

**Observation:** The core orchestration workflows in `src/infrafoundry/core/orchestrator_workflows.py` directly import and instantiate specific runners like `TerraformRunner` and `AnsibleRunner`. This completely bypasses the existing `RunnerRegistry` (`src/infrafoundry/core/runners/runner_registry.py`).

**Problem:** This creates tight coupling between the orchestration logic and the specific runner implementations. It makes the system rigid and difficult to extend with new runner types (e.g., for different cloud providers or deployment tools) without modifying the core workflow files.

**Suggestion:** Refactor the `PlanOrchestrator`, `ApplyOrchestrator`, `DestroyOrchestrator`, and other workflow classes to use the `RunnerRegistry` to dynamically create and manage runner instances. The orchestrator should be runner-agnostic and work with any runner that conforms to the `BaseRunner` interface.

**Relevant Files:**
- `src/infrafoundry/core/orchestrator_workflows.py` (to be changed)
- `src/infrafoundry/core/runners/runner_registry.py` (to be used)
- `src/infrafoundry/core/runners/base_runner.py` (the contract)

## 2. Decouple UI from Core Logic

**Observation:** The `ApplyOrchestrator` in `src/infrafoundry/core/orchestrator_workflows.py` contains a call to `input()` to prompt the user for confirmation before applying changes.

**Problem:** Mixing user interface concerns (like console input/output) with core application logic violates the separation of concerns principle. The core logic should be usable in different contexts (e.g., a non-interactive CI/CD pipeline, a future web UI) without modification.

**Suggestion:** Move the user interaction and confirmation logic out of the orchestrator and into the presentation layer, specifically the CLI command implementation in `src/infrafoundry/cli/commands/apply.py`. The core `ApplyOrchestrator` should simply execute the deployment plan it is given. The CLI can be responsible for getting the necessary user approval before invoking the orchestrator.

**Relevant Files:**
- `src/infrafoundry/core/orchestrator_workflows.py` (remove `input()`)
- `src/infrafoundry/cli/commands/apply.py` (add `input()` here)

## 3. Refactor Dependency Injection in Orchestrator

**Observation:** The `Orchestrator.__init__` method in `src/infrafoundry/core/orchestrator.py` uses a pattern of passing `lambda` functions to instantiate dependencies like `SettingsManager`, `CredentialLoader`, and `StateManager`.

**Problem:** While this provides a form of lazy initialization, it makes the constructor's signature complex and the dependency graph harder to understand and trace. It's an unconventional pattern for dependency injection in Python.

**Suggestion:** Refactor this to use a more standard dependency injection approach. This could involve:
- A dedicated Dependency Injection (DI) container.
- A factory pattern to construct the `Orchestrator` with its dependencies.
- Simply instantiating and passing the dependency objects directly if lazy loading is not a critical performance requirement.

**Relevant Files:**
- `src/infrafoundry/core/orchestrator.py`

## 4. Improve Exception Handling

**Observation:** There are several broad `except Exception` blocks throughout the codebase.

**Problem:** Catching the generic `Exception` class can hide bugs and make debugging difficult because it suppresses unexpected errors that should be investigated. It can also lead to incorrect handling of system-exiting exceptions like `KeyboardInterrupt` or `SystemExit`.

**Suggestion:** Review all `except Exception` blocks and replace them with more specific exception types where possible. If a broad catch is truly necessary, it should at least log the full exception traceback for later analysis.

**Example Location (to be confirmed with a code search):**
- Expected to be found in workflow and runner execution logic. A search for `except Exception:` would be needed to identify all instances.
