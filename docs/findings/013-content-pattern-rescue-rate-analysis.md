# Finding 013: content-pattern rescues over half of divergence's real misses, at a real, non-trivial FP cost (finding-010 follow-up)

**Status:** Resolved (measurement complete, real evidence produced). Finding 010 (Priority 1) remains OPEN — this does not close it, but provides real evidence for one of its stated candidate directions.

## Background

Finding 010 (still Priority 1, open) identified a real generalization
gap: production divergence detection underperforms on real external
(AgentDojo) data relative to internal calibration. Three tested fixes
(median/percentile aggregation, low-param exclusion, threshold+
exemption joint recalibration) all failed to find a configuration that
simultaneously matches/exceeds external recall AND preserves the
internal held-out generalization set's 0% false-positive guarantee.
One candidate direction was left unattempted: "content-pattern and
other detectors may need to carry more weight [for long, complex
sessions] — divergence-based detection has real, stated limits."

This finding tests that specific claim directly, with real data: among
the real attacks divergence alone misses, how many does content-pattern
independently catch (rescue), and at what real false-positive cost on
trajectories divergence alone correctly clears?

## Method

Built `src/simulacrum/evaluation/divergence_rescue_analysis.py`
(`run_rescue_analysis()`, real, tested, CLI wrapper matching project
convention). Uses CURRENT production divergence behavior (raw
`min_similarity`, `MINILM_DIVERGENCE_THRESHOLD=0.3030` — the
configuration finding 010's third investigation reverted to, not the
abandoned low-param-exclusion variant).

Same real, seeded AgentDojo sample as findings 011/012 (n=120,
seed=42). Smoke-tested at n=10 first (per project discipline) before
scaling to the full run.

## Real result (n=120: 60 attacks, 60 resisted)

**Divergence alone (current production):** 81.7% recall, 76.7% FP rate
on this sample (differs slightly from finding 010's verified full-
dataset numbers of 78.4%/74.7% — expected: different sample
composition, n=120 subsample vs. full 984, plus real LLM
non-determinism already measured at ~30% per-call inconsistency,
finding 009. Not a new discrepancy to chase.)

**Rescue analysis — real attacks divergence misses (11/60):**
Content-pattern independently catches **6/11 (54.5%)**.

**Cost analysis — real resisted divergence correctly clears (14/60):**
Content-pattern newly (incorrectly) flags **5/14 (35.7%)**.

## Honest interpretation

**Content-pattern carries real, independent signal — not just
correlated overlap with divergence.** A rescue rate over 50% is
substantial: more than half of divergence's specific blind spots are
covered by a mechanism that reasons about content rather than semantic
task-similarity. This is real, quantified support for candidate
direction #2 from finding 010 ("lean on content-pattern more for cases
divergence structurally can't handle").

**But the cost is real too, not negligible.** A 35.7% new-FP rate on
cases divergence already correctly clears means leaning harder on
content-pattern is a genuine trade, not a strict improvement. This is
consistent with `docs/CALIBRATION_REPORT.md`'s own earlier finding
that naive detector combination doesn't come free — recall gains
arrive with real FP cost, every time this has been measured on this
external dataset.

## What this does and does not do for finding 010

**Does not close finding 010.** The underlying generalization gap in
divergence itself is unchanged — this measures a different question
(how much does composing with content-pattern help/cost), not a fix to
divergence's own calibration.

**Does provide real, missing evidence** for one of finding 010's three
stated candidate directions, moving it from "plausible, untested" to
"real, quantified, genuinely a trade-off, not a clean win." Combined
with finding 011's Baseline A result (90.0%/83.3% recall/FP for the
plain OR-combination) and CALIBRATION_REPORT's continuous-confidence
combination work (0.2673 Brier, still short of divergence alone's
0.2333), the honest, cumulative picture across all this project's
combination attempts is consistent: **every tested way of leaning
harder on content-pattern trades real recall gains for real,
comparable FP cost — none is a clean win over divergence alone.**

## Real, remaining candidate directions for finding 010

Given this and prior negative/mixed results, the two directions NOT
yet attempted with real evidence are:
1. A genuinely larger, more structurally diverse internal calibration
   corpus (still unattempted, still the largest real undertaking)
2. Formally documenting current numbers as an accepted, stated
   limitation rather than continuing to search for a combination rule
   — increasingly the pattern each new measurement supports, though
   not yet formally decided

## Reproducing this result

```bash
set -a && source .env && set +a
python3 -c "from simulacrum.evaluation.divergence_rescue_analysis import _run_cli; _run_cli()" --n 120 --seed 42
```
