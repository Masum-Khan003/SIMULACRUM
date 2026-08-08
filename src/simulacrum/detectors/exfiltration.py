"""
Exfiltration detector (§04/§09 session-level): "an authorized outbound
tool used with anomalous content or frequency." Direct structural
analog to Palimpsest's low-and-slow exfiltration / hit-count detector.

Two independent signals: frequency (any outbound-tool call count) and
content (anomalous param-value size — a crude, honestly-documented
proxy, not semantic content analysis).
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.session import SessionStore

OUTBOUND_TOOLS = frozenset({"reply_to_email", "set_forwarding_rule", "send_payment"})

# Real, evidence-based recalibration (finding 014, same root cause as
# loop_rate.py's DEFAULT_RATE_THRESHOLD): the OLD threshold of 3 was
# implicitly calibrated for task_sim's previous fixed-2-call-per-
# session regime, where reply_to_email (the only outbound tool task_sim
# legitimately uses) was never called more than once. Now that
# task_sim produces realistic variable-length sessions, legitimate
# sessions can genuinely call reply_to_email up to 6 times -- measured
# directly, real data: max outbound-tool count across 2500 real
# generated sessions (500 seeds x 5 task types) = 6. Set to 7, one
# above the real observed legitimate max, same "safe margin above
# observed max" discipline as finding 008's percentile derivation and
# loop_rate.py's own identical fix.
DEFAULT_OUTBOUND_FREQUENCY_THRESHOLD = 7
DEFAULT_CONTENT_SIZE_THRESHOLD = 150


@dataclass(frozen=True)
class ExfiltrationResult:
    tool_name: str
    outbound_call_count: int
    is_frequency_exceeded: bool
    is_content_anomalous: bool
    anomalous_params: frozenset[str]

    @property
    def is_flagged(self) -> bool:
        return self.is_frequency_exceeded or self.is_content_anomalous


def check_exfiltration(
    *,
    session_store: SessionStore,
    session_id: str,
    tool_name: str,
    params: dict[str, str],
    frequency_threshold: int = DEFAULT_OUTBOUND_FREQUENCY_THRESHOLD,
    content_size_threshold: int = DEFAULT_CONTENT_SIZE_THRESHOLD,
) -> ExfiltrationResult:
    if tool_name not in OUTBOUND_TOOLS:
        return ExfiltrationResult(
            tool_name=tool_name,
            outbound_call_count=0,
            is_frequency_exceeded=False,
            is_content_anomalous=False,
            anomalous_params=frozenset(),
        )

    prior_outbound = [
        a for a in session_store.get_attempts(session_id=session_id)
        if a.call.tool_name in OUTBOUND_TOOLS
    ]
    outbound_call_count = len(prior_outbound) + 1

    anomalous_params = frozenset(
        k for k, v in params.items() if len(v) > content_size_threshold
    )

    return ExfiltrationResult(
        tool_name=tool_name,
        outbound_call_count=outbound_call_count,
        is_frequency_exceeded=outbound_call_count >= frequency_threshold,
        is_content_anomalous=bool(anomalous_params),
        anomalous_params=anomalous_params,
    )
