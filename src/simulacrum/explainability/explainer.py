"""
Explainability layer (§14, §20's optional explanation-layer row): "why
was this blocked?" needs a real answer for a human approver to act on.

Two implementations behind one Protocol:
  - GroqExplainer: real LLM-generated natural-language explanation,
    via Groq's free-tier hosted API (§20: "fails open to a
    deterministic template on any failure").
  - TemplateExplainer: deterministic, dependency-free fallback —
    always correct, always available, used both as the designed
    fail-open path AND directly whenever an LLM explanation isn't
    wanted (e.g. most tests, to avoid real network calls).

Per §06's own honesty discipline: attribution is stated as a
correlational hypothesis, never a certainty — both explainers must
phrase things that way, not as unqualified assertions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExplanationContext:
    """Everything an explainer needs — deliberately just data, no
    dependency on detector/interceptor types, so this module has no
    import-cycle risk with the rest of the system."""
    tool_name: str
    response_tier: str  # e.g. "block", "require_approval"
    flagged_reasons: tuple[str, ...]  # e.g. ("schema_violation: missing flight_id",)


class Explainer(Protocol):
    def explain(self, *, context: ExplanationContext) -> str: ...


class TemplateExplainer:
    """
    Deterministic, dependency-free. This is the REQUIRED fallback
    (§20) — must never raise, must never call the network.
    """

    def explain(self, *, context: ExplanationContext) -> str:
        if not context.flagged_reasons:
            return (
                f"The call to '{context.tool_name}' was {context.response_tier} "
                f"with no specific detector findings recorded."
            )
        reasons_text = "; ".join(context.flagged_reasons)
        return (
            f"The call to '{context.tool_name}' was {context.response_tier} because "
            f"the following was observed: {reasons_text}. This is a correlational "
            f"finding, not a certainty of malicious intent."
        )


class GroqExplainer:
    """
    Real LLM-generated explanation via Groq's free-tier API. Fails
    OPEN to TemplateExplainer on ANY exception — a broken/unreachable
    LLM call must never break the explanation feature entirely, per
    §20's own stated design.
    """

    def __init__(self, *, api_key: str, model: str = "llama-3.3-70b-versatile") -> None:
        # Import here, not at module top-level, so importing this
        # MODULE never requires the groq package or network access —
        # only actually constructing a GroqExplainer does. Keeps
        # TemplateExplainer (and this file's own import) fully
        # dependency-free for tests that don't need the real client.
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self._model = model
        self._fallback = TemplateExplainer()

    def explain(self, *, context: ExplanationContext) -> str:
        try:
            reasons_text = "; ".join(context.flagged_reasons) or "no specific findings recorded"
            prompt = (
                f"A tool-calling AI agent's action was intercepted by a security "
                f"guardrail. Tool: '{context.tool_name}'. Decision: "
                f"'{context.response_tier}'. Findings: {reasons_text}. In 1-2 "
                f"sentences, explain to a human approver why this was flagged, "
                f"stating clearly this is a correlational finding, not a proven "
                f"certainty of malicious intent."
            )
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                timeout=5,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            # Fails open to the deterministic template — never lets a
            # broken/slow/rate-limited API call break explainability.
            return self._fallback.explain(context=context)
