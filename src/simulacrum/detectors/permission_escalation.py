"""
Permission-escalation detector (§04/§09 session-level tier): "a session
scoped for one tool category starts using tools well outside a normal
session's footprint for that task type."

Baseline per task type is derived directly from task_sim's own
templates — not a separately maintained list — same vocabulary-
consistency discipline as schema/call-text (avoids finding-011-shaped
drift between what's "normal" here and what task_sim actually
generates).
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.task_sim import TaskType
from simulacrum.task_sim.session import _TEMPLATES  # single source of truth


def _baseline_footprint(task_type: TaskType) -> frozenset[str]:
    template = _TEMPLATES[task_type]
    return frozenset(tool_name for tool_name, _ in template.steps)


BASELINE_FOOTPRINT: dict[TaskType, frozenset[str]] = {
    task_type: _baseline_footprint(task_type) for task_type in TaskType
}


@dataclass(frozen=True)
class PermissionEscalationResult:
    task_type: TaskType
    session_footprint: frozenset[str]
    baseline_footprint: frozenset[str]
    escalated_tools: frozenset[str]

    @property
    def is_escalated(self) -> bool:
        return bool(self.escalated_tools)


def check_permission_escalation(
    *, task_type: TaskType, session_footprint: frozenset[str]
) -> PermissionEscalationResult:
    baseline = BASELINE_FOOTPRINT[task_type]
    escalated = session_footprint - baseline
    return PermissionEscalationResult(
        task_type=task_type,
        session_footprint=session_footprint,
        baseline_footprint=baseline,
        escalated_tools=escalated,
    )
