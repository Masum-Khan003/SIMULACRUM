"""
Interception layer (§03, §12): wraps the tool-execution function so
every call is scored before it executes. Per-call checks (schema,
divergence) plus session-level checks (permission escalation) now
run together — every call passes through both timescales, matching
§04's fast-path/slow-path split. No trajectory model, no circuit
breaker, no flag/approve tiers yet (§03 architecture split, tracked
in docs/BACKLOG.md).

Design decisions, stated explicitly:
  - Any of schema violation, divergence flag, or permission escalation
    BLOCKS the call, regardless of tool risk tier. §07/§13's fail-open/
    closed distinction governs GUARDRAIL UNAVAILABILITY, not what to
    do with an actual finding.
  - The session store logs EVERY call attempt (allowed or blocked) —
    a blocked call still happened and is part of the session's real
    history/footprint for audit and future trajectory analysis, even
    though its underlying tool never executed.
  - Permission-escalation check includes the CURRENT call's tool name
    in the footprint being evaluated (not just prior calls) — so the
    very call that introduces an out-of-baseline tool is itself
    caught, not just calls after it.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.attribution import TaskRepresentation
from simulacrum.detectors import (
    ParamDivergenceResult,
    PermissionEscalationResult,
    SchemaRegistry,
    SchemaViolation,
    UnregisteredSchemaError,
    check_param_divergence,
    check_permission_escalation,
    check_schema,
)
from simulacrum.interception.fake_tools import FakeToolRegistry
from simulacrum.interception.session_store import SessionStore
from simulacrum.task_sim import TaskType, ToolCall


class BlockedCallError(RuntimeError):
    """Raised when the interception layer blocks a call due to a
    detected schema violation, divergence flag, or permission
    escalation."""


@dataclass(frozen=True)
class InterceptionResult:
    tool_name: str
    allowed: bool
    schema_violation: SchemaViolation | None
    divergence_result: ParamDivergenceResult | None
    escalation_result: PermissionEscalationResult
    tool_result: dict[str, str] | None


def intercept_and_call(
    *,
    tool_registry: FakeToolRegistry,
    schema_registry: SchemaRegistry,
    session_store: SessionStore,
    task_representation: TaskRepresentation,
    task_type: TaskType,
    session_id: str,
    tool_name: str,
    params: dict[str, str],
    turn_index: int,
) -> InterceptionResult:
    """
    The single entrypoint every tool call should go through. Runs
    schema conformance, param-vs-task divergence, and permission
    escalation (against the session footprint INCLUDING this call)
    BEFORE calling the underlying tool. Logs the call to the session
    store regardless of the outcome — a blocked attempt is still part
    of the session's real history.
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

    prior_footprint = session_store.get_tool_footprint(session_id=session_id)
    footprint_including_this_call = prior_footprint | {tool_name}
    escalation_result = check_permission_escalation(
        task_type=task_type, session_footprint=footprint_including_this_call
    )

    schema_flagged = schema_violation is not None and schema_violation.is_violation
    divergence_flagged = divergence_result.is_divergent
    escalation_flagged = escalation_result.is_escalated
    allowed = not (schema_flagged or divergence_flagged or escalation_flagged)

    call_record = ToolCall(tool_name=tool_name, params=params, turn_index=turn_index)
    session_store.append_call(session_id=session_id, call=call_record)

    tool_result = None
    if allowed:
        tool_result = tool_registry.call(tool_name=tool_name, params=params)

    return InterceptionResult(
        tool_name=tool_name,
        allowed=allowed,
        schema_violation=schema_violation,
        divergence_result=divergence_result,
        escalation_result=escalation_result,
        tool_result=tool_result,
    )
