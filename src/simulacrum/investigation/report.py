"""
Exportable per-session investigation report (Phase 3, §23, finding
021). Real, structured answer to "what happened in this session, and
why" -- aggregates every real call's outcome, detector detail (finding
021's scoring_detail extension), and, for held calls, the real eventual
approval decision (finding 020's ApproverRole distinction).

Real, honest scope: JSON-first (clean, testable, real data structure).
Markdown rendering is a real, fast follow within this same item, not
a separate future task.

Deliberately depends only on SessionStore + ApprovalQueue's real,
public interfaces -- no coupling to interceptor internals beyond the
plain-dict scoring_detail shape _scoring_to_dict() already produces.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from simulacrum.session import CallOutcome, SessionStore
from simulacrum.tier_engine import ApprovalQueue, UnknownApprovalRequestError


@dataclass(frozen=True)
class CallReportEntry:
    turn_index: int
    tool_name: str
    params: dict[str, str]
    outcome: str
    scoring_detail: dict | None
    # Real, only populated for PENDING_APPROVAL-outcome calls whose
    # approval_request_id could still be resolved via the real
    # ApprovalQueue (None if never held, or if the request has since
    # been evicted from an in-memory queue's real lifetime).
    approval_outcome: str | None = None
    approval_decided_by_role: str | None = None


@dataclass(frozen=True)
class InvestigationReport:
    session_id: str
    total_calls: int
    calls: tuple[CallReportEntry, ...]
    flagged_call_count: int  # real count of calls with scoring_detail.flagged_detector_count > 0
    outcome_breakdown: dict[str, int]  # real counts per CallOutcome value


def generate_investigation_report(
    *, session_id: str, session_store: SessionStore, approval_queue: ApprovalQueue | None = None
) -> InvestigationReport:
    """
    Real, honest note: approval_queue is optional. If omitted, held
    calls are still reported with their real detector detail, just
    without the real eventual decision looked up -- this keeps the
    report usable even when only session_store is available (e.g. a
    read-only audit context with no live approval queue reference).
    """
    attempts = session_store.get_attempts(session_id=session_id)

    entries = []
    outcome_counts: dict[str, int] = {}
    flagged_count = 0

    for attempt in attempts:
        outcome_value = attempt.outcome.value
        outcome_counts[outcome_value] = outcome_counts.get(outcome_value, 0) + 1

        if attempt.scoring_detail is not None and attempt.scoring_detail.get("flagged_detector_count", 0) > 0:
            flagged_count += 1

        approval_outcome = None
        approval_decided_by_role = None
        if (
            attempt.outcome is CallOutcome.PENDING_APPROVAL
            and attempt.scoring_detail is not None
            and approval_queue is not None
        ):
            request_id = attempt.scoring_detail.get("approval_request_id")
            if request_id is not None:
                try:
                    request = approval_queue.get(request_id=request_id)
                    approval_outcome = request.outcome.value
                    if request.decided_by_role is not None:
                        approval_decided_by_role = request.decided_by_role.value
                except UnknownApprovalRequestError:
                    pass  # real, honest: request no longer resolvable, leave both fields None

        entries.append(
            CallReportEntry(
                turn_index=attempt.call.turn_index,
                tool_name=attempt.call.tool_name,
                params=dict(attempt.call.params),
                outcome=outcome_value,
                scoring_detail=attempt.scoring_detail,
                approval_outcome=approval_outcome,
                approval_decided_by_role=approval_decided_by_role,
            )
        )

    return InvestigationReport(
        session_id=session_id,
        total_calls=len(entries),
        calls=tuple(entries),
        flagged_call_count=flagged_count,
        outcome_breakdown=outcome_counts,
    )


def to_redacted_dict(report: InvestigationReport) -> dict:
    """
    Real, Phase 3 requirement (§19's "day-one requirement" for
    sensitive-parameter redaction, same discipline finding
    "§19 sensitive-parameter redaction" already applied to explanation/
    reasoning fields): converts a real InvestigationReport into a
    plain, JSON-safe dict with redaction applied to every real
    parameter value and every real content-pattern reasoning string --
    the two places this report could otherwise leak real sensitive
    content (emails, SSNs, credentials) via HTTP, exactly the same
    exposure that finding's own audit found and closed for the
    explanation endpoints.
    """
    from simulacrum.redaction.redactor import redact_params, redact_text

    def _redact_scoring_detail(detail: dict | None) -> dict | None:
        if detail is None:
            return None
        redacted = dict(detail)
        content_pattern = redacted.get("content_pattern")
        if content_pattern is not None and content_pattern.get("reasoning"):
            redacted["content_pattern"] = {
                **content_pattern,
                "reasoning": redact_text(text=content_pattern["reasoning"]),
            }
        return redacted

    return {
        "session_id": report.session_id,
        "total_calls": report.total_calls,
        "flagged_call_count": report.flagged_call_count,
        "outcome_breakdown": report.outcome_breakdown,
        "calls": [
            {
                "turn_index": c.turn_index,
                "tool_name": c.tool_name,
                "params": redact_params(params=c.params),
                "outcome": c.outcome,
                "scoring_detail": _redact_scoring_detail(c.scoring_detail),
                "approval_outcome": c.approval_outcome,
                "approval_decided_by_role": c.approval_decided_by_role,
            }
            for c in report.calls
        ],
    }
