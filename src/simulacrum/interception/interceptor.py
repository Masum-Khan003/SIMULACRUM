"""
Interception layer (§03, §12): wraps the tool-execution function so
every call is scored before it executes. Five detectors run through a
circuit breaker as ONE scoring unit (§12 scope note: coarse breaker,
not per-detector — see circuit_breaker.py docstring). If scoring
fails and the breaker is open, fallback is decided PER TOOL RISK TIER
(§07) — the core architectural departure from Palimpsest's uniform
fail-open breaker:
  - READ_ONLY / REVERSIBLE_WRITE -> fail OPEN (proceed unscored)
  - IRREVERSIBLE_LOW_VALUE / IRREVERSIBLE_HIGH_VALUE -> fail CLOSED (block)
  - tool not found in tier_registry at all -> fail CLOSED (conservative
    default; should not happen given §07's registration enforcement,
    but code must not assume it)

A guardrail-unavailable fallback is a DIFFERENT outcome from a
detected violation — logged loudly and distinctly (guardrail_bypassed
field), never silently indistinguishable from "scoring ran, found
nothing" (§12).
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.attribution import TaskRepresentation
from simulacrum.detectors import (
    ExfiltrationResult,
    LoopRateResult,
    ParamDivergenceResult,
    PermissionEscalationResult,
    SchemaRegistry,
    SchemaViolation,
    UnregisteredSchemaError,
    check_exfiltration,
    check_param_divergence,
    check_permission_escalation,
    check_schema,
    check_tool_loop_rate,
)
from simulacrum.interception.circuit_breaker import CircuitBreaker, CircuitOpenError
from simulacrum.interception.fake_tools import FakeToolRegistry
from simulacrum.risk_tiers import FailPolicy, ToolRegistry, UnregisteredToolError
from simulacrum.session import CallOutcome, SessionStore
from simulacrum.task_sim import TaskType, ToolCall


class BlockedCallError(RuntimeError):
    """Raised when the interception layer blocks a call."""


@dataclass(frozen=True)
class ScoringBundle:
    schema_violation: SchemaViolation | None
    divergence_result: ParamDivergenceResult
    escalation_result: PermissionEscalationResult
    loop_rate_result: LoopRateResult
    exfiltration_result: ExfiltrationResult


@dataclass(frozen=True)
class InterceptionResult:
    tool_name: str
    allowed: bool
    schema_violation: SchemaViolation | None
    divergence_result: ParamDivergenceResult | None
    escalation_result: PermissionEscalationResult | None
    loop_rate_result: LoopRateResult | None
    exfiltration_result: ExfiltrationResult | None
    tool_result: dict[str, str] | None
    guardrail_bypassed: bool = False
    guardrail_bypass_reason: str | None = None


def _run_scoring(
    *,
    schema_registry: SchemaRegistry,
    session_store: SessionStore,
    task_representation: TaskRepresentation,
    task_type: TaskType,
    session_id: str,
    tool_name: str,
    params: dict[str, str],
) -> ScoringBundle:
    """The full scoring path, run as ONE unit inside the breaker."""
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
    escalation_result = check_permission_escalation(
        task_type=task_type, session_footprint=prior_footprint | {tool_name}
    )
    loop_rate_result = check_tool_loop_rate(
        session_store=session_store, session_id=session_id, tool_name=tool_name, params=params
    )
    exfiltration_result = check_exfiltration(
        session_store=session_store, session_id=session_id, tool_name=tool_name, params=params
    )
    return ScoringBundle(
        schema_violation=schema_violation,
        divergence_result=divergence_result,
        escalation_result=escalation_result,
        loop_rate_result=loop_rate_result,
        exfiltration_result=exfiltration_result,
    )


def _fail_policy_for(*, tier_registry: ToolRegistry, tool_name: str) -> FailPolicy:
    try:
        return tier_registry.get(tool_name=tool_name).fail_policy
    except UnregisteredToolError:
        # Conservative default — should not happen given §07's
        # registration enforcement, but never assume.
        return FailPolicy.FAIL_CLOSED


def intercept_and_call(
    *,
    tool_registry: FakeToolRegistry,
    tier_registry: ToolRegistry,
    schema_registry: SchemaRegistry,
    session_store: SessionStore,
    circuit_breaker: CircuitBreaker,
    task_representation: TaskRepresentation,
    task_type: TaskType,
    session_id: str,
    tool_name: str,
    params: dict[str, str],
    turn_index: int,
) -> InterceptionResult:
    call_record = ToolCall(tool_name=tool_name, params=params, turn_index=turn_index)

    try:
        scoring = circuit_breaker.call(
            lambda: _run_scoring(
                schema_registry=schema_registry,
                session_store=session_store,
                task_representation=task_representation,
                task_type=task_type,
                session_id=session_id,
                tool_name=tool_name,
                params=params,
            )
        )
    except CircuitOpenError:
        fail_policy = _fail_policy_for(tier_registry=tier_registry, tool_name=tool_name)
        if fail_policy is FailPolicy.FAIL_OPEN:
            session_store.append_attempt(
                session_id=session_id, call=call_record, outcome=CallOutcome.ALLOWED
            )
            tool_result = tool_registry.call(tool_name=tool_name, params=params)
            return InterceptionResult(
                tool_name=tool_name,
                allowed=True,
                schema_violation=None,
                divergence_result=None,
                escalation_result=None,
                loop_rate_result=None,
                exfiltration_result=None,
                tool_result=tool_result,
                guardrail_bypassed=True,
                guardrail_bypass_reason="circuit_open_fail_open",
            )
        else:
            session_store.append_attempt(
                session_id=session_id, call=call_record, outcome=CallOutcome.BLOCKED
            )
            return InterceptionResult(
                tool_name=tool_name,
                allowed=False,
                schema_violation=None,
                divergence_result=None,
                escalation_result=None,
                loop_rate_result=None,
                exfiltration_result=None,
                tool_result=None,
                guardrail_bypassed=True,
                guardrail_bypass_reason="circuit_open_fail_closed",
            )

    schema_flagged = scoring.schema_violation is not None and scoring.schema_violation.is_violation
    allowed = not (
        schema_flagged
        or scoring.divergence_result.is_divergent
        or scoring.escalation_result.is_escalated
        or scoring.loop_rate_result.is_flagged
        or scoring.exfiltration_result.is_flagged
    )

    outcome = CallOutcome.ALLOWED if allowed else CallOutcome.BLOCKED
    session_store.append_attempt(session_id=session_id, call=call_record, outcome=outcome)

    tool_result = None
    if allowed:
        tool_result = tool_registry.call(tool_name=tool_name, params=params)

    return InterceptionResult(
        tool_name=tool_name,
        allowed=allowed,
        schema_violation=scoring.schema_violation,
        divergence_result=scoring.divergence_result,
        escalation_result=scoring.escalation_result,
        loop_rate_result=scoring.loop_rate_result,
        exfiltration_result=scoring.exfiltration_result,
        tool_result=tool_result,
        guardrail_bypassed=False,
    )
