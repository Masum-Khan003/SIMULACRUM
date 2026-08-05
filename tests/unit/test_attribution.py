"""
Verifies §06/gap-2 sub-task boundary logic and the provenance-trust
enforcement (task representation updatable only from user turns).
"""
import pytest

from simulacrum.attribution import (
    FakeTaskEmbedder,
    TaskRepresentation,
    cosine_similarity,
)


@pytest.fixture
def embedder():
    return FakeTaskEmbedder()


def test_same_text_same_vector(embedder):
    assert embedder.embed("book a flight") == embedder.embed("book a flight")


def test_different_text_different_vector(embedder):
    assert embedder.embed("book a flight") != embedder.embed("cancel my subscription")


def test_cosine_similarity_identical_is_one(embedder):
    v = embedder.embed("book a flight")
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_zero_vector_is_zero():
    assert cosine_similarity((0.0, 0.0), (1.0, 1.0)) == 0.0


def test_start_sets_initial_vector(embedder):
    task = TaskRepresentation.start(embedder=embedder, initial_user_text="book a flight to London")
    assert task.sub_task_index == 0
    assert len(task.history) == 1


def test_refinement_does_not_open_new_subtask(embedder):
    task = TaskRepresentation.start(embedder=embedder, initial_user_text="book a flight to London")
    # identical text = similarity 1.0, must be treated as pure refinement
    opened = task.update_from_user_turn(user_text="book a flight to London")
    assert opened is False
    assert task.sub_task_index == 0


def test_unrelated_instruction_opens_new_subtask(embedder):
    task = TaskRepresentation.start(embedder=embedder, initial_user_text="book a flight to London")
    opened = task.update_from_user_turn(user_text="cancel my streaming subscription")
    assert opened is True
    assert task.sub_task_index == 1


def test_multiple_boundaries_increment_index(embedder):
    task = TaskRepresentation.start(embedder=embedder, initial_user_text="book a flight to London")
    task.update_from_user_turn(user_text="cancel my streaming subscription")
    task.update_from_user_turn(user_text="order me a pizza")
    assert task.sub_task_index == 2


def test_current_vector_updates_after_turn(embedder):
    task = TaskRepresentation.start(embedder=embedder, initial_user_text="book a flight to London")
    original = task.current_vector
    task.update_from_user_turn(user_text="cancel my streaming subscription")
    assert task.current_vector != original


def test_no_method_accepts_tool_output():
    """
    Enforcement check: TaskRepresentation must not expose any method
    that updates current_vector from arbitrary/tool-output content.
    Only update_from_user_turn should exist as a mutator.
    """
    public_methods = [
        name for name in dir(TaskRepresentation)
        if not name.startswith("_") and callable(getattr(TaskRepresentation, name))
    ]
    mutators = [m for m in public_methods if m not in ("start", "update_from_user_turn")]
    assert mutators == [], f"Unexpected mutator methods found: {mutators}"
