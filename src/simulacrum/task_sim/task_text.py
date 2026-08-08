"""
What a user would plausibly say to kick off each task type — used to
seed TaskRepresentation for param-vs-task divergence scoring (§09).
"""
from __future__ import annotations

from simulacrum.task_sim.session import TaskType

TASK_INITIAL_USER_TEXT: dict[TaskType, str] = {
    TaskType.INBOX_TRIAGE: "Please check my inbox and reply to anything urgent",
    TaskType.FLIGHT_BOOKING: "Please search for a flight and book it for me",
    TaskType.CALENDAR_SCHEDULING: "Please check my calendar and schedule a new event",
    TaskType.FILE_SHARING: "Please find that document and share it with the team",
    TaskType.CONTACT_UPDATE: "Please look up that contact and update their information",
}
