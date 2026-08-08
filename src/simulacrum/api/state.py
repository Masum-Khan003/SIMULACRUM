"""
Process-wide singleton state for the API (§21). Registries, the
circuit breaker, and the approval queue are shared across requests —
this IS the real deployment shape (§12 explicitly scopes single-
instance MVP). TaskRepresentation instances are per-session and kept
in an in-process dict, since they're genuinely process-local mutable
state, not shared infrastructure like the session store.

Uses RedisSessionStore (not InMemorySessionStore) — proves the real
Redis path end-to-end via HTTP, not just via pytest.
"""
from __future__ import annotations

import os

from simulacrum.attribution import FakeSemanticEmbedder, TaskRepresentation
from simulacrum.config import get_settings
from simulacrum.detectors import build_default_schema_registry
from simulacrum.explainability import GroqExplainer, TemplateExplainer
from simulacrum.interception import build_default_registry
from simulacrum.interception.circuit_breaker import CircuitBreaker
from simulacrum.risk_tiers import ToolRegistry
from simulacrum.session import RedisSessionStore
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType
from simulacrum.tier_engine import ApprovalQueue


class AppState:
    def __init__(self) -> None:
        settings = get_settings()
        self.tier_registry = ToolRegistry()
        self.tool_registry = build_default_registry(tier_registry=self.tier_registry)
        self.schema_registry = build_default_schema_registry()
        self.session_store = RedisSessionStore(redis_url=settings.redis_url)
        self.circuit_breaker = CircuitBreaker()
        self.approval_queue = ApprovalQueue()

        # Real MiniLM is opt-in (SIMULACRUM_USE_REAL_EMBEDDINGS=1),
        # NOT the default, deliberately — sentence-transformers pulls
        # in torch, a heavy dependency that would break the lightweight
        # fresh-venv install we explicitly verified (§22). Calibrated
        # against real data: on-topic similarity 0.30-0.71 (mean 0.51),
        # off-topic -0.03-0.15 (mean 0.04), clean separation, no
        # overlap, across 360 real samples (cleared
        # MIN_CALIBRATION_SAMPLES). Requires `pip install -e ".[ml]"`.
        from simulacrum.attribution import EmbeddingBoundaryClassifier, GroqBoundaryClassifier
        from simulacrum.detectors import FAKE_DIVERGENCE_THRESHOLD, MINILM_DIVERGENCE_THRESHOLD

        if os.environ.get("SIMULACRUM_USE_REAL_EMBEDDINGS") == "1":
            from simulacrum.attribution import MiniLMEmbedder

            self.embedder = MiniLMEmbedder(hf_token=settings.hf_token)
            self.divergence_threshold = MINILM_DIVERGENCE_THRESHOLD
        else:
            self.embedder = FakeSemanticEmbedder()
            self.divergence_threshold = FAKE_DIVERGENCE_THRESHOLD

        # §20: explanation layer is optional, fails open to the
        # deterministic template when no key is configured — same
        # "absence is valid config" pattern as groq_api_key itself.
        if settings.groq_api_key:
            self.explainer = GroqExplainer(api_key=settings.groq_api_key)
        else:
            self.explainer = TemplateExplainer()

        # §06/gap 2 boundary detection: real Groq reasoning as primary,
        # embedding fallback always available. Uses this same
        # AppState-level embedder, so boundary detection'''s fallback
        # is consistent with whatever divergence scoring is using.
        boundary_fallback = EmbeddingBoundaryClassifier(embedder=self.embedder, threshold=0.15)
        if settings.groq_api_key:
            self.boundary_classifier = GroqBoundaryClassifier(
                api_key=settings.groq_api_key, fallback=boundary_fallback
            )
        else:
            self.boundary_classifier = boundary_fallback

        # §04/§10 goal drift: session-level, NOT per-call. Fails open
        # to NullDriftDetector (never flags) when no key is configured
        # — the correct conservative default for this specific,
        # least-certain detector (see goal_drift.py docstring).
        from simulacrum.attribution import GroqDriftDetector, NullDriftDetector

        drift_fallback = NullDriftDetector()
        if settings.groq_api_key:
            self.drift_detector = GroqDriftDetector(
                api_key=settings.groq_api_key, fallback=drift_fallback
            )
        else:
            self.drift_detector = drift_fallback

        # §03/§12: real async/background drift scheduler, closing the
        # gap where only an on-demand endpoint existed. Started/stopped
        # via FastAPI lifespan events in app.py, not constructed here.
        from simulacrum.attribution.drift_scheduler import DriftScheduler

        self.drift_scheduler = DriftScheduler(drift_detector=self.drift_detector)

        # Finding 007 fix: content-pattern detector closes the real,
        # complete blind spot (in-baseline tool + camouflaged short
        # payload evaded all 5 prior detectors). REQUIRED, no
        # implicit no-op default — same discipline as every other
        # detector in this system.
        from simulacrum.detectors import GroqContentPatternDetector, HeuristicContentPatternDetector

        content_pattern_fallback = HeuristicContentPatternDetector()
        if settings.groq_api_key:
            self.content_pattern_detector = GroqContentPatternDetector(
                api_key=settings.groq_api_key, fallback=content_pattern_fallback
            )
        else:
            self.content_pattern_detector = content_pattern_fallback

        self._task_representations: dict[str, TaskRepresentation] = {}
        self._task_types: dict[str, TaskType] = {}

    def start_session(self, *, session_id: str, task_type: TaskType) -> None:
        initial_text = TASK_INITIAL_USER_TEXT[task_type]
        self._task_representations[session_id] = TaskRepresentation.start(
            embedder=self.embedder, initial_user_text=initial_text
        )
        self._task_types[session_id] = task_type

    def get_task_representation(self, *, session_id: str) -> TaskRepresentation:
        try:
            return self._task_representations[session_id]
        except KeyError:
            raise UnknownSessionError(
                f"Session '{session_id}' not found — call POST /sessions first."
            ) from None

    def get_task_type(self, *, session_id: str) -> TaskType:
        try:
            return self._task_types[session_id]
        except KeyError:
            raise UnknownSessionError(
                f"Session '{session_id}' not found — call POST /sessions first."
            ) from None

    def get_active_sessions_for_drift_check(self):
        """
        Real data source for DriftScheduler'''s background loop:
        every currently-tracked session'''s real task text and real
        call history from the actual session store. Returns a list
        (not a generator) since the scheduler iterates it once per
        poll cycle and we want a stable snapshot, not a live cursor
        into a dict that could mutate mid-iteration.
        """
        sessions = []
        for session_id, task_repr in self._task_representations.items():
            calls = self.session_store.get_calls(session_id=session_id)
            call_descriptions = tuple(
                f"{c.tool_name}({', '.join(f'{k}={v}' for k, v in c.params.items())})" for c in calls
            )
            sessions.append((session_id, task_repr.current_task_text, call_descriptions))
        return sessions


class UnknownSessionError(RuntimeError):
    pass


app_state = AppState()
