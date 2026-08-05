"""
Interception layer (§03, §12): wraps the tool-execution function so
every call is scored before it executes. Four detectors run on every
call: schema conformance, param-vs-task divergence, permission
escalation, and tool-loop-rate (retry-vs-evasion split). No trajectory
model, no circuit breaker, no flag/approve tiers yet.

Design decisions, stated explicitly:
  - Any flagging detector BLOCKS the call, regardless of risk tier.
  - Loop-rate checked against PRIOR outcome history; this call's own
    outcome logged AFTER the decision via append_attempt.
  - Permission-escalation footprint includes the CURRENT call.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.attribution import TaskRepresentation
from simulacrum.detectors import (
    LoopRateResult,
    ParamDivergenceResult,
    PermissionEscalationResult,
    SchemaRegistry,
    SchemaViolation,
    UnregisteredSchemaError,
    check_param_divergence,
    check_permission_escalation,
    check_schema,
    check_tool_loop_rate,
)
from simulacrum.interception.fake_tools import FakeToolRegistry
from simulacrum.session import CallOutcome, SessionStore
from simulacrum.task_sim import TaskType, ToolCall


class BlockedCallError(RuntimeError):
    """Raised when the interception layer blocks a call."""


@dataclass(frozen=True)
class InterceptionResult:
    tool_name: str
    allowed: bool
    schema_violation: SchemaViolation | None
    divergence_result: ParamDivergenceResult | None
    escalation_result: PermissionEscalationResult
    loop_rate_result: LoopRateResult
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

    loop_rate_result = check_tool_loop_rate(
        session_store=session_store, session_id=session_id, tool_name=tool_name, params=params
    )

    schema_flagged = schema_violation is not None and schema_violation.is_violation
    divergence_flagged = divergence_result.is_divergent
    escalation_flagged = escalation_result.is_escalated
    loop_rate_flagged = loop_rate_result.is_flagged
    allowed = not (schema_flagged or divergence_flagged or escalation_flagged or loop_rate_flagged)

    call_record = ToolCall(tool_name=tool_name, params=params, turn_index=turn_index)
    outcome = CallOutcome.ALLOWED if allowed else CallOutcome.BLOCKED
    session_store.append_attempt(session_id=session_id, call=call_record, outcome=outcome)

    tool_result = None
    if allowed:
        tool_result = tool_registry.call(tool_name=tool_name, params=params)

    return InterceptionResult(
        tool_name=tool_name,
        allowed=allowed,
        schema_violation=schema_violation,
        divergence_result=divergence_result,
        escalation_result=escalation_result,
        loop_rate_result=loop_rate_result,
        tool_result=tool_result,
    )
