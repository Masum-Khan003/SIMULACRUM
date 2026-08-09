"""
Interception layer (§03, §12, §13, §18): wraps the tool-execution
function. SIX detectors run through a circuit breaker as one scoring
unit: schema, param-vs-task divergence, permission escalation,
loop-rate (retry-vs-evasion split), exfiltration, and content-pattern
(finding 007's fix — closes the real, complete blind spot where an
in-baseline tool with camouflaged content evaded all five prior
detectors). Prometheus metrics recorded for every decision (§18),
same instrumentation as the original observability-wiring commit
(6951b2b) — restored here after being accidentally dropped during
this file's content-pattern-detector rewrite and caught by
test_observability.py's real-value assertions (exactly the discipline
§18 exists to enforce).

Design decisions, stated explicitly:
  - Any flagging detector BLOCKS/escalates the call, regardless of
    risk tier — §07/§13's fail-open/closed distinction governs
    GUARDRAIL UNAVAILABILITY, not what to do with an actual finding.
  - content_pattern_detector is REQUIRED (no default) — same "no
    silent gaps" discipline as every other detector.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.attribution import TaskRepresentation
from simulacrum.detectors import (
    ContentPatternDetector,
    ContentPatternResult,
    ExfiltrationResult,
    LoopRateResult,
    ParamDivergenceResult,
    PermissionEscalationResult,
    SchemaRegistry,
    SchemaViolation,
    UnregisteredSchemaError,
    FAKE_DIVERGENCE_THRESHOLD,
    check_exfiltration,
    check_param_divergence,
    check_permission_escalation,
    check_schema,
    check_tool_loop_rate,
)
from simulacrum.interception.circuit_breaker import CircuitBreaker, CircuitOpenError
from simulacrum.interception.redis_circuit_breaker import CircuitBreakerProtocol
from simulacrum.interception.fake_tools import FakeToolRegistry
from simulacrum.observability import (
    record_action,
    record_circuit_breaker_state,
    record_circuit_breaker_trip,
    record_detector_flag,
)
from simulacrum.risk_tiers import FailPolicy, ToolRegistry, UnregisteredToolError
from simulacrum.session import CallOutcome, SessionStore
from simulacrum.task_sim import TaskType, ToolCall
from simulacrum.tier_engine import ApprovalQueue, ResponseTier, decide_response_tier

BREAKER_NAME = "detector_scoring"


class BlockedCallError(RuntimeError):
    """Raised when the interception layer blocks a call."""


def _scoring_to_dict(scoring: "ScoringBundle") -> dict:
    """
    Real, Phase 3 addition (finding 021): converts a real ScoringBundle
    into a plain, JSON-serializable dict for persistence in
    CallAttempt.scoring_detail -- closes §18's SIEM-export gap and
    feeds the investigation report. Deliberately plain data, not
    detector dataclass objects, matching ExplanationContext's own
    "just data" principle.
    """
    return {
        "schema_violation": (
            {
                "missing_params": sorted(scoring.schema_violation.missing_params),
                "unexpected_params": sorted(scoring.schema_violation.unexpected_params),
                "is_violation": scoring.schema_violation.is_violation,
            }
            if scoring.schema_violation is not None
            else None
        ),
        "divergence": {
            "similarity": scoring.divergence_result.similarity,
            "is_divergent": scoring.divergence_result.is_divergent,
        },
        "escalation": {
            "escalated_tools": sorted(scoring.escalation_result.escalated_tools),
            "is_escalated": scoring.escalation_result.is_escalated,
        },
        "loop_rate": {
            "same_tool_attempt_count": scoring.loop_rate_result.same_tool_attempt_count,
            "is_rate_exceeded": scoring.loop_rate_result.is_rate_exceeded,
            "is_evasion_retry": scoring.loop_rate_result.is_evasion_retry,
            "is_benign_retry": scoring.loop_rate_result.is_benign_retry,
        },
        "exfiltration": {
            "outbound_call_count": scoring.exfiltration_result.outbound_call_count,
            "is_frequency_exceeded": scoring.exfiltration_result.is_frequency_exceeded,
            "is_content_anomalous": scoring.exfiltration_result.is_content_anomalous,
            "anomalous_params": sorted(scoring.exfiltration_result.anomalous_params),
        },
        "content_pattern": {
            "is_suspicious": scoring.content_pattern_result.is_suspicious,
            "reasoning": scoring.content_pattern_result.reasoning,
            "matched_patterns": list(scoring.content_pattern_result.matched_patterns),
            "confidence": scoring.content_pattern_result.confidence,
        },
        "flagged_detector_count": scoring.flagged_detector_count,
    }


@dataclass(frozen=True)
class ScoringBundle:
    schema_violation: SchemaViolation | None
    divergence_result: ParamDivergenceResult
    escalation_result: PermissionEscalationResult
    loop_rate_result: LoopRateResult
    exfiltration_result: ExfiltrationResult
    content_pattern_result: ContentPatternResult

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
        if self.content_pattern_result.is_suspicious:
            count += 1
        return count

    def record_flag_metrics(self) -> None:
        if self.schema_violation is not None and self.schema_violation.is_violation:
            record_detector_flag(detector_name="schema")
        if self.divergence_result.is_divergent:
            record_detector_flag(detector_name="divergence")
        if self.escalation_result.is_escalated:
            record_detector_flag(detector_name="permission_escalation")
        if self.loop_rate_result.is_flagged:
            record_detector_flag(detector_name="loop_rate")
        if self.exfiltration_result.is_flagged:
            record_detector_flag(detector_name="exfiltration")
        if self.content_pattern_result.is_suspicious:
            record_detector_flag(detector_name="content_pattern")


@dataclass(frozen=True)
class InterceptionResult:
    tool_name: str
    response_tier: ResponseTier
    schema_violation: SchemaViolation | None
    divergence_result: ParamDivergenceResult | None
    escalation_result: PermissionEscalationResult | None
    loop_rate_result: LoopRateResult | None
    exfiltration_result: ExfiltrationResult | None
    content_pattern_result: ContentPatternResult | None
    tool_result: dict[str, str] | None
    approval_request_id: str | None = None
    guardrail_bypassed: bool = False
    guardrail_bypass_reason: str | None = None
    shadow_mode_active: bool = False

    @property
    def allowed(self) -> bool:
        if self.shadow_mode_active:
            return True
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
    divergence_threshold: float,
    content_pattern_detector: ContentPatternDetector,
) -> ScoringBundle:
    schema_violation: SchemaViolation | None
    try:
        schema_violation = check_schema(
            registry=schema_registry, tool_name=tool_name, params=params
        )
    except UnregisteredSchemaError:
        schema_violation = None

    divergence_result = check_param_divergence(
        task_representation=task_representation, tool_name=tool_name, params=params,
        threshold=divergence_threshold,
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
    content_pattern_result = content_pattern_detector.check_content(
        tool_name=tool_name, params=params
    )
    return ScoringBundle(
        schema_violation=schema_violation,
        divergence_result=divergence_result,
        escalation_result=escalation_result,
        loop_rate_result=loop_rate_result,
        exfiltration_result=exfiltration_result,
        content_pattern_result=content_pattern_result,
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
    circuit_breaker: CircuitBreakerProtocol,  # real, structural interface --
    # CircuitBreaker (in-memory, single-instance) and RedisCircuitBreaker
    # (multi-instance, Phase 3 §23) are both genuine drop-ins, same
    # discipline as SessionStore's protocol/InMemory/Redis split.
    approval_queue: ApprovalQueue,
    content_pattern_detector: ContentPatternDetector,
    task_representation: TaskRepresentation,
    task_type: TaskType,
    session_id: str,
    tool_name: str,
    params: dict[str, str],
    turn_index: int,
    divergence_threshold: float = FAKE_DIVERGENCE_THRESHOLD,
    shadow_mode: bool = False,
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
                divergence_threshold=divergence_threshold,
                content_pattern_detector=content_pattern_detector,
            )
        )
    except CircuitOpenError:
        record_circuit_breaker_state(breaker_name=BREAKER_NAME, is_open=True)
        fail_policy = _fail_policy_for(tier_registry=tier_registry, tool_name=tool_name)
        if fail_policy is FailPolicy.FAIL_OPEN:
            session_store.append_attempt(
                session_id=session_id, call=call_record, outcome=CallOutcome.ALLOWED
            )
            tool_result = tool_registry.call(tool_name=tool_name, params=params)
            record_action(response_tier=ResponseTier.ALLOW.value)
            return InterceptionResult(
                tool_name=tool_name, response_tier=ResponseTier.ALLOW,
                schema_violation=None, divergence_result=None, escalation_result=None,
                loop_rate_result=None, exfiltration_result=None, content_pattern_result=None,
                tool_result=tool_result, guardrail_bypassed=True,
                guardrail_bypass_reason="circuit_open_fail_open",
            )
        else:
            session_store.append_attempt(
                session_id=session_id, call=call_record, outcome=CallOutcome.BLOCKED
            )
            record_action(response_tier=ResponseTier.BLOCK.value)
            return InterceptionResult(
                tool_name=tool_name, response_tier=ResponseTier.BLOCK,
                schema_violation=None, divergence_result=None, escalation_result=None,
                loop_rate_result=None, exfiltration_result=None, content_pattern_result=None,
                tool_result=None, guardrail_bypassed=True,
                guardrail_bypass_reason="circuit_open_fail_closed",
            )

    record_circuit_breaker_state(breaker_name=BREAKER_NAME, is_open=False)
    scoring.record_flag_metrics()

    tool_tier = tier_registry.get(tool_name=tool_name).tier
    response_tier = decide_response_tier(
        flagged_detector_count=scoring.flagged_detector_count, tool_tier=tool_tier
    )
    record_action(response_tier=response_tier.value)

    tool_result = None
    approval_request_id = None

    if shadow_mode:
        # Real shadow-mode requirement (found via blueprint
        # re-audit, closes §13's gap): REAL response_tier is
        # still computed above and recorded in the outcome/
        # metrics below for graduation-criteria analysis, but
        # the action ALWAYS executes -- shadow mode never
        # actually blocks or holds, only observes and logs.
        session_store.append_attempt(
            session_id=session_id, call=call_record, outcome=CallOutcome.ALLOWED,
            scoring_detail=_scoring_to_dict(scoring),
        )
        tool_result = tool_registry.call(tool_name=tool_name, params=params)
    elif response_tier is ResponseTier.BLOCK:
        session_store.append_attempt(
            session_id=session_id, call=call_record, outcome=CallOutcome.BLOCKED,
            scoring_detail=_scoring_to_dict(scoring),
        )
    elif response_tier is ResponseTier.REQUIRE_APPROVAL:
        request = approval_queue.submit(session_id=session_id, tool_name=tool_name, params=params)
        approval_request_id = request.request_id
        detail = _scoring_to_dict(scoring)
        # Real, Phase 3 addition (finding 021): threads the real
        # approval_request_id into scoring_detail so the investigation
        # report can look up the REAL eventual decision (approved/
        # denied/expired, and which ApproverRole decided) via
        # approval_queue.get() -- without this, a held call would be
        # unlinkable from its own real outcome in the report.
        detail["approval_request_id"] = approval_request_id
        session_store.append_attempt(
            session_id=session_id, call=call_record, outcome=CallOutcome.PENDING_APPROVAL,
            scoring_detail=detail,
        )
    else:
        session_store.append_attempt(
            session_id=session_id, call=call_record, outcome=CallOutcome.ALLOWED,
            scoring_detail=_scoring_to_dict(scoring),
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
        content_pattern_result=scoring.content_pattern_result,
        tool_result=tool_result,
        approval_request_id=approval_request_id,
        guardrail_bypassed=False,
        shadow_mode_active=shadow_mode,
    )
