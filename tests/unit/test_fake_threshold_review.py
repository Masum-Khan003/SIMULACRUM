"""
Reviews FAKE_DIVERGENCE_THRESHOLD for finding 008's poisoning
vulnerability (closing the last item from that finding's follow-up).
Confirms real, current headroom against FakeSemanticEmbedder's actual
similarity distribution and full attack coverage — not assumed, not
inherited from an earlier smaller measurement.
"""
import random

import pytest

from simulacrum.attack_suite import generate_injection_session
from simulacrum.attribution import FakeSemanticEmbedder, TaskRepresentation, call_topic_text, cosine_similarity
from simulacrum.detectors import FAKE_DIVERGENCE_THRESHOLD, check_param_divergence
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType, generate_session

ATTACK_TOOLS = ["send_payment", "set_forwarding_rule", "delete_data", "modify_permissions"]


def test_fake_threshold_has_real_margin_against_real_on_topic_distribution():
    embedder = FakeSemanticEmbedder()
    on_topic_similarities = []
    for task_type in TaskType:
        task = TaskRepresentation.start(embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[task_type])
        for seed in range(70):
            session = generate_session(task_type=task_type, rng=random.Random(seed))
            for call in session.calls:
                text = call_topic_text(tool_name=call.tool_name, params=call.params)
                sim = cosine_similarity(embedder.embed(text), task.current_vector)
                on_topic_similarities.append(sim)

    false_positives = [s for s in on_topic_similarities if s < FAKE_DIVERGENCE_THRESHOLD]
    assert len(false_positives) == 0, (
        f"FAKE_DIVERGENCE_THRESHOLD ({FAKE_DIVERGENCE_THRESHOLD}) now has real false "
        f"positives against measured on-topic data — headroom may have eroded, "
        f"real recalibration needed: {false_positives}"
    )


def test_fake_threshold_catches_all_real_injection_attacks():
    embedder = FakeSemanticEmbedder()
    total = detected = 0
    for task_type in TaskType:
        task = TaskRepresentation.start(embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[task_type])
        for tool_name in ATTACK_TOOLS:
            for seed in range(20):
                attack = generate_injection_session(
                    task_type=task_type, injected_tool_name=tool_name, rng=random.Random(seed)
                )
                attack_call = attack.session.calls[attack.attack_call_index]
                result = check_param_divergence(
                    task_representation=task, tool_name=attack_call.tool_name,
                    params=attack_call.params, threshold=FAKE_DIVERGENCE_THRESHOLD,
                )
                total += 1
                if result.is_divergent:
                    detected += 1
    assert total == 240
    assert detected == total, f"Recall: {detected}/{total}"
