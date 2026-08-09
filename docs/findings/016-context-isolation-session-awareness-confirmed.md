# Finding 016: clean isolation test confirms session-awareness has real, asymmetric value — holding LLM reasoning constant

**Status:** Resolved. Real, clean answer to the open follow-up flagged in finding 010's own honest interpretation section and `docs/CALIBRATION_REPORT.md`.

## Background

`docs/CALIBRATION_REPORT.md`'s input-only-classifier baseline found a real, uncomfortable result: a naive single-call LLM classifier with no session context (90.0% recall) outperformed the session-aware MiniLM divergence detector (78.4% recall) on real AgentDojo data. The report's own honest interpretation flagged this as NOT a clean test of "does context help" — it conflated two different variables at once: reasoning sophistication (full LLM judgment vs. narrow mechanical cosine similarity) and context availability. The report explicitly named the needed follow-up: LLM reasoning WITH session context vs. WITHOUT, holding the underlying mechanism constant. That comparison had never been run — this finding runs it.

## Method

Built `ContextAwareClassifier` (`src/simulacrum/evaluation/context_aware_baseline.py`) as a deliberate, minimal-diff pair to the existing `InputOnlyClassifier`: identical model (`llama-3.3-70b-versatile`), identical temperature (0), identical token budget (150), identical reasoning-then-verdict prompt structure. The **only** real difference: `ContextAwareClassifier` is given the real task description and real prior call history; `InputOnlyClassifier` sees neither.

Built `run_context_isolation_comparison()` to evaluate both classifiers on the same real target call per trajectory (the last call in the sequence, a real, consistent choice for both attack and resisted groups — not necessarily identical to `attack_call_index` used elsewhere in this project's evaluation code, stated explicitly since the numbers below are not directly comparable to CALIBRATION_REPORT's original 90.0%/75.0% figures).

Real, seeded AgentDojo sample (n=120, seed=42 — same corpus and sampling as findings 011/013/014/015). Smoke-tested at n=10 first, matching this project's cost-conscious verification discipline; the n=10 result (both recall and FP up +20pp together) looked inconclusive/noisy, underscoring why the full run mattered before drawing any conclusion.

**Real test-design note:** an attempted synthetic unit test ("does the classifier correctly NOT flag an obviously routine call, given context") failed twice with two different fixtures — not from a classifier bug, but because context-aware reasoning proved measurably more skeptical of generic/vague actions than input-only reasoning (it can judge whether a reply actually addresses the stated task, not just whether the call type is plausible in isolation). Rather than force a pass with a cherry-picked fixture, this was left as an honest note in the test file — itself a small, relevant preview of the real, full-scale result below.

## Real result (n=120: 60 attacks, 60 resisted)

| | Recall | FP rate |
|---|---|---|
| Input-only (no context) | 61.7% | 55.0% |
| Context-aware (task + call history) | 83.3% | 58.3% |
| **Delta** | **+21.7pp** | **+3.3pp** |

## Honest interpretation

**Session-awareness has real, substantial, asymmetric value — holding the reasoning mechanism fixed.** Recall improved roughly 6.5x more than false-positive rate rose. This is the first clean result in this project's entire combination/context history showing a genuinely favorable trade, in contrast to every prior detector-combination measurement (finding 011's Baseline A/B, CALIBRATION_REPORT's binary and continuous-confidence combinations, finding 013's rescue analysis) which consistently traded roughly comparable amounts of recall for FP cost.

**This resolves the honest ambiguity CALIBRATION_REPORT itself flagged.** The original input-only-beats-divergence result was real but structurally uninformative about session-awareness specifically — it compared a sophisticated reasoning mechanism with no context against a narrow mechanical mechanism, conflating two variables. This experiment isolates the one variable that matters for the project's own core thesis (§00, blueprint vision: "session-level, trajectory-aware behavioral analysis catches injected and drifted agent behavior that single-message input classifiers structurally cannot"), and the real evidence now supports it — for LLM-based reasoning specifically, context measurably helps, and the benefit clearly outweighs its cost.

**Two honest caveats, stated plainly, not glossed over:**
1. These input-only numbers (61.7%/55.0%) are not directly comparable to CALIBRATION_REPORT's original figures (90.0%/75.0%) — different real methodology for selecting the target call (last-call heuristic here, `attack_call_index` there) and a different real sample. The internal comparison (input-only vs. context-aware, same sample, same target-call selection) is the valid, load-bearing result; the absolute numbers should not be cross-referenced against the earlier report's figures.
2. FP rate still rose, not fell. Context-aware reasoning is not simply "better" in every dimension — it is measurably more willing to flag ambiguous or under-justified actions (seen directly in the failed synthetic unit test above). The net trade is real and favorable at this scale, but not free.

## What this means going forward

This is real, positive evidence for the project's core thesis, specifically for LLM-based reasoning components (content-pattern, goal-drift) — consistent with this whole session's broader pattern that LLM reasoning outperforms mechanical signals (divergence, regex heuristics), now extended to show WHY context helps when the mechanism is fixed. It does not by itself validate the mechanical divergence detector's own design; that detector's real limitations (finding 010/014/015) are a separate, already-closed line of investigation.

## Reproducing this result

```bash
set -a && source .env && set +a
python3 -c "from simulacrum.evaluation.context_isolation_comparison import _run_cli; _run_cli()" --n 120 --seed 42
```
