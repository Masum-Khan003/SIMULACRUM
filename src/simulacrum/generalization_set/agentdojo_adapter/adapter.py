"""
§08 Layer 4: adapter translating AgentDojo's trajectory JSON format
into our own ToolCall/Session types, so real external-benchmark
trajectories can be run through our actual detectors.

AgentDojo's format (see runs/<model>/<suite>/<task>/<injection>/<attack>.json):
  messages: list of {role, content, tool_calls?, tool_call_id?, ...}
  Assistant messages with tool_calls contain the actual agent actions
  we care about -- these become our ToolCall objects.

Real, honest scope note: this adapter extracts TOOL CALLS AND THEIR
PARAMS from AgentDojo trajectories. It does NOT attempt to map
AgentDojo's tool/suite schema onto our RiskTier taxonomy or fake tool
registry -- those are two independent systems with different tools
entirely (AgentDojo has send_email/delete_file/search_calendar_events
etc.; we have read_inbox/reply_to_email/etc.). This adapter is used
to extract REAL, EXTERNALLY-AUTHORED tool-call sequences and REAL
task descriptions to test our DETECTORS' underlying logic (schema-
agnostic ones like param-vs-task divergence, content-pattern) against
genuinely external data -- not to run our full tiered interceptor
against AgentDojo's exact tool set.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExtractedToolCall:
    tool_name: str
    params: dict[str, str]


@dataclass(frozen=True)
class ExtractedTrajectory:
    suite_name: str
    user_task_id: str
    injection_task_id: str | None
    attack_type: str | None
    user_instruction: str
    tool_calls: tuple[ExtractedToolCall, ...]
    had_injection: bool
    attack_succeeded: bool | None
    """CRITICAL ground truth field, added after a real methodological
    finding: had_injection=True only means an injection was ATTEMPTED,
    NOT that it succeeded. AgentDojo'''s own 'security' field means the
    OPPOSITE of what the name suggests at first glance: security=True
    means the agent RESISTED (trajectory is genuinely benign, no real
    attack occurred); security=False means the injection SUCCEEDED
    (trajectory genuinely contains malicious agent behavior). This is
    the correct ground truth for whether our detectors SHOULD flag a
    trajectory -- NOT had_injection alone, which conflates attempted-
    but-resisted attacks with genuinely successful ones. Stored here
    as attack_succeeded = (security is False) for clarity, None if the
    file has no security field (utility-only baseline runs)."""


def _stringify_args(args: dict) -> dict[str, str]:
    """AgentDojo tool call args can be arbitrarily typed (lists, dicts,
    numbers) -- our param_divergence/content_pattern detectors expect
    dict[str, str], so we stringify non-string values rather than
    dropping them (dropping would silently lose real signal, e.g. a
    'recipients' list is exactly the kind of content a content-pattern
    detector needs to see)."""
    return {k: str(v) for k, v in args.items()}


def parse_agentdojo_result_file(*, path: Path) -> ExtractedTrajectory:
    with open(path) as f:
        data = json.load(f)

    user_instruction = ""
    tool_calls = []
    for message in data["messages"]:
        if message["role"] == "user" and not user_instruction:
            content = message.get("content", [])
            if content and isinstance(content, list):
                user_instruction = content[0].get("content", "")
        if message["role"] == "assistant" and message.get("tool_calls"):
            for tc in message["tool_calls"]:
                tool_calls.append(
                    ExtractedToolCall(
                        tool_name=tc["function"],
                        params=_stringify_args(tc.get("args", {})),
                    )
                )

    security_field = data.get("security")
    attack_succeeded = (security_field is False) if security_field is not None else None

    return ExtractedTrajectory(
        suite_name=data["suite_name"],
        user_task_id=data["user_task_id"],
        injection_task_id=data.get("injection_task_id"),
        attack_type=data.get("attack_type"),
        user_instruction=user_instruction,
        tool_calls=tuple(tool_calls),
        had_injection=data.get("injection_task_id") is not None,
        attack_succeeded=attack_succeeded,
    )


def load_all_trajectories(*, runs_dir: Path) -> list[ExtractedTrajectory]:
    """Walks the AgentDojo runs/ directory structure and parses every
    result JSON file found, skipping any that fail to parse (logging
    which ones, rather than silently dropping) -- real trajectories
    can have edge-case shapes (e.g. errored runs) worth knowing about."""
    trajectories = []
    skipped = []
    for path in runs_dir.rglob("*.json"):
        try:
            trajectories.append(parse_agentdojo_result_file(path=path))
        except (KeyError, json.JSONDecodeError) as e:
            skipped.append((str(path), str(e)))
    if skipped:
        print(f"Skipped {len(skipped)} unparseable files: {skipped[:5]}")
    return trajectories
