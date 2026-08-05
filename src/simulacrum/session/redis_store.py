"""
Real Redis-backed SessionStore (§03, §20). Implements the exact same
SessionStore protocol as InMemorySessionStore — proves the protocol
abstraction built in Phase 1 actually paid off: detector/interceptor
code written against SessionStore works unchanged against either
implementation.

Serialization: each CallAttempt stored as a JSON string in a Redis
list per session key (Redis has no native structured-record-list
type). Key pattern: simulacrum:session:{session_id}:attempts —
matches §11's repo-layout convention of namespacing external-resource
keys explicitly.

No default redis_url — required, keyword-only, per §00b/finding 001's
standing rule for every resource connection in this codebase.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import redis

from simulacrum.session.store import CallAttempt, CallOutcome
from simulacrum.task_sim import ToolCall

_KEY_PREFIX = "simulacrum:session"


def _key(session_id: str) -> str:
    return f"{_KEY_PREFIX}:{session_id}:attempts"


def _serialize(attempt: CallAttempt) -> str:
    return json.dumps({
        "tool_name": attempt.call.tool_name,
        "params": attempt.call.params,
        "turn_index": attempt.call.turn_index,
        "outcome": attempt.outcome.value,
    })


def _deserialize(raw: str) -> CallAttempt:
    data = json.loads(raw)
    return CallAttempt(
        call=ToolCall(
            tool_name=data["tool_name"],
            params=data["params"],
            turn_index=data["turn_index"],
        ),
        outcome=CallOutcome(data["outcome"]),
    )


@dataclass
class RedisSessionStore:
    redis_url: str  # required, keyword-only via dataclass field, no default

    def __post_init__(self) -> None:
        self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)

    def append_attempt(self, *, session_id: str, call: ToolCall, outcome: CallOutcome) -> None:
        attempt = CallAttempt(call=call, outcome=outcome)
        self._client.rpush(_key(session_id), _serialize(attempt))

    def append_call(self, *, session_id: str, call: ToolCall) -> None:
        self.append_attempt(session_id=session_id, call=call, outcome=CallOutcome.ALLOWED)

    def get_attempts(self, *, session_id: str) -> tuple[CallAttempt, ...]:
        raw_list = self._client.lrange(_key(session_id), 0, -1)
        return tuple(_deserialize(raw) for raw in raw_list)

    def get_calls(self, *, session_id: str) -> tuple[ToolCall, ...]:
        return tuple(a.call for a in self.get_attempts(session_id=session_id))

    def get_tool_footprint(self, *, session_id: str) -> frozenset[str]:
        return frozenset(a.call.tool_name for a in self.get_attempts(session_id=session_id))
