"""
Interception layer (§03, §12, §13): wraps the tool-execution function.
Five detectors run through a circuit breaker as one scoring unit. The
result feeds §13's tiered response: ALLOW / FLAG / REQUIRE_APPROVAL /
BLOCK, decided via decide_response_tier's detector-flag-count severity
proxy (see tier_engine/response_tier.py docstring for the honesty
caveat on that proxy).

REQUIRE_APPROVAL calls do NOT execute immediately — submitted to the
ApprovalQueue, tool_result stays None until a caller separately checks
the decided outcome and explicitly triggers execution (kept as a
distinct step from queue.decide() itself, so ApprovalQueue stays
dependency-free — see chat discussion / commit log).

Circuit-breaker-open fallback (guardrail unavailable) is a SEPARATE
path from this whole tiered-response system — §07's per-tier fail-
open/closed still governs when scoring itself can't run at all.
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
from simulacrum.tier_engine import ApprovalQueue, ResponseTier, decide_response_tier


class BlockedCallError(RuntimeError):
    """Raised when the interception layer blocks a call."""


@dataclass(frozen=True)
class ScoringBundle:
    schema_violation: SchemaViolation | None
    divergence_result: ParamDivergenceResult
    escalation_result: PermissionEscalationResult
    loop_rate_result: LoopRateResult
    exfiltration_result: ExfiltrationResult

    @property
    def flagged_detector_count(self) -> int:
        count = 0
        if self.schema_violation is not None and self.schema_violation.is_violation:
            count += 1
        if self.divergence_result.is_divergent:
            count += 1
        if self.escalation_result.is_escalated:
            count += 1
        if self.loop_rate_result.is_flagged:
            count += 1
        if self.exfiltration_result.is_flagged:
            count += 1
        return count


@dataclass(frozen=True)
class InterceptionResult:
    tool_name: str
    response_tier: ResponseTier
    schema_violation: SchemaViolation | None
    divergence_result: ParamDivergenceResult | None
    escalation_result: PermissionEscalationResult | None
    loop_rate_result: LoopRateResult | None
    exfiltration_result: ExfiltrationResult | None
    tool_result: dict[str, str] | None
    approval_request_id: str | None = None
    guardrail_bypassed: bool = False
    guardrail_bypass_reason: str | None = None

    @property
    def allowed(self) -> bool:
        """Convenience: True only for ALLOW/FLAG (executed immediately).
        REQUIRE_APPROVAL and BLOCK are both 'not allowed yet/at all'."""
        return self.response_tier in (ResponseTier.ALLOW, ResponseTier.FLAG)


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
        return FailPolicy.FAIL_CLOSED


def intercept_and_call(
    *,
    tool_registry: FakeToolRegistry,
    tier_registry: ToolRegistry,
    schema_registry: SchemaRegistry,
    session_store: SessionStore,
    circuit_breaker: CircuitBreaker,
    approval_queue: ApprovalQueue,
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
                response_tier=ResponseTier.ALLOW,
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
                response_tier=ResponseTier.BLOCK,
                schema_violation=None,
                divergence_result=None,
                escalation_result=None,
                loop_rate_result=None,
                exfiltration_result=None,
                tool_result=None,
                guardrail_bypassed=True,
                guardrail_bypass_reason="circuit_open_fail_closed",
            )

    # §07 guarantees every callable tool is registered with a tier —
    # FakeToolRegistry.call() itself would already have raised if not.
    # No defensive fallback needed here; a genuinely unregistered tool
    # is a configuration bug that should surface loudly, not be
    # silently papered over with an assumed conservative tier.
    tool_tier = tier_registry.get(tool_name=tool_name).tier
    response_tier = decide_response_tier(
        flagged_detector_count=scoring.flagged_detector_count, tool_tier=tool_tier
    )

    tool_result = None
    approval_request_id = None

    if response_tier is ResponseTier.BLOCK:
        session_store.append_attempt(
            session_id=session_id, call=call_record, outcome=CallOutcome.BLOCKED
        )
    elif response_tier is ResponseTier.REQUIRE_APPROVAL:
        request = approval_queue.submit(session_id=session_id, tool_name=tool_name, params=params)
        approval_request_id = request.request_id
        # Not yet ALLOWED or BLOCKED — pending a human decision. Logged
        # as BLOCKED for now (call did not execute) since SessionStore
        # doesn't yet have a PENDING call-outcome concept; tracked in
        # docs/BACKLOG.md as a real gap, not silently glossed over.
        session_store.append_attempt(
            session_id=session_id, call=call_record, outcome=CallOutcome.BLOCKED
        )
    else:  # ALLOW or FLAG — both execute immediately
        session_store.append_attempt(
            session_id=session_id, call=call_record, outcome=CallOutcome.ALLOWED
        )
        tool_result = tool_registry.call(tool_name=tool_name, params=params)

    return InterceptionResult(
        tool_name=tool_name,
        response_tier=response_tier,
        schema_violation=scoring.schema_violation,
        divergence_result=scoring.divergence_result,
        escalation_result=scoring.escalation_result,
        loop_rate_result=scoring.loop_rate_result,
        exfiltration_result=scoring.exfiltration_result,
        tool_result=tool_result,
        approval_request_id=approval_request_id,
        guardrail_bypassed=False,
    )

