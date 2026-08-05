"""
Verifies §07: no tool is callable without an assigned risk tier, and
fail-policy is correctly derived per tier (fail-open for read-only/
reversible, fail-closed for irreversible).
"""
import pytest

from simulacrum.risk_tiers import (
    DuplicateRegistrationError,
    FailPolicy,
    RiskTier,
    ToolRegistry,
    UnregisteredToolError,
)


@pytest.fixture
def registry():
    return ToolRegistry()


def test_unregistered_tool_raises(registry):
    with pytest.raises(UnregisteredToolError, match="never_registered"):
        registry.get(tool_name="never_registered")


def test_register_and_get_roundtrip(registry):
    registry.register(tool_name="read_inbox", tier=RiskTier.READ_ONLY)
    reg = registry.get(tool_name="read_inbox")
    assert reg.tier is RiskTier.READ_ONLY


def test_duplicate_registration_raises(registry):
    registry.register(tool_name="send_email", tier=RiskTier.IRREVERSIBLE_LOW_VALUE)
    with pytest.raises(DuplicateRegistrationError, match="send_email"):
        registry.register(tool_name="send_email", tier=RiskTier.READ_ONLY)


@pytest.mark.parametrize(
    "tier,expected_policy",
    [
        (RiskTier.READ_ONLY, FailPolicy.FAIL_OPEN),
        (RiskTier.REVERSIBLE_WRITE, FailPolicy.FAIL_OPEN),
        (RiskTier.IRREVERSIBLE_LOW_VALUE, FailPolicy.FAIL_CLOSED),
        (RiskTier.IRREVERSIBLE_HIGH_VALUE, FailPolicy.FAIL_CLOSED),
    ],
)
def test_fail_policy_derived_correctly(registry, tier, expected_policy):
    registry.register(tool_name="some_tool", tier=tier)
    reg = registry.get(tool_name="some_tool")
    assert reg.fail_policy is expected_policy


def test_registration_is_frozen(registry):
    reg = registry.register(tool_name="delete_data", tier=RiskTier.IRREVERSIBLE_HIGH_VALUE)
    with pytest.raises(AttributeError):
        reg.tier = RiskTier.READ_ONLY
