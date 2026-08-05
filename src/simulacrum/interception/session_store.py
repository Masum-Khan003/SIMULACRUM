"""
Session store (§03, §06): accumulates a session's tool-call history so
session-level detectors (permission escalation, exfiltration — §04)
can score against the FULL trajectory, not just one call.

SessionStore is a Protocol, not a base class — same pattern as
TaskEmbedder (attribution/embedding.py). InMemorySessionStore is the
dependency-free fake for testing detector LOGIC. RedisSessionStore
(real implementation, §20's named choice) is separate, thin, and
tested against a real Redis service — deferred until a detector
actually needs to run against it, not built speculatively now.

Deliberately minimal for this step: append + retrieve calls, and
tool-category footprint (the concrete signal permission escalation
needs). NOT building trajectory-model storage, circuit-breaker state,
or approval-queue state yet — those are separate concerns for later
work (see docs/BACKLOG.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from simulacrum.task_sim import ToolCall


class SessionStore(Protocol):
    def append_call(self, *, session_id: str, call: ToolCall) -> None: ...
    def get_calls(self, *, session_id: str) -> tuple[ToolCall, ...]: ...
    def get_tool_footprint(self, *, session_id: str) -> frozenset[str]: ...


@dataclass
class InMemorySessionStore:
    """
    Dependency-free fake, keyed by session_id. No default resource
    URL concern here since it's not a shared/external resource — but
    still requires session_id explicitly at every call site, no
    "current session" implicit state, to avoid a different class of
    bug (silent cross-session leakage from forgetting to pass the id).
    """
    _sessions: dict[str, list[ToolCall]] = field(default_factory=dict)

    def append_call(self, *, session_id: str, call: ToolCall) -> None:
        self._sessions.setdefault(session_id, []).append(call)

    def get_calls(self, *, session_id: str) -> tuple[ToolCall, ...]:
        return tuple(self._sessions.get(session_id, []))

    def get_tool_footprint(self, *, session_id: str) -> frozenset[str]:
        return frozenset(c.tool_name for c in self._sessions.get(session_id, []))
