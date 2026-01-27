"""Pydantic models for lifecycle hooks."""

from pydantic import BaseModel, Field


class HookConfig(BaseModel):
    """Configuration for a single lifecycle hook.

    Hooks are user-defined scripts that run at specific points during
    infrastructure operations (plan, apply, destroy).

    Attributes:
        script: Path to script file, relative to environment directory
        description: Optional human-readable description of what the hook does
        env: Environment variables to pass to the script
        continue_on_error: If True, operation continues even if hook fails
        timeout: Maximum execution time in seconds (1-3600)
    """

    script: str
    description: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    continue_on_error: bool = False
    timeout: int = Field(default=300, ge=1, le=3600)


class HooksConfig(BaseModel):
    """Collection of hooks organized by lifecycle stage.

    Hooks can be defined at two levels:
    - Environment-level: In settings.yaml, runs for all operations
    - Resource-level: In resource configs, runs only for that resource

    Execution order:
        Environment before_X -> Resource before_X -> [Operation] ->
        Resource after_X -> Environment after_X

    Attributes:
        before_plan: Hooks to run before plan operation
        after_plan: Hooks to run after successful plan
        before_apply: Hooks to run before apply operation
        after_apply: Hooks to run after successful apply
        before_destroy: Hooks to run before destroy operation
        after_destroy: Hooks to run after successful destroy
    """

    before_plan: list[HookConfig] = Field(default_factory=list)
    after_plan: list[HookConfig] = Field(default_factory=list)
    before_apply: list[HookConfig] = Field(default_factory=list)
    after_apply: list[HookConfig] = Field(default_factory=list)
    before_destroy: list[HookConfig] = Field(default_factory=list)
    after_destroy: list[HookConfig] = Field(default_factory=list)


class HookResult(BaseModel):
    """Result of a hook execution.

    Attributes:
        script: Path to the executed script
        success: Whether the hook completed successfully
        exit_code: Process exit code
        stdout: Captured standard output
        stderr: Captured standard error
        duration_seconds: Execution time in seconds
        timed_out: Whether the hook was terminated due to timeout
        error_message: Human-readable error description if failed
    """

    script: str
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    error_message: str | None = None
