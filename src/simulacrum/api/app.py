"""
FastAPI app (§20's stack choice) exposing /health, /metrics (§18), and
real session/intercept/approval endpoints (§21) so the Docker Compose
stack demonstrates genuine live traffic, not just static scrapes.
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

import simulacrum.observability  # noqa: F401 — registers metric families
from simulacrum.api.state import UnknownSessionError, app_state
from simulacrum.interception import intercept_and_call
from simulacrum.risk_tiers import UnregisteredToolError
from simulacrum.task_sim import TaskType
from simulacrum.tier_engine import ApprovalAlreadyDecidedError, UnknownApprovalRequestError

app = FastAPI(title="Simulacrum", version="0.0.1")


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
        )
    except UnregisteredToolError as e:
        # §07: an unregistered tool cannot be processed at all — this
        # IS correct behavior, just needs to surface as a clean 4xx
        # to the HTTP caller instead of an unhandled 500.
        raise HTTPException(status_code=404, detail=str(e)) from None
    return InterceptResponse(
        tool_name=result.tool_name,
        response_tier=result.response_tier.value,
        allowed=result.allowed,
        tool_result=result.tool_result,
        approval_request_id=result.approval_request_id,
        guardrail_bypassed=result.guardrail_bypassed,
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
