---
title: "ADR-0019: Provider sub-validators share one validate(context) contract"
description: Every provider sub-validator implements validate(context) against a typed ValidationContext, enforced by mypy and a contract test
date: 2026-11-08
audience:
  - contributors
tags:
  - adr
---

# ADR-0019: Provider sub-validators share one validate(context) contract

## Status
Accepted

## Context
The provider sub-validators under `src/infrafoundry/providers/*/validators/` had no common contract. Their `validate()` methods took four different argument shapes, and 21 of them take live API data or derived lookups (an API client, cluster VM lists, cross-reference indexes) rather than only config resources. Each provider wired its validators in its own way, and a new validator had no pattern to follow. This was the one item of #196 left open (#1307). `ResourceValidator` in `core/validation_helpers` was meant as the shared piece, but no validator used it.

## Decision
Every provider sub-validator implements one concrete signature, `validate(self, context) -> None`:

- `core/validation.py` defines `ValidationContext`, a frozen, keyword-only dataclass carrying `resources`, and `run_validators(validators, context)`.
- `core/protocols.py` defines `SpecializedValidator[ContextT]`, a generic runtime-checkable Protocol with a `report` and `validate(context)`.
- Each provider defines typed context dataclasses (subclasses of `ValidationContext`) in `providers/<provider>/validators/context.py`. Inputs always available at call time are required fields; every old `validate` parameter becomes a field of the same type and default.
- Validators subclass `SpecializedValidator[<Context>]` explicitly and mark `validate` with `@override`, so mypy rejects a drifting signature at the class definition.
- Provider validators build the context and call `run_validators`; where API fetches are interleaved with validator calls, the context is built step by step with `dataclasses.replace`.
- A contract test (`tests/unit/providers/test_specialized_validator_contract.py`) discovers every class under `providers/*/validators/` and enforces the contract, so new validators are covered automatically.
- `ResourceValidator` and `BaseProviderValidator.validate_resource_exists` were unused and are removed. `BaseProviderValidator` stays; `BaseAPIValidator` wraps it.

Validator behaviour does not change: bodies only rebind locals from the context.

## Rationale
Validators differ in what they validate, not only in argument shape, so a single concrete signature needs a context object. A typed context per provider keeps each validator's inputs checked by mypy, and a contravariant generic Protocol lets `run_validators` accept a mix of base-context and specialised-context validators.

Alternatives rejected:

- **One generic context with optional fields for every provider.** Validators would need `None` checks for inputs that are always present, and mypy could not tell a validator what it is given.
- **A varargs/keyword protocol (`validate(*args, **kwargs)`).** It gives no type checking of the inputs and defeats the point of a contract.
- **Adopting `ResourceValidator` as the contract.** It validates a single reference, takes no live data, and no validator used it.

## Consequences
- Positive: one pattern for new validators, enforced by mypy and a test; wiring is uniform.
- Positive: tests that call `validate` build a typed context instead of passing positional arguments.
- Negative: existing tests changed at their call sites, and mock assertions on how `validate` was called changed shape.
- Negative: removing `ResourceValidator` is a breaking change to a public name exported from `core.validation_helpers`.
- OPNsense uses one context with a field per input; validators read only the fields they need.

## Related
- Issues: #1307, #196
- ADR-0010: Protocol-Based Runner Interfaces
- Documentation: [Validator Architecture](../development/implementing-providers.md#validator-architecture)
