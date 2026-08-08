"""
Sensitive-parameter redaction (§19): a redaction layer between the
interception point and every log/metric/export sink, treated as a
day-one requirement per the blueprint -- direct extension of
Palimpsest's own §17 IP-hashing discipline to substantially
higher-stakes content (real email bodies, payment details, etc.).

Real, current exposure this closes: GroqExplainer/GroqContentPatternDetector/
GroqDriftDetector's reasoning text often quotes or directly references
the real param content it's reasoning about (an LLM naturally echoes
back what it's analyzing) -- this reasoning text flows UNREDACTED into
HTTP API responses (explanation/reasoning fields) with zero scrubbing
applied. Reuses the same real, tested structured-data regex patterns
already built for content_pattern.py's heuristic fallback, rather than
duplicating pattern-matching logic.
"""
from __future__ import annotations

import re

# Reused, not duplicated, from detectors/content_pattern.py's own
# real, tested patterns -- same real structural indicators (email,
# SSN, card, password/credential keywords), applied here for
# REDACTION rather than detection. Kept as a separate copy (not a
# shared import) deliberately: redaction and detection are different
# concerns with different failure costs (a detection false-negative
# misses an attack; a redaction false-negative leaks real PII) -- a
# future change to one module's patterns should not silently change
# the other's behavior without an explicit, reviewed decision.
_REDACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[REDACTED_CARD]"),
    (
        re.compile(
            r"\b(?:password|api[_\s-]?key|secret|credential|token)s?\s*[:=]?\s*\S+",
            re.IGNORECASE,
        ),
        "[REDACTED_CREDENTIAL]",
    ),
]


def redact_text(*, text: str) -> str:
    """
    Applies all real redaction patterns to arbitrary text (e.g. an
    LLM's reasoning output). Order matters: credential-keyword
    matching runs LAST so it doesn't accidentally consume an email
    address that happens to appear near a keyword like "password" in
    unrelated context (e.g. "password reset email: user@site.com" --
    the email pattern should still match the email portion cleanly
    before the credential pattern's broader match could swallow it).
    """
    result = text
    for pattern, replacement in _REDACTION_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_params(*, params: dict[str, str]) -> dict[str, str]:
    """Redacts every value in a params dict -- used before params
    themselves (not just LLM reasoning about them) reach any log/
    export sink."""
    return {k: redact_text(text=v) for k, v in params.items()}
