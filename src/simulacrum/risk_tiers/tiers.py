"""
Tool risk classification (§07). No tool is callable without an assigned
tier — this is the largest architectural departure from Palimpsest's
uniform fail-open circuit breaker.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RiskTier(Enum):
    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    IRREVERSIBLE_LOW_VALUE = "irreversible_low_value"
    IRREVERSIBLE_HIGH_VALUE = "irreversible_high_value"


class FailPolicy(Enum):
    FAIL_OPEN = "fail_open"
    FAIL_CLOSED = "fail_closed"


_TIER_FAIL_POLICY: dict[RiskTier, FailPolicy] = {
    RiskTier.READ_ONLY: FailPolicy.FAIL_OPEN,
    RiskTier.REVERSIBLE_WRITE: FailPolicy.FAIL_OPEN,
    RiskTier.IRREVERSIBLE_LOW_VALUE: FailPolicy.FAIL_CLOSED,
    RiskTier.IRREVERSIBLE_HIGH_VALUE: FailPolicy.FAIL_CLOSED,
}


@dataclass(frozen=True)
class ToolRegistration:
    tool_name: str
    tier: RiskTier

    @property
    def fail_policy(self) -> FailPolicy:
        return _TIER_FAIL_POLICY[self.tier]


class UnregisteredToolError(RuntimeError):
    """Raised when a tool is called without ever being registered."""


class DuplicateRegistrationError(RuntimeError):
    """Raised when a tool name is registered twice."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolRegistration] = {}

    def register(self, *, tool_name: str, tier: RiskTier) -> ToolRegistration:
        if tool_name in self._tools:
            raise DuplicateRegistrationError(
                f"Tool '{tool_name}' is already registered with tier "
                f"{self._tools[tool_name].tier}."
            )
        reg = ToolRegistration(tool_name=tool_name, tier=tier)
        self._tools[tool_name] = reg
        return reg

    def get(self, *, tool_name: str) -> ToolRegistration:
        try:
            return self._tools[tool_name]
        except KeyError:
            raise UnregisteredToolError(
                f"Tool '{tool_name}' has no assigned risk tier. "
                f"Every tool must be registered via ToolRegistry.register() "
                f"before it can be called."
            ) from None
