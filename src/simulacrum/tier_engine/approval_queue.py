"""
Human-approval queue (§13): holds REQUIRE_APPROVAL-tier calls pending
explicit sign-off. Approval timeout policy (§13 v2): no response within
a configurable window (default 30 min) -> EXPIRED, defaults to deny.
EXPIRED is logged as a DISTINCT outcome from an actively DENIED
decision, so dashboards never conflate "nobody was watching" with "a
human actively rejected this" (§13's own stated requirement).

Uses an injectable clock (same pattern as CircuitBreaker) so tests
don't need to actually sleep 30 minutes.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class ApprovalOutcome(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"  # distinct from DENIED — timeout, not an active decision


DEFAULT_TIMEOUT_SECONDS = 30 * 60  # 30 minutes, §13's stated default


@dataclass
class ApprovalRequest:
    request_id: str
    session_id: str
    tool_name: str
    params: dict[str, str]
    submitted_at: float
    outcome: ApprovalOutcome = ApprovalOutcome.PENDING
    decided_at: float | None = None


class UnknownApprovalRequestError(RuntimeError):
    pass


class ApprovalAlreadyDecidedError(RuntimeError):
    pass


@dataclass
class ApprovalQueue:
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    clock: Callable[[], float] = field(default=time.monotonic)
    _requests: dict[str, ApprovalRequest] = field(default_factory=dict)

    def submit(
        self, *, session_id: str, tool_name: str, params: dict[str, str]
    ) -> ApprovalRequest:
        request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            session_id=session_id,
            tool_name=tool_name,
            params=params,
            submitted_at=self.clock(),
        )
        self._requests[request.request_id] = request
        return request

    def get(self, *, request_id: str) -> ApprovalRequest:
        """
        Applies timeout expiry lazily on read — if PENDING and past
        timeout, transitions to EXPIRED before returning, so callers
        never see a stale PENDING that should already be expired.
        """
        try:
            request = self._requests[request_id]
        except KeyError:
            raise UnknownApprovalRequestError(f"No approval request '{request_id}'") from None

        if request.outcome is ApprovalOutcome.PENDING:
            if self.clock() - request.submitted_at >= self.timeout_seconds:
                request.outcome = ApprovalOutcome.EXPIRED
                request.decided_at = self.clock()
        return request

    def decide(self, *, request_id: str, approved: bool) -> ApprovalRequest:
        """
        Records an ACTIVE human decision. Raises if the request already
        expired or was already decided — a human decision after expiry
        does not retroactively un-expire it (the expiry already
        happened and was already logged as such).
        """
        request = self.get(request_id=request_id)
        if request.outcome is not ApprovalOutcome.PENDING:
            raise ApprovalAlreadyDecidedError(
                f"Request '{request_id}' already resolved as {request.outcome.value}; "
                f"cannot record a new decision."
            )
        request.outcome = ApprovalOutcome.APPROVED if approved else ApprovalOutcome.DENIED
        request.decided_at = self.clock()
        return request
