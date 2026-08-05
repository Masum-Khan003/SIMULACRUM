"""
Verifies §06/gap-2 sub-task boundary bookkeeping (TaskRepresentation
itself) and the provenance-trust enforcement, using
EmbeddingBoundaryClassifier (deterministic, no network) — these tests
verify TaskRepresentation's own state-tracking logic, not classifier
accuracy (that's covered separately in test_boundary_classifier.py).
"""
import pytest

from simulacrum.attribution import (
    EmbeddingBoundaryClassifier,
    FakeTaskEmbedder,
    TaskRepresentation,
    cosine_similarity,
)


@pytest.fixture
def embedder():
    return FakeTaskEmbedder()


@pytest.fixture
def classifier(embedder):
    return EmbeddingBoundaryClassifier(embedder=embedder, threshold=0.5)


@pytest.fixture
def semantic_embedder():
    # FakeTaskEmbedder (whole-string hash) treats ANY two distinct
    # strings as near-zero similarity by design — fine for the
    # identical-vs-different tests above, but wrong for tests that
    # need a refinement (different wording, same intent) to plausibly
    # score as similar. FakeSemanticEmbedder (bag-of-words) shares
    # real vocabulary between related phrases, so it'''s the correct
    # fixture for those cases.
    from simulacrum.attribution import FakeSemanticEmbedder
    return FakeSemanticEmbedder()


@pytest.fixture
def semantic_classifier(semantic_embedder):
    return EmbeddingBoundaryClassifier(embedder=semantic_embedder, threshold=0.1)


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
    assert task.current_task_text == "book a flight to London"


def test_refinement_does_not_open_new_subtask(embedder, classifier):
    task = TaskRepresentation.start(embedder=embedder, initial_user_text="book a flight to London")
    opened = task.update_from_user_turn(
        user_text="book a flight to London", boundary_classifier=classifier
    )
    assert opened is False
    assert task.sub_task_index == 0


def test_unrelated_instruction_opens_new_subtask(embedder, classifier):
    task = TaskRepresentation.start(embedder=embedder, initial_user_text="book a flight to London")
    opened = task.update_from_user_turn(
        user_text="cancel my streaming subscription", boundary_classifier=classifier
    )
    assert opened is True
    assert task.sub_task_index == 1


def test_multiple_boundaries_increment_index(embedder, classifier):
    task = TaskRepresentation.start(embedder=embedder, initial_user_text="book a flight to London")
    task.update_from_user_turn(user_text="cancel my streaming subscription", boundary_classifier=classifier)
    task.update_from_user_turn(user_text="order me a pizza", boundary_classifier=classifier)
    assert task.sub_task_index == 2


def test_current_vector_updates_after_turn(embedder, classifier):
    task = TaskRepresentation.start(embedder=embedder, initial_user_text="book a flight to London")
    original = task.current_vector
    task.update_from_user_turn(user_text="cancel my streaming subscription", boundary_classifier=classifier)
    assert task.current_vector != original
    assert task.current_task_text == "cancel my streaming subscription"


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


def test_current_task_text_stable_across_refinement(semantic_embedder, semantic_classifier):
    """
    THE bug found via real end-to-end HTTP testing: current_task_text
    must NOT drift to the refinement's own text — it stays anchored
    to the actual ongoing task so a LATER turn is still judged against
    the real task, not an intermediate refinement.
    """
    task = TaskRepresentation.start(embedder=semantic_embedder, initial_user_text="book a flight to London")
    task.update_from_user_turn(user_text="preferably a direct flight", boundary_classifier=semantic_classifier)
    assert task.current_task_text == "book a flight to London"


def test_current_task_text_advances_only_on_new_subtask(embedder, classifier):
    task = TaskRepresentation.start(embedder=embedder, initial_user_text="book a flight to London")
    task.update_from_user_turn(user_text="cancel my streaming subscription", boundary_classifier=classifier)
    assert task.current_task_text == "cancel my streaming subscription"


def test_multi_turn_chain_does_not_drift_anchor(semantic_embedder, semantic_classifier):
    """
    Regression test for the exact failure mode discovered live: a
    refinement followed by a genuine pivot must still correctly judge
    the pivot against the ORIGINAL task, not the intermediate
    refinement text.
    """
    task = TaskRepresentation.start(
        embedder=semantic_embedder, initial_user_text="Please check my inbox and reply to urgent emails"
    )
    # Deliberately shares real vocabulary ("reply", "emails") with the
    # initial text, since FakeSemanticEmbedder is bag-of-words and needs
    # literal word overlap to register similarity — unlike real MiniLM,
    # which understands paraphrase without shared vocabulary.
    opened1 = task.update_from_user_turn(
        user_text="reply to the emails briefly please", boundary_classifier=semantic_classifier
    )
    assert opened1 is False
    assert task.current_task_text == "Please check my inbox and reply to urgent emails"

    opened2 = task.update_from_user_turn(
        user_text="actually cancel my streaming subscription too", boundary_classifier=semantic_classifier
    )
    assert opened2 is True
