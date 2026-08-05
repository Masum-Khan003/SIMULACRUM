"""
Tiered response decision (§13): allow / flag / require-approval / block.

Severity proxy, stated as an honest placeholder: §13's table describes
gradation by SCORE MAGNITUDE (elevated/high/very-high), but current
detectors are boolean (flagged or not), not continuous scores. Using
COUNT OF DISTINCT DETECTORS FLAGGED as the severity proxy: 0=none,
1=elevated, 2+=high. This is a coarse stand-in pending real calibration
(§15) against a labeled corpus with actual score distributions — same
honesty discipline as every other placeholder threshold in this
project (boundary/divergence thresholds, rate thresholds, etc).
"""
from __future__ import annotations

from enum import Enum

from simulacrum.risk_tiers import RiskTier


class ResponseTier(Enum):
    ALLOW = "allow"
    FLAG = "flag"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


def decide_response_tier(
    *, flagged_detector_count: int, tool_tier: RiskTier
) -> ResponseTier:
    """
    §13's table, applied with the detector-count severity proxy:
      - 0 flags -> ALLOW
      - IRREVERSIBLE_HIGH_VALUE + ANY flag -> BLOCK outright (§13: "any
        score on a high-value-irreversible tool")
      - IRREVERSIBLE_LOW_VALUE + ANY flag -> REQUIRE_APPROVAL (§13:
        "any score on irreversible tool above flag threshold")
      - READ_ONLY/REVERSIBLE_WRITE + 1 flag -> FLAG (proceeds, marked
        for review)
      - READ_ONLY/REVERSIBLE_WRITE + 2+ flags -> REQUIRE_APPROVAL
        ("high score" proxy)
    """
    if flagged_detector_count == 0:
        return ResponseTier.ALLOW

    if tool_tier is RiskTier.IRREVERSIBLE_HIGH_VALUE:
        return ResponseTier.BLOCK

    if tool_tier is RiskTier.IRREVERSIBLE_LOW_VALUE:
        return ResponseTier.REQUIRE_APPROVAL

    # READ_ONLY / REVERSIBLE_WRITE
    if flagged_detector_count >= 2:
        return ResponseTier.REQUIRE_APPROVAL
    return ResponseTier.FLAG
