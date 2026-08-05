"""
Shared ground-truth record type for all attack classes (§05, §08).
One shared dataclass, not one per attack class — same "don't let
independently-written things silently diverge" discipline as
task_sim's own single-generator rule (finding 011).

injected_tool_name is optional (None default) because not every
attack class substitutes a whole different tool — param_tampering
corrupts the EXPECTED call's params instead, so it has no separate
"which tool" to record.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.task_sim import Session


@dataclass(frozen=True)
class LabeledAttackSession:
    session: Session
    attack_call_index: int
    injected_document_text: str
    ground_truth_label: str
    injected_tool_name: str | None = None
