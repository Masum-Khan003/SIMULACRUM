"""
FastAPI app (§20's stack choice) exposing /health, /metrics (§18), and
real session/intercept/approval endpoints (§21) so the Docker Compose
stack demonstrates genuine live traffic, not just static scrapes.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

import simulacrum.observability  # noqa: F401 — registers metric families
from simulacrum.api.state import UnknownSessionError, app_state
from simulacrum.explainability import ExplanationContext
from simulacrum.interception import intercept_and_call
from simulacrum.redaction.redactor import redact_text
from simulacrum.risk_tiers import UnregisteredToolError
from simulacrum.task_sim import TaskType
from simulacrum.tier_engine import ApprovalAlreadyDecidedError, UnknownApprovalRequestError


@asynccontextmanager
async def lifespan(app: FastAPI):
    # §03/§12: starts the real async/background drift scheduler on
    # app startup, stops it cleanly on shutdown -- closes the gap
    # where drift checks only ever ran on-demand via an explicit
    # HTTP call.
    await app_state.drift_scheduler.start(
        get_active_sessions=app_state.get_active_sessions_for_drift_check
    )
    yield
    await app_state.drift_scheduler.stop()


def _collect_flagged_reasons(result) -> tuple[str, ...]:
    reasons = []
    if result.schema_violation is not None and result.schema_violation.is_violation:
        v = result.schema_violation
        reasons.append(
            f"schema_violation: missing={sorted(v.missing_params)}, "
            f"unexpected={sorted(v.unexpected_params)}"
        )
    if result.divergence_result is not None and result.divergence_result.is_divergent:
        reasons.append(
            f"param_divergence: similarity={result.divergence_result.similarity:.3f} "
            f"below threshold"
        )
    if result.escalation_result is not None and result.escalation_result.is_escalated:
        reasons.append(
            f"permission_escalation: {sorted(result.escalation_result.escalated_tools)} "
            f"outside task baseline"
        )
    if result.loop_rate_result is not None and result.loop_rate_result.is_flagged:
        reasons.append(
            f"loop_rate: evasion={result.loop_rate_result.is_evasion_retry}, "
            f"rate_exceeded={result.loop_rate_result.is_rate_exceeded}"
        )
    if result.exfiltration_result is not None and result.exfiltration_result.is_flagged:
        reasons.append(
            f"exfiltration: frequency={result.exfiltration_result.is_frequency_exceeded}, "
            f"content={result.exfiltration_result.is_content_anomalous}"
        )
    return tuple(reasons)

app = FastAPI(title="Simulacrum", version="0.0.1", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


class StartSessionRequest(BaseModel):
    task_type: str


class StartSessionResponse(BaseModel):
    session_id: str
    task_type: str


@app.post("/sessions", response_model=StartSessionResponse)
def start_session(body: StartSessionRequest) -> StartSessionResponse:
    try:
        task_type = TaskType(body.task_type)
    except ValueError:
        valid = [t.value for t in TaskType]
        raise HTTPException(
            status_code=422, detail=f"Unknown task_type '{body.task_type}'. Valid: {valid}"
        ) from None

    session_id = str(uuid.uuid4())
    app_state.start_session(session_id=session_id, task_type=task_type)
    return StartSessionResponse(session_id=session_id, task_type=task_type.value)


class UserTurnRequest(BaseModel):
    text: str


class UserTurnResponse(BaseModel):
    is_new_subtask: bool
    sub_task_index: int


@app.post("/sessions/{session_id}/turn", response_model=UserTurnResponse)
def user_turn(session_id: str, body: UserTurnRequest) -> UserTurnResponse:
    """
    §06/gap 2: a new user turn within an existing session. Detects
    whether this text opens a new sub-task (real Groq reasoning,
    fails open to embedding fallback) and updates the task
    representation accordingly — same trust-gated update path as
    always (§06: never accepts tool-output content, only direct
    user text).
    """
    try:
        task_representation = app_state.get_task_representation(session_id=session_id)
    except UnknownSessionError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    is_new = task_representation.update_from_user_turn(
        user_text=body.text, boundary_classifier=app_state.boundary_classifier
    )
    return UserTurnResponse(
        is_new_subtask=is_new, sub_task_index=task_representation.sub_task_index
    )


class InterceptRequest(BaseModel):
    tool_name: str
    params: dict[str, str]
    turn_index: int = 0


class InterceptResponse(BaseModel):
    tool_name: str
    response_tier: str
    allowed: bool
    tool_result: dict[str, str] | None
    approval_request_id: str | None
    guardrail_bypassed: bool
    explanation: str | None


class DriftCheckResponse(BaseModel):
    is_drifted: bool
    reasoning: str | None


@app.post("/sessions/{session_id}/check-drift", response_model=DriftCheckResponse)
def check_drift(session_id: str) -> DriftCheckResponse:
    """
    §04/§10 goal drift, ON-DEMAND (§03 specifies this should really
    run off-path/async/on-a-rolling-interval — true background
    scheduling is separate, larger infrastructure not built yet, see
    docs/BACKLOG.md). This endpoint runs it synchronously, right now,
    against the session'''s REAL call history from the real session
    store — usable today, honestly scoped as on-demand rather than
    automatic.
    """
    try:
        task_representation = app_state.get_task_representation(session_id=session_id)
    except UnknownSessionError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    calls = app_state.session_store.get_calls(session_id=session_id)
    call_descriptions = tuple(
        f"{c.tool_name}({', '.join(f'{k}={v}' for k, v in c.params.items())})" for c in calls
    )
    result = app_state.drift_detector.check_drift(
        task_description=task_representation.current_task_text,
        call_history=call_descriptions,
    )
    redacted_reasoning = redact_text(text=result.reasoning) if result.reasoning else None
    return DriftCheckResponse(is_drifted=result.is_drifted, reasoning=redacted_reasoning)


class StandingDriftResponse(BaseModel):
    has_decision: bool
    is_drifted: bool | None
    reasoning: str | None
    checked_at_call_count: int | None


@app.get("/sessions/{session_id}/drift-status", response_model=StandingDriftResponse)
def get_drift_status(session_id: str) -> StandingDriftResponse:
    """
    Retrieves the STANDING drift decision computed by the real
    background scheduler (§03/§12) -- does NOT trigger a new check,
    just returns whatever the background loop has already computed.
    Distinct from POST /sessions/{id}/check-drift, which runs a
    synchronous, on-demand check right now.
    """
    try:
        app_state.get_task_representation(session_id=session_id)
    except UnknownSessionError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    decision = app_state.drift_scheduler.get_standing_decision(session_id=session_id)
    if decision is None:
        return StandingDriftResponse(
            has_decision=False, is_drifted=None, reasoning=None, checked_at_call_count=None
        )
    return StandingDriftResponse(
        has_decision=True,
        is_drifted=decision.result.is_drifted,
        reasoning=redact_text(text=decision.result.reasoning) if decision.result.reasoning else None,
        checked_at_call_count=decision.checked_at_call_count,
    )


@app.post("/sessions/{session_id}/intercept", response_model=InterceptResponse)
def intercept(session_id: str, body: InterceptRequest) -> InterceptResponse:
    try:
        task_representation = app_state.get_task_representation(session_id=session_id)
        task_type = app_state.get_task_type(session_id=session_id)
    except UnknownSessionError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    try:
        result = intercept_and_call(
            tool_registry=app_state.tool_registry,
            tier_registry=app_state.tier_registry,
            schema_registry=app_state.schema_registry,
            session_store=app_state.session_store,
            circuit_breaker=app_state.circuit_breaker,
            approval_queue=app_state.approval_queue,
            task_representation=task_representation,
            task_type=task_type,
            session_id=session_id,
            tool_name=body.tool_name,
            params=body.params,
            turn_index=body.turn_index,
            divergence_threshold=app_state.divergence_threshold,
            content_pattern_detector=app_state.content_pattern_detector,
        )
    except UnregisteredToolError as e:
        # §07: an unregistered tool cannot be processed at all — this
        # IS correct behavior, just needs to surface as a clean 4xx
        # to the HTTP caller instead of an unhandled 500.
        raise HTTPException(status_code=404, detail=str(e)) from None
    # Only generate an explanation for non-ALLOW decisions — an
    # unremarkable clean allow needs no explanation, and generating
    # one for every single call would waste real LLM calls for no
    # benefit (§14 is about explaining FLAGGED/HELD/BLOCKED actions).
    explanation = None
    if result.response_tier.value != "allow":
        raw_explanation = app_state.explainer.explain(
            context=ExplanationContext(
                tool_name=result.tool_name,
                response_tier=result.response_tier.value,
                flagged_reasons=_collect_flagged_reasons(result),
            )
        )
        # §19 day-one requirement: redact before this text ever leaves
        # the process (LLM reasoning naturally quotes back the real
        # param content it analyzed).
        explanation = redact_text(text=raw_explanation)

    return InterceptResponse(
        tool_name=result.tool_name,
        response_tier=result.response_tier.value,
        allowed=result.allowed,
        tool_result=result.tool_result,
        approval_request_id=result.approval_request_id,
        guardrail_bypassed=result.guardrail_bypassed,
        explanation=explanation,
    )


class ApprovalDecisionRequest(BaseModel):
    approved: bool


class ApprovalStatusResponse(BaseModel):
    request_id: str
    outcome: str


@app.get("/approvals/{request_id}", response_model=ApprovalStatusResponse)
def get_approval(request_id: str) -> ApprovalStatusResponse:
    try:
        request = app_state.approval_queue.get(request_id=request_id)
    except UnknownApprovalRequestError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return ApprovalStatusResponse(request_id=request.request_id, outcome=request.outcome.value)


@app.post("/approvals/{request_id}/decide", response_model=ApprovalStatusResponse)
def decide_approval(request_id: str, body: ApprovalDecisionRequest) -> ApprovalStatusResponse:
    try:
        request = app_state.approval_queue.decide(request_id=request_id, approved=body.approved)
    except UnknownApprovalRequestError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ApprovalAlreadyDecidedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return ApprovalStatusResponse(request_id=request.request_id, outcome=request.outcome.value)
