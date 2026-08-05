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

            self.embedder = MiniLMEmbedder()
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


class UnknownSessionError(RuntimeError):
    pass


app_state = AppState()
