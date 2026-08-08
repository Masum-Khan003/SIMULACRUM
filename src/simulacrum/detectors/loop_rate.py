"""
Tool-loop-rate detector (§04/§09 session-level, gap 5): runaway
repeated calls to the same tool, with the retry-vs-evasion split gap 5
requires — retry-after-block-with-varied-params (evasion, high weight)
vs retry-after-error (benign, low weight) — distinguished via the
tool's own outcome, not conflated into one undifferentiated rate signal.

A retry after PENDING_APPROVAL (held for human sign-off, not actively
blocked) is neither evasion nor benign-error-retry — it's a distinct,
expected situation (e.g. a user resubmitting with a small correction
while waiting on approval) and must not be misclassified as either.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.session import CallOutcome, SessionStore

# Real, evidence-based recalibration (finding 014, variable-length
# task_sim follow-up): the OLD threshold of 3 was implicitly calibrated
# for task_sim's previous fixed-2-call-per-session regime, where no
# legitimate session ever called the same tool twice. Now that
# task_sim produces realistic, variable-length sessions (finding 010's
# root-cause fix), legitimate sessions can genuinely repeat a tool up
# to 6 times (e.g. replying to 6 emails in one inbox-triage session) --
# measured directly, real data: max same-tool repeat count across 2500
# real generated sessions (500 seeds x 5 task types) = 6. Set to 7, one
# above the real observed legitimate max, same "safe margin above
# observed max" discipline as finding 008's percentile threshold
# derivation. Real loop-evasion attacks (loop_evasion.py) are still
# caught independently via is_evasion_retry (outcome-based: BLOCKED +
# varied params), which does NOT depend on this raw-count threshold at
# all -- so raising this threshold does not weaken evasion detection.
DEFAULT_RATE_THRESHOLD = 7


@dataclass(frozen=True)
class LoopRateResult:
    tool_name: str
    same_tool_attempt_count: int
    is_rate_exceeded: bool
    is_evasion_retry: bool
    is_benign_retry: bool

    @property
    def is_flagged(self) -> bool:
        return self.is_rate_exceeded or self.is_evasion_retry


def check_tool_loop_rate(
    *,
    session_store: SessionStore,
    session_id: str,
    tool_name: str,
    params: dict[str, str],
    rate_threshold: int = DEFAULT_RATE_THRESHOLD,
) -> LoopRateResult:
    prior_same_tool = [
        a for a in session_store.get_attempts(session_id=session_id) if a.call.tool_name == tool_name
    ]
    same_tool_attempt_count = len(prior_same_tool) + 1

    is_evasion_retry = False
    is_benign_retry = False
    if prior_same_tool:
        last = prior_same_tool[-1]
        params_changed = last.call.params != params
        if last.outcome is CallOutcome.BLOCKED and params_changed:
            is_evasion_retry = True
        elif last.outcome is CallOutcome.TOOL_ERROR and params_changed:
            is_benign_retry = True
        # CallOutcome.PENDING_APPROVAL and CallOutcome.ALLOWED are
        # deliberately NOT classified as either evasion or benign —
        # neither is the adversarial or error-correction signature.

    return LoopRateResult(
        tool_name=tool_name,
        same_tool_attempt_count=same_tool_attempt_count,
        is_rate_exceeded=same_tool_attempt_count >= rate_threshold,
        is_evasion_retry=is_evasion_retry,
        is_benign_retry=is_benign_retry,
    )
