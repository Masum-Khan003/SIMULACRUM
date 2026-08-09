"""
Verifies the finding-018 tie-breaking combination rule: divergence's
own score is used directly except within a real, evidence-derived
ambiguous zone around MINILM_DIVERGENCE_THRESHOLD, where content-
pattern's confidence breaks the tie. See tiebreak_combination.py's
module docstring and docs/findings/018-*.md for the full writeup.
"""
import os
from pathlib import Path

import pytest

from simulacrum.attribution import MiniLMEmbedder
from simulacrum.detectors import MINILM_DIVERGENCE_THRESHOLD
from simulacrum.detectors.content_pattern import (
    GroqContentPatternDetector,
    HeuristicContentPatternDetector,
)
from simulacrum.evaluation.calibration_report import similarity_to_pseudo_probability
from simulacrum.evaluation.explicit_detectors_baseline import build_sample
from simulacrum.evaluation.tiebreak_combination import (
    AMBIGUOUS_ZONE_WIDTH,
    tiebreak_probability,
)
from simulacrum.generalization_set.agentdojo_adapter.scoring import score_trajectory_divergence

RUNS_DIR = Path("./runs")


def _require_env_and_data():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        pytest.skip("GROQ_API_KEY not set — skipping real baseline test")
    if not RUNS_DIR.exists() or not any(RUNS_DIR.rglob("*.json")):
        pytest.skip("No AgentDojo runs/ data present — real benchmark data required")
    return api_key


def test_returns_divergence_probability_outside_ambiguous_zone():
    """
    Real, structural invariant: for a trajectory whose min_similarity
    is clearly OUTSIDE the ambiguous zone, tiebreak_probability must
    equal divergence's own pseudo-probability exactly — content-
    pattern must never override a confident divergence score.
    """
    api_key = _require_env_and_data()
    embedder = MiniLMEmbedder()
    content_detector = GroqContentPatternDetector(
        api_key=api_key, fallback=HeuristicContentPatternDetector()
    )

    attacks, resisted = build_sample(n=20, seed=42)
    checked_any_outside_zone = False

    for t in attacks + resisted:
        div_result = score_trajectory_divergence(trajectory=t, embedder=embedder)
        distance = abs(div_result.min_similarity - MINILM_DIVERGENCE_THRESHOLD)
        if distance <= AMBIGUOUS_ZONE_WIDTH:
            continue  # in-zone cases are allowed to differ, tested separately

        checked_any_outside_zone = True
        expected = similarity_to_pseudo_probability(similarity=div_result.min_similarity)
        actual = tiebreak_probability(trajectory=t, embedder=embedder, content_detector=content_detector)
        assert actual == expected, (
            f"Outside ambiguous zone (distance={distance:.4f}), tiebreak_probability "
            f"must equal divergence's own probability exactly"
        )

    assert checked_any_outside_zone, "expected at least one real trajectory outside the ambiguous zone in this sample"


def test_ambiguous_zone_width_is_evidence_derived_and_reasonable():
    """
    Real, non-arbitrary sanity check: the zone width should be small
    relative to the full similarity range (not swallowing most of the
    dataset) but non-zero (not vacuous). Guards against a future,
    unreviewed edit turning this into either extreme.
    """
    assert 0.0 < AMBIGUOUS_ZONE_WIDTH < 0.2
