"""
Verifies the Phase 3 exportable investigation report (finding 021).
Real, structural tests against InMemorySessionStore + real
intercept_and_call() output -- not synthetic report objects.
"""
import random

from simulacrum.attribution import FakeSemanticEmbedder, TaskRepresentation
from simulacrum.detectors import HeuristicContentPatternDetector, build_default_schema_registry
from simulacrum.interception import build_default_registry, intercept_and_call
from simulacrum.interception.circuit_breaker import CircuitBreaker
from simulacrum.investigation import generate_investigation_report
from simulacrum.investigation.report import to_redacted_dict
from simulacrum.risk_tiers import ToolRegistry
from simulacrum.session import InMemorySessionStore
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType
from simulacrum.tier_engine import ApprovalQueue


def _real_setup():
    embedder = FakeSemanticEmbedder()
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    session_store = InMemorySessionStore()
    breaker = CircuitBreaker()
    approval_queue = ApprovalQueue()
    task = TaskRepresentation.start(
        embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[TaskType.INBOX_TRIAGE]
    )
    return tool_registry, tier_registry, schema_registry, session_store, breaker, approval_queue, task


def test_report_reflects_real_calls_and_real_scoring_detail():
    tool_registry, tier_registry, schema_registry, session_store, breaker, approval_queue, task = _real_setup()

    intercept_and_call(
        tool_registry=tool_registry, tier_registry=tier_registry, schema_registry=schema_registry,
        session_store=session_store, circuit_breaker=breaker, approval_queue=approval_queue,
        content_pattern_detector=HeuristicContentPatternDetector(),
        task_representation=task, task_type=TaskType.INBOX_TRIAGE,
        session_id="report-test-1", tool_name="read_inbox", params={"count": "5"}, turn_index=0,
    )

    report = generate_investigation_report(session_id="report-test-1", session_store=session_store)
    assert report.session_id == "report-test-1"
    assert report.total_calls == 1
    assert report.calls[0].tool_name == "read_inbox"
    assert report.calls[0].scoring_detail is not None
    assert "divergence" in report.calls[0].scoring_detail
    assert report.outcome_breakdown.get("allowed") == 1


def test_report_links_held_call_to_real_eventual_approval_decision():
    """
    THE real, load-bearing test: a call that gets REQUIRE_APPROVAL
    must, after a real decision, show up in the report linked to that
    real outcome and real ApproverRole -- proving the
    approval_request_id threading actually works end-to-end.
    """
    tool_registry, tier_registry, schema_registry, session_store, breaker, approval_queue, task = _real_setup()

    result = intercept_and_call(
        tool_registry=tool_registry, tier_registry=tier_registry, schema_registry=schema_registry,
        session_store=session_store, circuit_breaker=breaker, approval_queue=approval_queue,
        content_pattern_detector=HeuristicContentPatternDetector(),
        task_representation=task, task_type=TaskType.FLIGHT_BOOKING,
        session_id="report-test-2", tool_name="book_flight", params={}, turn_index=0,
    )
    assert result.response_tier.value == "require_approval"

    approval_queue.decide(request_id=result.approval_request_id, approved=True)

    report = generate_investigation_report(
        session_id="report-test-2", session_store=session_store, approval_queue=approval_queue
    )
    entry = report.calls[0]
    assert entry.outcome == "pending_approval"
    assert entry.approval_outcome == "approved"
    assert entry.approval_decided_by_role == "task_initiating_user"


def test_redacted_dict_never_leaks_raw_sensitive_content_pattern_reasoning():
    """
    Real, direct proof redaction is actually applied -- not just that
    the function exists. Builds a report with a real ContentPattern-
    style scoring_detail containing a real, sensitive-shaped string,
    confirms it does NOT survive into the redacted output.
    """
    from simulacrum.investigation.report import CallReportEntry, InvestigationReport

    entry = CallReportEntry(
        turn_index=0,
        tool_name="send_email",
        params={"body": "my SSN is 123-45-6789"},
        outcome="flag",
        scoring_detail={
            "content_pattern": {
                "is_suspicious": True,
                "reasoning": "The body contains a value matching SSN pattern 123-45-6789",
                "matched_patterns": [],
                "confidence": 0.8,
            },
            "flagged_detector_count": 1,
        },
    )
    report = InvestigationReport(
        session_id="redaction-test", total_calls=1, calls=(entry,),
        flagged_call_count=1, outcome_breakdown={"flag": 1},
    )

    redacted = to_redacted_dict(report)
    serialized = str(redacted)
    assert "123-45-6789" not in serialized, (
        f"Real sensitive SSN-shaped content leaked into redacted report: {serialized}"
    )
