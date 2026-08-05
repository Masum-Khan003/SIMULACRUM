"""
Session store (§03, §06): accumulates a session's tool-call history so
session-level detectors (permission escalation, exfiltration, loop-rate
— §04) can score against the FULL trajectory, not just one call.

Tracks CALL OUTCOME alongside each call (§09 gap 5: retry-vs-evasion
classification needs to know whether the PRIOR attempt to a tool was
blocked, errored, or succeeded — not just that it happened).

append_call/get_calls are kept as backward-compatible convenience
wrappers (default outcome=ALLOWED) so earlier call sites/tests that
predate outcome-tracking keep working unchanged.
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


@dataclass(frozen=True)
class CallAttempt:
    call: ToolCall
    outcome: CallOutcome


class SessionStore(Protocol):
    def append_attempt(self, *, session_id: str, call: ToolCall, outcome: CallOutcome) -> None: ...
    def append_call(self, *, session_id: str, call: ToolCall) -> None: ...
    def get_attempts(self, *, session_id: str) -> tuple[CallAttempt, ...]: ...
    def get_calls(self, *, session_id: str) -> tuple[ToolCall, ...]: ...
    def get_tool_footprint(self, *, session_id: str) -> frozenset[str]: ...


@dataclass
class InMemorySessionStore:
    _sessions: dict[str, list[CallAttempt]] = field(default_factory=dict)

    def append_attempt(self, *, session_id: str, call: ToolCall, outcome: CallOutcome) -> None:
        self._sessions.setdefault(session_id, []).append(CallAttempt(call=call, outcome=outcome))

    def append_call(self, *, session_id: str, call: ToolCall) -> None:
        """Backward-compatible convenience — defaults outcome to ALLOWED."""
        self.append_attempt(session_id=session_id, call=call, outcome=CallOutcome.ALLOWED)

    def get_attempts(self, *, session_id: str) -> tuple[CallAttempt, ...]:
        return tuple(self._sessions.get(session_id, []))

    def get_calls(self, *, session_id: str) -> tuple[ToolCall, ...]:
        return tuple(a.call for a in self._sessions.get(session_id, []))

    def get_tool_footprint(self, *, session_id: str) -> frozenset[str]:
        return frozenset(a.call.tool_name for a in self._sessions.get(session_id, []))
