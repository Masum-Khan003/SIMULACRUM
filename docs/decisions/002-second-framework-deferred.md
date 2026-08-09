# Decision 002: second agent-framework integration deferred, not built

**Status:** Decided. Deferred indefinitely, not scoped into this project's delivered work.

## Context

§23's Phase 3 roadmap named "a second agent-framework integration for genuine framework-agnosticism proof" as stretch scope, explicitly "if time allows." After completing the three approved Phase 3 items (findings 019–021: multi-instance circuit breaker, authenticated ops-approver role, exportable investigation report), this was the one remaining named Phase 3 item.

## Real assessment

`intercept_and_call()` is already framework-agnostic **by construction**: a plain Python function with no framework-specific types in its signature, exercised through two genuinely independent real paths today — the sandboxed demo agent (`task_sim`) and the raw HTTP API (any external caller, any language, any framework). This structural design already makes the framework-agnostic claim credible without a second integration.

A second real integration (e.g., wrapping an actual LangChain agent loop around the interceptor) would strengthen that claim **empirically** rather than close a functional gap — unlike findings 019–021, which each resolved a real, named limitation (unshared breaker state, no independent approver, no persisted detector detail). This item is a demonstration/proof exercise, not a new question about detection quality or system correctness.

## Decision

**Deferred, not built.** Given the project's real state (Phases 0–2 complete, all three approved Phase 3 items delivered, 21 documented findings, 331 passing tests), this item's marginal value is lower than completing the README with the substantial real material now available, and it was always the blueprint's softest commitment ("if time allows," not a stated gap like the other three Phase 3 items).

## Revisit conditions, stated explicitly (not a silent, permanent drop)

Revisit if:
- A real, specific need arises to demonstrate compatibility with a named third-party framework (e.g., a user or reviewer explicitly asks "does this work with LangChain")
- The project moves toward broader production adoption where empirical, not just structural, proof of framework-agnosticism becomes load-bearing
