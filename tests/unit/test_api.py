"""
Verifies the real HTTP API (§21): session lifecycle, real interception
through the full pipeline over HTTP, approval flow, and clean error
handling for all the failure modes discovered manually before writing
this suite (unregistered tool, unknown session, invalid task_type).

Requires real Redis (SIMULACRUM_REDIS_URL) — same dependency as
test_redis_session_store.py.
"""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SIMULACRUM_REDIS_URL", "redis://localhost:6379/0")

from simulacrum.api.app import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_metrics_endpoint_serves_prometheus_format(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "simulacrum_actions_total" in r.text


def test_start_session_returns_id_and_task_type(client):
    r = client.post("/sessions", json={"task_type": "inbox_triage"})
    assert r.status_code == 200
    body = r.json()
    assert "session_id" in body
    assert body["task_type"] == "inbox_triage"


def test_start_session_invalid_task_type_returns_422(client):
    r = client.post("/sessions", json={"task_type": "not_real"})
    assert r.status_code == 422
    assert "Unknown task_type" in r.json()["detail"]


def test_clean_intercept_call_allows_and_executes(client):
    r1 = client.post("/sessions", json={"task_type": "inbox_triage"})
    session_id = r1.json()["session_id"]

    r2 = client.post(
        f"/sessions/{session_id}/intercept",
        json={"tool_name": "read_inbox", "params": {"count": "5"}},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["response_tier"] == "allow"
    assert body["allowed"] is True
    assert body["tool_result"] is not None


def test_intercept_on_unknown_session_returns_404(client):
    r = client.post(
        "/sessions/does-not-exist/intercept",
        json={"tool_name": "read_inbox", "params": {}},
    )
    assert r.status_code == 404


def test_intercept_on_unregistered_tool_returns_404_not_500(client):
    r1 = client.post("/sessions", json={"task_type": "inbox_triage"})
    session_id = r1.json()["session_id"]
    r2 = client.post(
        f"/sessions/{session_id}/intercept",
        json={"tool_name": "totally_fake_tool", "params": {}},
    )
    assert r2.status_code == 404


def test_require_approval_call_returns_pending_and_can_be_decided(client):
    """
    Full HTTP round-trip through the human-approval flow: intercept
    a call that requires approval, poll it, decide it, confirm the
    status reflects the decision.
    """
    r1 = client.post("/sessions", json={"task_type": "flight_booking"})
    session_id = r1.json()["session_id"]

    r2 = client.post(
        f"/sessions/{session_id}/intercept",
        json={"tool_name": "book_flight", "params": {}},  # missing flight_id -> flagged
    )
    body = r2.json()
    assert body["response_tier"] == "require_approval"
    assert body["tool_result"] is None
    request_id = body["approval_request_id"]
    assert request_id is not None

    r3 = client.get(f"/approvals/{request_id}")
    assert r3.status_code == 200
    assert r3.json()["outcome"] == "pending"

    r4 = client.post(f"/approvals/{request_id}/decide", json={"approved": True})
    assert r4.status_code == 200
    assert r4.json()["outcome"] == "approved"


def test_deciding_same_approval_twice_returns_409(client):
    r1 = client.post("/sessions", json={"task_type": "flight_booking"})
    session_id = r1.json()["session_id"]
    r2 = client.post(
        f"/sessions/{session_id}/intercept",
        json={"tool_name": "book_flight", "params": {}},
    )
    request_id = r2.json()["approval_request_id"]

    client.post(f"/approvals/{request_id}/decide", json={"approved": True})
    r3 = client.post(f"/approvals/{request_id}/decide", json={"approved": False})
    assert r3.status_code == 409


def test_unknown_approval_request_returns_404(client):
    r = client.get("/approvals/nonexistent-request-id")
    assert r.status_code == 404
