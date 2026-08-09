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


def test_background_drift_scheduler_computes_standing_decision_unattended():
    """
    Real, end-to-end proof of §03/§12's async/background drift
    scheduling: starts the REAL FastAPI lifespan (via TestClient's
    context manager), runs real calls through a session, waits with
    REAL time.sleep for the background asyncio loop to pick it up on
    its OWN -- nobody explicitly triggers a drift check. Confirms
    GET /sessions/{id}/drift-status reflects a standing decision
    computed unattended, not by an on-demand call.
    """
    import time

    from simulacrum.api.state import app_state

    app_state.drift_scheduler.poll_interval_seconds = 0.3

    with TestClient(app) as client:
        r1 = client.post("/sessions", json={"task_type": "inbox_triage"})
        session_id = r1.json()["session_id"]

        # Before any calls, no standing decision should exist yet.
        r_before = client.get(f"/sessions/{session_id}/drift-status")
        assert r_before.json()["has_decision"] is False

        calls = [
            ("read_inbox", {"count": "10"}),
            ("reply_to_email", {"email_id": "42", "body": "Acknowledged"}),
            ("get_calendar", {"date": "2026-08-10"}),
        ]
        for tool_name, params in calls:
            client.post(
                f"/sessions/{session_id}/intercept", json={"tool_name": tool_name, "params": params}
            )

        time.sleep(1.5)  # real wait for the real background loop

        r_after = client.get(f"/sessions/{session_id}/drift-status")
        body = r_after.json()
        assert body["has_decision"] is True, (
            "Background scheduler should have computed a standing decision unattended"
        )
        assert body["checked_at_call_count"] == 3


def test_drift_status_for_unknown_session_returns_404():
    with TestClient(app) as client:
        r = client.get("/sessions/nonexistent-session/drift-status")
        assert r.status_code == 404


def test_explanation_field_never_leaks_raw_sensitive_params():
    """
    Real, end-to-end proof of §19's redaction requirement: sends real
    sensitive content (email address, SSN) through the actual HTTP
    API, confirms neither appears anywhere in the response body.
    """
    with TestClient(app) as client:
        r1 = client.post("/sessions", json={"task_type": "inbox_triage"})
        session_id = r1.json()["session_id"]

        r2 = client.post(
            f"/sessions/{session_id}/intercept",
            json={
                "tool_name": "reply_to_email",
                "params": {
                    "email_id": "42",
                    "body": (
                        "Please find attached the customer export including "
                        "jane.doe@company.com and SSN 987-65-4321"
                    ),
                },
            },
        )
        body_text = str(r2.json())
        assert "jane.doe@company.com" not in body_text
        assert "987-65-4321" not in body_text


def test_ops_decide_returns_503_when_not_configured(client, monkeypatch):
    """
    Real, honest-disablement check (finding 020): with no
    SIMULACRUM_OPS_APPROVER_API_KEY configured, the ops-decide
    endpoint must be HONESTLY unavailable (503), never silently
    permissive.
    """
    from simulacrum.config.settings import get_settings

    monkeypatch.delenv("SIMULACRUM_OPS_APPROVER_API_KEY", raising=False)
    get_settings.cache_clear()

    r1 = client.post("/sessions", json={"task_type": "flight_booking"})
    session_id = r1.json()["session_id"]
    r2 = client.post(
        f"/sessions/{session_id}/intercept",
        json={"tool_name": "book_flight", "params": {}},
    )
    request_id = r2.json()["approval_request_id"]

    r3 = client.post(
        f"/approvals/{request_id}/ops-decide",
        json={"approved": True},
        headers={"X-Ops-Approver-Key": "any-key-at-all"},
    )
    assert r3.status_code == 503
    get_settings.cache_clear()


def test_ops_decide_returns_401_with_wrong_key(client, monkeypatch):
    """Real auth check: a configured key that doesn't match must reject with 401."""
    from simulacrum.config.settings import get_settings

    monkeypatch.setenv("SIMULACRUM_OPS_APPROVER_API_KEY", "real-correct-key")
    get_settings.cache_clear()

    r1 = client.post("/sessions", json={"task_type": "flight_booking"})
    session_id = r1.json()["session_id"]
    r2 = client.post(
        f"/sessions/{session_id}/intercept",
        json={"tool_name": "book_flight", "params": {}},
    )
    request_id = r2.json()["approval_request_id"]

    r3 = client.post(
        f"/approvals/{request_id}/ops-decide",
        json={"approved": True},
        headers={"X-Ops-Approver-Key": "wrong-key"},
    )
    assert r3.status_code == 401

    monkeypatch.delenv("SIMULACRUM_OPS_APPROVER_API_KEY", raising=False)
    get_settings.cache_clear()


def test_ops_decide_succeeds_with_real_correct_key(client, monkeypatch):
    """
    THE real, load-bearing test: a genuinely correct key succeeds,
    and the decision is recorded as OPS_SECURITY_APPROVER, not the
    default TASK_INITIATING_USER -- proving the real role distinction
    actually threads through end-to-end via real HTTP.
    """
    from simulacrum.api.state import app_state
    from simulacrum.config.settings import get_settings
    from simulacrum.tier_engine import ApproverRole

    monkeypatch.setenv("SIMULACRUM_OPS_APPROVER_API_KEY", "real-correct-key")
    get_settings.cache_clear()

    r1 = client.post("/sessions", json={"task_type": "flight_booking"})
    session_id = r1.json()["session_id"]
    r2 = client.post(
        f"/sessions/{session_id}/intercept",
        json={"tool_name": "book_flight", "params": {}},
    )
    request_id = r2.json()["approval_request_id"]

    r3 = client.post(
        f"/approvals/{request_id}/ops-decide",
        json={"approved": True},
        headers={"X-Ops-Approver-Key": "real-correct-key"},
    )
    assert r3.status_code == 200
    assert r3.json()["outcome"] == "approved"

    real_request = app_state.approval_queue.get(request_id=request_id)
    assert real_request.decided_by_role is ApproverRole.OPS_SECURITY_APPROVER

    monkeypatch.delenv("SIMULACRUM_OPS_APPROVER_API_KEY", raising=False)
    get_settings.cache_clear()


def test_regular_decide_still_records_task_initiating_user_role(client):
    """
    Real, structural regression guard: the ORIGINAL /decide endpoint
    must still record ApproverRole.TASK_INITIATING_USER (the default),
    proving the ops-approver addition didn't silently change existing
    MVP behavior.
    """
    from simulacrum.api.state import app_state
    from simulacrum.tier_engine import ApproverRole

    r1 = client.post("/sessions", json={"task_type": "flight_booking"})
    session_id = r1.json()["session_id"]
    r2 = client.post(
        f"/sessions/{session_id}/intercept",
        json={"tool_name": "book_flight", "params": {}},
    )
    request_id = r2.json()["approval_request_id"]

    client.post(f"/approvals/{request_id}/decide", json={"approved": True})

    real_request = app_state.approval_queue.get(request_id=request_id)
    assert real_request.decided_by_role is ApproverRole.TASK_INITIATING_USER
