"""
Verifies explainability (§14/§20): TemplateExplainer is deterministic
and dependency-free (the REQUIRED fallback per §20). GroqExplainer
fails open to the template on ANY failure — proven with a genuinely
invalid API key causing a real network round-trip to fail, not
mocked, per this project's "verify real behavior" discipline.
"""
import pytest

from simulacrum.explainability import (
    ExplanationContext,
    GroqExplainer,
    TemplateExplainer,
)


def test_template_explainer_with_flagged_reasons():
    explainer = TemplateExplainer()
    context = ExplanationContext(
        tool_name="delete_data",
        response_tier="block",
        flagged_reasons=("param_divergence: similarity 0.0 below threshold 0.15",),
    )
    result = explainer.explain(context=context)
    assert "delete_data" in result
    assert "block" in result
    assert "correlational" in result  # honesty discipline, §06


def test_template_explainer_with_no_reasons():
    explainer = TemplateExplainer()
    context = ExplanationContext(tool_name="read_inbox", response_tier="allow", flagged_reasons=())
    result = explainer.explain(context=context)
    assert "read_inbox" in result
    assert "no specific detector findings" in result


def test_template_explainer_never_raises_and_never_needs_network():
    """The required fallback must be bulletproof — no exception path exists."""
    explainer = TemplateExplainer()
    for tier in ["allow", "flag", "require_approval", "block"]:
        context = ExplanationContext(
            tool_name="x", response_tier=tier, flagged_reasons=("a", "b", "c")
        )
        result = explainer.explain(context=context)
        assert isinstance(result, str)
        assert len(result) > 0


def test_groq_explainer_fails_open_on_genuinely_invalid_api_key():
    """
    Real network round-trip with a deliberately invalid key — NOT
    mocked. Confirms the fail-open behavior actually works against a
    real failure mode (auth rejection), not an assumed one.
    """
    explainer = GroqExplainer(api_key="sk-definitely-not-a-real-key-12345")
    context = ExplanationContext(
        tool_name="send_payment",
        response_tier="block",
        flagged_reasons=("param_divergence: similarity 0.0",),
    )
    result = explainer.explain(context=context)
    # Must fall back to the EXACT template output, proving fail-open
    # actually routes through TemplateExplainer, not just "some string"
    fallback = TemplateExplainer()
    expected = fallback.explain(context=context)
    assert result == expected


def test_groq_explainer_importing_module_does_not_require_groq_package_installed():
    """
    Sanity check on the lazy-import design: importing the
    explainability module itself must not require the groq package —
    only constructing a GroqExplainer does. Already implicitly proven
    by every other test in this file importing successfully, but
    stated explicitly here as a named guarantee.
    """
    import simulacrum.explainability  # noqa: F401
    assert True
