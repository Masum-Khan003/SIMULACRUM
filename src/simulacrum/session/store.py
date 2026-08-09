"""
Session store (§03, §06): accumulates a session's tool-call history so
session-level detectors (permission escalation, exfiltration,
loop-rate — §04) can score against the FULL trajectory. Tracks call
OUTCOME alongside each call (§09 gap 5: retry-vs-evasion needs to know
whether the prior attempt was blocked, errored, held pending approval,
or succeeded).

PENDING_APPROVAL is distinct from BLOCKED (added to close a real gap:
previously REQUIRE_APPROVAL calls were logged as BLOCKED, conflating
"held pending a human decision" with "actively blocked by a
detector" — which matters because loop_rate.py's evasion
classification treats a retry-after-BLOCKED as the adversarial
signature; a retry after a call that's merely awaiting human sign-off
is a different, non-adversarial situation and must not be classified
the same way).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from simulacrum.task_sim import ToolCall


class CallOutcome(Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    TOOL_ERROR = "tool_error"
    PENDING_APPROVAL = "pending_approval"


@dataclass(frozen=True)
class CallAttempt:
    call: ToolCall
    outcome: CallOutcome
    scoring_detail: dict | None = None  # real, Phase 3 addition (finding 021,
    # closes §18's SIEM-export gap AND enables the investigation report):
    # a plain, JSON-serializable dict of real per-call detector results
    # (schema/divergence/escalation/loop-rate/exfiltration/content-pattern),
    # not detector dataclass objects -- deliberately kept as plain data,
    # same principle as ExplanationContext, to avoid import coupling
    # between session storage and the detectors package. None when no
    # real scoring occurred for this attempt (e.g. circuit-breaker
    # bypass paths), never a fabricated placeholder.


class SessionStore(Protocol):
    def append_attempt(self, *, session_id: str, call: ToolCall, outcome: CallOutcome, scoring_detail: dict | None = None) -> None: ...
    def append_call(self, *, session_id: str, call: ToolCall) -> None: ...
    def get_attempts(self, *, session_id: str) -> tuple[CallAttempt, ...]: ...
    def get_calls(self, *, session_id: str) -> tuple[ToolCall, ...]: ...
    def get_tool_footprint(self, *, session_id: str) -> frozenset[str]: ...


@dataclass
class InMemorySessionStore:
    _sessions: dict[str, list[CallAttempt]] = field(default_factory=dict)

    def append_attempt(self, *, session_id: str, call: ToolCall, outcome: CallOutcome, scoring_detail: dict | None = None) -> None:
        self._sessions.setdefault(session_id, []).append(
            CallAttempt(call=call, outcome=outcome, scoring_detail=scoring_detail)
        )

    def append_call(self, *, session_id: str, call: ToolCall) -> None:
        self.append_attempt(session_id=session_id, call=call, outcome=CallOutcome.ALLOWED)

    def get_attempts(self, *, session_id: str) -> tuple[CallAttempt, ...]:
        return tuple(self._sessions.get(session_id, []))

    def get_calls(self, *, session_id: str) -> tuple[ToolCall, ...]:
        return tuple(a.call for a in self._sessions.get(session_id, []))

    def get_tool_footprint(self, *, session_id: str) -> frozenset[str]:
        return frozenset(a.call.tool_name for a in self._sessions.get(session_id, []))
