"""
Interception layer (§03, §12): wraps the tool-execution function so
every call is scored before it executes. This is the Phase 1 slice
only — per-call schema check, no trajectory store, no circuit breaker,
no flag/approve tiers yet (those require the session store and tier
engine, later work per §03's architecture split).

Design decision, stated explicitly: a genuine schema violation BLOCKS
the call regardless of the tool's risk tier. §07/§13's fail-open vs.
fail-closed distinction governs what happens when the GUARDRAIL ITSELF
is unavailable (circuit breaker tripped) — not what happens when the
guardrail ran fine and found a real violation. A malformed call is
blocked outright; there is no tier where a detected schema violation
is allowed through.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.detectors import SchemaRegistry, SchemaViolation, check_schema
from simulacrum.interception.fake_tools import FakeToolRegistry


class BlockedCallError(RuntimeError):
    """Raised when the interception layer blocks a call due to a
    detected schema violation."""


@dataclass(frozen=True)
class InterceptionResult:
    tool_name: str
    allowed: bool
    violation: SchemaViolation
    tool_result: dict[str, str] | None


def intercept_and_call(
    *,
    tool_registry: FakeToolRegistry,
    schema_registry: SchemaRegistry,
    tool_name: str,
    params: dict[str, str],
) -> InterceptionResult:
    """
    The single entrypoint every tool call should go through. Checks
    schema conformance BEFORE calling the underlying tool — a blocked
    call never reaches FakeToolRegistry.call(), never executes.
    """
    violation = check_schema(
        registry=schema_registry, tool_name=tool_name, params=params
    )
    if violation.is_violation:
        return InterceptionResult(
            tool_name=tool_name, allowed=False, violation=violation, tool_result=None
        )
    result = tool_registry.call(tool_name=tool_name, params=params)
    return InterceptionResult(
        tool_name=tool_name, allowed=True, violation=violation, tool_result=result
    )
