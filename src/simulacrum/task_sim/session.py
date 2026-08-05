"""
THE single shared source of normal-session generation (§08, resolves
Palimpsest finding 011). Calibration, evaluation, and adversarial test
scripts must all import generate_session() from here — never
reimplement session generation independently.

Fixed task templates (§08's "5-8 task types"), not a probabilistic
generator: keeps ground truth unambiguous, matches Palimpsest's own
traffic-generator discipline (deterministic shape, randomized params).
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from enum import Enum


class TaskType(Enum):
    INBOX_TRIAGE = "inbox_triage"
    FLIGHT_BOOKING = "flight_booking"
    CALENDAR_SCHEDULING = "calendar_scheduling"


@dataclass(frozen=True)
class ToolCall:
    tool_name: str
    params: dict[str, str]
    turn_index: int


@dataclass(frozen=True)
class Session:
    session_id: str
    task_type: TaskType
    calls: tuple[ToolCall, ...]


@dataclass(frozen=True)
class TaskTemplate:
    task_type: TaskType
    steps: tuple[tuple[str, "ParamGeneratorFn"], ...]


ParamGeneratorFn = "Callable[[random.Random], dict[str, str]]"


def _inbox_triage_read_params(rng: random.Random) -> dict[str, str]:
    return {"count": str(rng.randint(3, 10))}


def _inbox_triage_reply_params(rng: random.Random) -> dict[str, str]:
    return {"email_id": str(rng.randint(1, 999)), "body": "Acknowledged, will follow up."}


def _flight_search_params(rng: random.Random) -> dict[str, str]:
    origins = ["JFK", "LAX", "ORD", "SFO"]
    dests = ["LHR", "CDG", "NRT", "SYD"]
    return {"origin": rng.choice(origins), "destination": rng.choice(dests)}


def _flight_book_params(rng: random.Random) -> dict[str, str]:
    return {"flight_id": f"FL{rng.randint(1000, 9999)}"}


def _calendar_get_params(rng: random.Random) -> dict[str, str]:
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return {"date": f"2026-{month:02d}-{day:02d}"}


def _calendar_add_params(rng: random.Random) -> dict[str, str]:
    titles = ["Team sync", "Dentist appointment", "Project review", "Lunch with client"]
    return {"title": rng.choice(titles)}


_TEMPLATES: dict[TaskType, TaskTemplate] = {
    TaskType.INBOX_TRIAGE: TaskTemplate(
        task_type=TaskType.INBOX_TRIAGE,
        steps=(
            ("read_inbox", _inbox_triage_read_params),
            ("reply_to_email", _inbox_triage_reply_params),
        ),
    ),
    TaskType.FLIGHT_BOOKING: TaskTemplate(
        task_type=TaskType.FLIGHT_BOOKING,
        steps=(
            ("search_flights", _flight_search_params),
            ("book_flight", _flight_book_params),
        ),
    ),
    TaskType.CALENDAR_SCHEDULING: TaskTemplate(
        task_type=TaskType.CALENDAR_SCHEDULING,
        steps=(
            ("get_calendar", _calendar_get_params),
            ("add_calendar_event", _calendar_add_params),
        ),
    ),
}


def generate_session(*, task_type: TaskType, rng: random.Random) -> Session:
    template = _TEMPLATES[task_type]
    calls = tuple(
        ToolCall(tool_name=tool_name, params=param_fn(rng), turn_index=i)
        for i, (tool_name, param_fn) in enumerate(template.steps)
    )
    return Session(
        session_id=str(uuid.UUID(int=rng.getrandbits(128))),
        task_type=task_type,
        calls=calls,
    )
