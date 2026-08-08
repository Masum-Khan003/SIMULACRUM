"""
Task-completion-rate cost reporting (§02's MVP scope, "Task-completion-
rate cost reporting for every false positive"): a REAL, distinct
metric from per-call false-positive rate. Runs real, legitimate
task_sim sessions through the real interceptor and asks a different
question: does ANY call in an otherwise-legitimate multi-call session
get falsely flagged/held/blocked? A single false positive anywhere in
a session derails the WHOLE TASK for a real user, not just that one
call -- this is the actual, felt cost of a false positive, distinct
from (and more consequential than) a bare per-call FP rate.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.attribution import TaskEmbedder, TaskRepresentation
from simulacrum.detectors import (
    ContentPatternDetector,
    SchemaRegistry,
)
from simulacrum.interception import FakeToolRegistry, intercept_and_call
from simulacrum.interception.circuit_breaker import CircuitBreaker
from simulacrum.risk_tiers import ToolRegistry
from simulacrum.session import InMemorySessionStore
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType, generate_session
from simulacrum.tier_engine import ApprovalQueue, ResponseTier


@dataclass(frozen=True)
class TaskCompletionResult:
    task_type: TaskType
    session_id: str
    completed_cleanly: bool
    """True if EVERY call in this session got ALLOW -- a real user
    would experience zero friction. False if ANY call got FLAG,
    REQUIRE_APPROVAL, or BLOCK -- a real user's task was interrupted,
    even if the interruption was ultimately survivable (e.g. FLAG)."""
    first_disruption_tier: str | None


@dataclass(frozen=True)
class TaskCompletionReport:
    total_sessions: int
    cleanly_completed: int
    disrupted: int

    @property
    def clean_completion_rate(self) -> float:
        return self.cleanly_completed / self.total_sessions if self.total_sessions else 0.0

    @property
    def false_positive_task_cost_rate(self) -> float:
        """The real, felt cost: fraction of legitimate sessions that
        experienced ANY disruption at all."""
        return self.disrupted / self.total_sessions if self.total_sessions else 0.0


def run_task_completion_report(
    *,
    embedder: TaskEmbedder,
    tool_registry: FakeToolRegistry,
    tier_registry: ToolRegistry,
    schema_registry: SchemaRegistry,
    content_pattern_detector: ContentPatternDetector,
    divergence_threshold: float,
    sessions_per_task_type: int = 20,
    seed_offset: int = 0,
) -> TaskCompletionReport:
    import random

    results = []
    for task_type in TaskType:
        task = TaskRepresentation.start(
            embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[task_type]
        )
        for i in range(sessions_per_task_type):
            seed = seed_offset + i
            session = generate_session(task_type=task_type, rng=random.Random(seed))
            session_store = InMemorySessionStore()
            breaker = CircuitBreaker()
            approval_queue = ApprovalQueue()

            first_disruption = None
            for call in session.calls:
                result = intercept_and_call(
                    tool_registry=tool_registry, tier_registry=tier_registry,
                    schema_registry=schema_registry, session_store=session_store,
                    circuit_breaker=breaker, approval_queue=approval_queue,
                    content_pattern_detector=content_pattern_detector,
                    task_representation=task, task_type=task_type,
                    session_id=session.session_id, tool_name=call.tool_name,
                    params=call.params, turn_index=call.turn_index,
                    divergence_threshold=divergence_threshold,
                )
                if result.response_tier is not ResponseTier.ALLOW and first_disruption is None:
                    first_disruption = result.response_tier.value

            results.append(
                TaskCompletionResult(
                    task_type=task_type, session_id=session.session_id,
                    completed_cleanly=(first_disruption is None),
                    first_disruption_tier=first_disruption,
                )
            )

    cleanly_completed = sum(1 for r in results if r.completed_cleanly)
    return TaskCompletionReport(
        total_sessions=len(results),
        cleanly_completed=cleanly_completed,
        disrupted=len(results) - cleanly_completed,
    )
