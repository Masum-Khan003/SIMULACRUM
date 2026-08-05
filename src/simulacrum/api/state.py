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
        self.embedder = FakeSemanticEmbedder()
        # §20: explanation layer is optional, fails open to the
        # deterministic template when no key is configured — same
        # "absence is valid config" pattern as groq_api_key itself.
        if settings.groq_api_key:
            self.explainer = GroqExplainer(api_key=settings.groq_api_key)
        else:
            self.explainer = TemplateExplainer()
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
