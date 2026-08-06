"""
Verifies §08 Layer 3 (held-out generalization set): does the
recalibrated MINILM_DIVERGENCE_THRESHOLD (finding 008's fix) actually
generalize, or does it overfit to attack_suite/task_sim's specific
param values and seeds used during calibration?

Uses genuinely disjoint data: mutated_attacks.py's param variants
(never used in calibration) for the attack side, and task_sim seeds
100-129 (calibration used seeds 0-69) for the legitimate-traffic side.

Requires real MiniLM (ml extra) — skips cleanly without it.
"""
import random

import pytest

from simulacrum.generalization_set.mutated_attacks import _PARAM_VARIANTS, generate_mutated_attack
from simulacrum.attribution import TaskRepresentation
from simulacrum.detectors import MINILM_DIVERGENCE_THRESHOLD, check_param_divergence
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType, generate_session


def _require_minilm():
    try:
        from simulacrum.attribution import MiniLMEmbedder
        return MiniLMEmbedder()
    except ImportError:
        pytest.skip("sentence-transformers not installed (requires [ml] extra)")


@pytest.fixture(scope="module")
def embedder():
    return _require_minilm()


def test_recalibrated_threshold_generalizes_to_held_out_attack_variants(embedder):
    """
    THE real generalization check: mutated_attacks.py's param variants
    were NEVER used to derive MINILM_DIVERGENCE_THRESHOLD (0.3030,
    from 420 samples using attack_suite's fixed params). If the
    threshold overfit to those specific values, this would show real
    recall degradation on genuinely different-but-equivalent params.
    """
    total = detected = 0
    for task_type in TaskType:
        task = TaskRepresentation.start(
            embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[task_type]
        )
        for tool_name in _PARAM_VARIANTS:
            for seed in range(15):
                attack = generate_mutated_attack(tool_name=tool_name, rng=random.Random(seed))
                result = check_param_divergence(
                    task_representation=task, tool_name=attack.tool_name, params=attack.params,
                    threshold=MINILM_DIVERGENCE_THRESHOLD,
                )
                total += 1
                if result.is_divergent:
                    detected += 1
    assert total == 180
    assert detected == total, (
        f"Generalization recall degraded on held-out attack variants: {detected}/{total}. "
        f"This could mean the threshold overfit to attack_suite's specific param values."
    )


def test_recalibrated_threshold_no_false_positives_on_held_out_normal_traffic(embedder):
    """
    Held-out check on the LEGITIMATE side: seeds 100-129, genuinely
    disjoint from the 0-69 range used during MINILM_DIVERGENCE_THRESHOLD's
    calibration (see param_divergence.py's finding-008 comment).
    """
    false_positives = []
    for task_type in TaskType:
        task = TaskRepresentation.start(
            embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[task_type]
        )
        for seed in range(100, 130):
            session = generate_session(task_type=task_type, rng=random.Random(seed))
            for call in session.calls:
                result = check_param_divergence(
                    task_representation=task, tool_name=call.tool_name, params=call.params,
                    threshold=MINILM_DIVERGENCE_THRESHOLD,
                )
                if result.is_divergent:
                    false_positives.append((task_type.value, call.tool_name, call.params))
    assert false_positives == [], (
        f"Held-out false positives found — threshold may be too aggressive "
        f"on genuinely unseen legitimate traffic: {false_positives}"
    )
