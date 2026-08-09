"""
Human-approval queue (§13, §18): holds REQUIRE_APPROVAL-tier calls
pending explicit sign-off. Timeout policy (§13 v2): no response within
timeout_seconds (default 30 min) -> EXPIRED, distinct from an active
DENIED decision, so dashboards never conflate the two (§13's own
stated requirement).

Records queue-depth and outcome metrics (§18) on every state
transition — pending count updates on submit/decide/expire, outcome
counter increments on approve/deny/expire.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from simulacrum.observability import record_approval_outcome, set_approval_queue_depth


class ApprovalOutcome(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class ApproverRole(Enum):
    """
    Real, Phase 3 extension (finding 020, resolves §13's own named
    limitation): distinguishes WHO made a decision. TASK_INITIATING_USER
    is the original MVP-scoped approver (§13's honest "does not defend
    against the agent socially engineering the same user it's asking"
    limitation). OPS_SECURITY_APPROVER is genuinely out-of-band --
    authenticated via a real, separately-configured API key
    (ops_approver_api_key), not just a self-reported claim.
    """
    TASK_INITIATING_USER = "task_initiating_user"
    OPS_SECURITY_APPROVER = "ops_security_approver"


DEFAULT_TIMEOUT_SECONDS = 30 * 60


@dataclass
class ApprovalRequest:
    request_id: str
    session_id: str
    tool_name: str
    params: dict[str, str]
    submitted_at: float
    outcome: ApprovalOutcome = ApprovalOutcome.PENDING
    decided_at: float | None = None
    decided_by_role: ApproverRole | None = None  # real, Phase 3 (finding 020) --
    # None until a real decision is recorded; distinguishes which
    # approver role made the call, for genuine audit-trail purposes.


class UnknownApprovalRequestError(RuntimeError):
    pass


class ApprovalAlreadyDecidedError(RuntimeError):
    pass


@dataclass
class ApprovalQueue:
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    clock: Callable[[], float] = field(default=time.monotonic)
    _requests: dict[str, ApprovalRequest] = field(default_factory=dict)

    def _pending_count(self) -> int:
        return sum(1 for r in self._requests.values() if r.outcome is ApprovalOutcome.PENDING)

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
        set_approval_queue_depth(depth=self._pending_count())
        return request

    def get(self, *, request_id: str) -> ApprovalRequest:
        try:
            request = self._requests[request_id]
        except KeyError:
            raise UnknownApprovalRequestError(f"No approval request '{request_id}'") from None

        if request.outcome is ApprovalOutcome.PENDING:
            if self.clock() - request.submitted_at >= self.timeout_seconds:
                request.outcome = ApprovalOutcome.EXPIRED
                request.decided_at = self.clock()
                record_approval_outcome(outcome=ApprovalOutcome.EXPIRED.value)
                set_approval_queue_depth(depth=self._pending_count())
        return request

    def decide(
        self, *, request_id: str, approved: bool,
        approver_role: ApproverRole = ApproverRole.TASK_INITIATING_USER,
    ) -> ApprovalRequest:
        """
        approver_role defaults to TASK_INITIATING_USER -- the original
        MVP behavior is completely unchanged for existing callers.
        Real ops-approver decisions (finding 020) pass
        ApproverRole.OPS_SECURITY_APPROVER explicitly, only after real
        API-key auth succeeds at the API layer (§21/api/app.py) --
        this method itself does not authenticate, it only RECORDS which
        already-authenticated role decided, keeping auth and queue
        logic cleanly separated.
        """
        request = self.get(request_id=request_id)
        if request.outcome is not ApprovalOutcome.PENDING:
            raise ApprovalAlreadyDecidedError(
                f"Request '{request_id}' already resolved as {request.outcome.value}; "
                f"cannot record a new decision."
            )
        request.outcome = ApprovalOutcome.APPROVED if approved else ApprovalOutcome.DENIED
        request.decided_at = self.clock()
        request.decided_by_role = approver_role
        record_approval_outcome(outcome=request.outcome.value)
        set_approval_queue_depth(depth=self._pending_count())
        return request
