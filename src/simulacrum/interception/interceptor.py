"""
Interception layer (§03, §12): wraps the tool-execution function so
every call is scored before it executes. This is the Phase 1 slice:
per-call schema + param-vs-task divergence checks, no trajectory
store, no circuit breaker, no flag/approve tiers yet (those require
the session store and tier engine, later work per §03's architecture
split — tracked in docs/BACKLOG.md).

Design decision, stated explicitly: a genuine schema violation OR
divergence flag BLOCKS the call regardless of the tool's risk tier.
§07/§13's fail-open vs. fail-closed distinction governs what happens
when the GUARDRAIL ITSELF is unavailable (circuit breaker tripped) —
not what happens when the guardrail ran fine and found a real
violation. Either detector flagging is sufficient to block.

Both detectors run on every call (schema first — cheaper, no embedding
call — then divergence). Result reports BOTH findings independently,
not a collapsed pass/fail, since which detector fired matters for
explainability (§14).
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.attribution import TaskRepresentation
from simulacrum.detectors import (
    ParamDivergenceResult,
    SchemaRegistry,
    SchemaViolation,
    UnregisteredSchemaError,
    check_param_divergence,
    check_schema,
)
from simulacrum.interception.fake_tools import FakeToolRegistry


class BlockedCallError(RuntimeError):
    """Raised when the interception layer blocks a call due to a
    detected schema violation or divergence flag."""


@dataclass(frozen=True)
class InterceptionResult:
    tool_name: str
    allowed: bool
    schema_violation: SchemaViolation | None
    divergence_result: ParamDivergenceResult | None
    tool_result: dict[str, str] | None


def intercept_and_call(
    *,
    tool_registry: FakeToolRegistry,
    schema_registry: SchemaRegistry,
    task_representation: TaskRepresentation,
    tool_name: str,
    params: dict[str, str],
) -> InterceptionResult:
    """
    The single entrypoint every tool call should go through. Runs
    schema conformance, then param-vs-task divergence, BEFORE calling
    the underlying tool — a blocked call never reaches
    FakeToolRegistry.call(), never executes.

    schema_violation is None if the tool has no registered schema
    (e.g. an attack-target tool outside any legitimate task template —
    see test_injection.py) rather than raising, since an unscorable-
    by-schema call should still be evaluated by divergence, not abort
    the whole interception path. Only UnregisteredSchemaError is
    caught here — any OTHER exception from check_schema is a real bug
    and must propagate, not be silently swallowed.
    """
    schema_violation: SchemaViolation | None
    try:
        schema_violation = check_schema(
            registry=schema_registry, tool_name=tool_name, params=params
        )
    except UnregisteredSchemaError:
        schema_violation = None

    divergence_result = check_param_divergence(
        task_representation=task_representation, tool_name=tool_name, params=params
    )

    schema_flagged = schema_violation is not None and schema_violation.is_violation
    divergence_flagged = divergence_result.is_divergent
    allowed = not (schema_flagged or divergence_flagged)

    tool_result = None
    if allowed:
        tool_result = tool_registry.call(tool_name=tool_name, params=params)

    return InterceptionResult(
        tool_name=tool_name,
        allowed=allowed,
        schema_violation=schema_violation,
        divergence_result=divergence_result,
        tool_result=tool_result,
    )
