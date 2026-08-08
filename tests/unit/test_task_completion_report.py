"""
Verifies task-completion-rate cost reporting (§02 MVP scope item,
found missing via blueprint re-audit). Real evidence this session: the
first real measurement found a genuine 20% false-positive task-cost
rate, traced to a real regex bug in the heuristic content-pattern
fallback (flagged ANY single email address, not genuine bulk-data
shape) -- fixed, re-measured at 0% after the fix.
"""
from simulacrum.attribution import FakeSemanticEmbedder
from simulacrum.detectors import (
    FAKE_DIVERGENCE_THRESHOLD,
    HeuristicContentPatternDetector,
    build_default_schema_registry,
)
from simulacrum.evaluation.task_completion_report import run_task_completion_report
from simulacrum.interception import build_default_registry
from simulacrum.risk_tiers import ToolRegistry


def test_real_task_completion_rate_is_now_clean_with_default_config():
    """
    THE real regression guard for the fixed content-pattern regex bug:
    default production configuration (fake embedder, heuristic
    fallback) should show ZERO false-positive task disruption on
    legitimate task_sim sessions. If this regresses, a future change
    reintroduced the overly-broad single-email-match bug (or a new,
    different false-positive source).
    """
    embedder = FakeSemanticEmbedder()
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    content_detector = HeuristicContentPatternDetector()

    report = run_task_completion_report(
        embedder=embedder, tool_registry=tool_registry, tier_registry=tier_registry,
        schema_registry=schema_registry, content_pattern_detector=content_detector,
        divergence_threshold=FAKE_DIVERGENCE_THRESHOLD, sessions_per_task_type=20,
    )

    assert report.total_sessions == 100  # 5 task types x 20 sessions
    assert report.disrupted == 0, (
        f"Real false-positive task disruption detected: {report.disrupted}/{report.total_sessions} "
        f"sessions disrupted. This may be a regression of the content-pattern regex fix."
    )
    assert report.clean_completion_rate == 1.0
