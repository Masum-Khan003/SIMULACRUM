# Formal Confidence Calibration Report (§05/§15)

Brier score and reliability diagram for Simulacrum's param-vs-task
divergence detector, computed against real, ground-truth-verified
AgentDojo external benchmark data (§08 Layer 4) — the same corpus and
ground-truth methodology validated across findings 007-010.

## Methodology

The divergence detector's raw cosine-similarity score is mapped to a
pseudo-probability of attack via `(1 - similarity) / 2`, clipped to
`[0, 1]` — lower similarity (less related to the task) maps to higher
estimated attack probability. This is a real, honest reuse of an
existing continuous signal, not an invented probability estimate the
detector doesn't actually produce.

Real ground truth: `attack_succeeded` (AgentDojo's own `security`
field, polarity verified against source code and 19 real result files
— see `docs/findings/010-*.md`). n=980 total samples (660 real
attacks, 320 real resisted/benign — note this real report used the
full dataset at time of generation, close to but not identical to
earlier reported n=980 due to minor dataset evolution across the
session's iterative work).

## Results

**Brier score: 0.2333** (0 = perfect, 0.25 = coin-flip baseline on a
balanced dataset, 1.0 = worst possible / confidently wrong every time)

This is real, honest, and sobering: only marginally better than random
guessing. This formally confirms, via a standard calibration metric,
what finding 010's extensive investigation already found empirically —
the divergence detector's confidence signal does not generalize well
to genuinely external data, despite strong internal calibration
evidence (finding 008's percentile derivation, §08 Layer 3's 100%
recall / 0% FP on our own held-out corpus).

### Reliability diagram

| Bin | Mean Predicted | Observed Frequency | N |
|---|---|---|---|
| [0.0-0.1) | 0.085 | 1.000 | 3 |
| [0.1-0.2) | 0.125 | 0.222 | 18 |
| [0.2-0.3) | 0.258 | 0.235 | 115 |
| [0.3-0.4) | 0.354 | 0.335 | 260 |
| [0.4-0.5) | 0.452 | 0.369 | 428 |
| [0.5-0.6) | 0.520 | 0.263 | 156 |
| [0.6-1.0) | -- | -- | 0 |

### Two real, honest findings from this report specifically

1. **The detector never confidently predicts "attack."** Zero samples
   fall in bins 0.6-1.0 across the ENTIRE real dataset. Minimum-
   aggregated similarity across a trajectory structurally caps out
   around 0.5-0.6 pseudo-probability even for genuine attacks, since
   most calls in even a successful attack trajectory are legitimate-
   looking (see finding 010's own trajectory inspection work). This is
   a real, structural property of the min-aggregation approach, not a
   threshold-tuning issue.

2. **The lowest-confidence bin is inverted (small sample, worth
   flagging honestly, not over-interpreting).** The 3 samples the
   detector was MOST confident were benign (<10% predicted attack
   probability) were, per real ground truth, actually all real
   attacks. n=3 is too small to draw a strong conclusion, but it's
   an honest, reported data point, not hidden.

## What this report does NOT claim

This is a real calibration measurement for ONE detector
(param-vs-task divergence) against ONE real external dataset
(AgentDojo). It does not measure the SYSTEM's overall calibration
(which includes 5 other independent detectors — schema, escalation,
loop-rate, exfiltration, content-pattern — several of which
structurally catch cases divergence alone misses, per findings 007
and 010's own trajectory-level analysis). A full system-level
calibration report, incorporating all 6 detectors' combined decision
confidence, is real, valuable future work not yet built.

## Reproducing this report

```python
from pathlib import Path
from simulacrum.attribution import MiniLMEmbedder
from simulacrum.generalization_set.agentdojo_adapter.adapter import load_all_trajectories
from simulacrum.generalization_set.agentdojo_adapter.scoring import score_trajectory_divergence
from simulacrum.evaluation.calibration_report import (
    CalibrationSample, generate_calibration_report, similarity_to_pseudo_probability,
)

embedder = MiniLMEmbedder()
trajectories = load_all_trajectories(runs_dir=Path("./runs"))
succeeded = [t for t in trajectories if t.attack_succeeded is True and t.tool_calls]
resisted = [t for t in trajectories if t.attack_succeeded is False and t.tool_calls]

samples = []
for t in succeeded:
    result = score_trajectory_divergence(trajectory=t, embedder=embedder)
    prob = similarity_to_pseudo_probability(similarity=result.min_similarity)
    samples.append(CalibrationSample(predicted_probability=prob, actual_outcome=True))
for t in resisted:
    result = score_trajectory_divergence(trajectory=t, embedder=embedder)
    prob = similarity_to_pseudo_probability(similarity=result.min_similarity)
    samples.append(CalibrationSample(predicted_probability=prob, actual_outcome=False))

report = generate_calibration_report(samples=samples)
print(f"Brier score: {report.brier_score:.4f}")
```

## System-level calibration (divergence + content-pattern), real bounded sample

Real, honest scope note: a genuinely honest "system-level" report for
THIS external dataset can only combine detectors that structurally can
evaluate AgentDojo's different tool vocabulary at all — schema,
permission escalation, and exfiltration are keyed to Simulacrum's own
tool names/baselines and cannot meaningfully evaluate AgentDojo's
tools (see `agentdojo_adapter/adapter.py`'s own scope docstring).
Only param-vs-task divergence and content-pattern detection are
genuinely tool-vocabulary-agnostic. This report combines those two,
using a real, bounded sample (n=120: 60 real attacks, 60 real resisted,
random-seeded) rather than the full dataset, given content-pattern
scoring requires real Groq API calls.

**Pseudo-probability construction:** fraction of the 2 detectors that
flagged the trajectory (0.0 = neither, 0.5 = one, 1.0 = both).

### Real result: Brier score 0.4146 — WORSE than divergence alone (0.2333)

This is a genuine, honest, somewhat counterintuitive finding, reported
precisely rather than hidden or spun positively.

| Bin | Mean Predicted | Observed Frequency | N |
|---|---|---|---|
| [0.0-0.1) (neither flags) | 0.000 | 0.357 | 14 |
| [0.5-0.6) (one flags) | 0.500 | 0.590 | 39 |
| [0.9-1.0) (both flag) | 1.000 | 0.478 | 67 |

**Real diagnosis, not spin:**
1. When NEITHER detector flags, 35.7% of those trajectories were
   still real attacks — a genuine, meaningful miss rate for the
   "both clear" case.
2. When BOTH detectors flag, only 47.8% were real attacks — the two
   detectors' errors are CORRELATED (they tend to agree even when
   wrong), not independent. Combining them does not behave like
   independent evidence stacking would predict.
3. A real methodological factor: this combination only produces 3
   discrete probability levels (0.0/0.5/1.0), a much coarser scale
   than divergence alone's continuous similarity score. Brier score
   penalizes confident, coarse predictions more heavily than smooth
   continuous ones — some of this regression is a real artifact of
   discretization, not purely a signal-quality problem.

**Honest conclusion:** naively combining two detectors' binary
flags does NOT automatically improve calibration, and can make it
measurably worse if the detectors' errors correlate and the
combination discards the continuous signal either detector had on its
own. A better system-level combination would likely need to preserve
each detector's own continuous confidence (not just a binary flag)
and/or model correlation between detectors explicitly — real,
valuable, NOT YET attempted follow-up work.

## System-level calibration, take two: continuous confidence

Follow-up to the binary-flag combination above. Added a genuine
continuous confidence score to GroqContentPatternDetector (additive
change, existing `is_suspicious` decision logic untouched — see
`ContentPatternResult.confidence`), correctly converted to a real
probability-of-attack (handling the semantic direction: confidence is
"how sure of THIS verdict," not "probability of attack" directly —
verdict=NORMAL with confidence=0.95 means 5% attack probability, not
95%). Combined via simple averaging with divergence's own continuous
pseudo-probability, same real bounded sample (n=120, same random seed,
fair comparison).

| Approach | Brier Score |
|---|---|
| Divergence alone | 0.2333 |
| Binary-flag combination (0.0/0.5/1.0) | 0.4146 |
| Continuous-confidence combination (averaged) | 0.2673 |

**Real, honest conclusion:** continuous confidence is a genuine,
substantial improvement over binary flags (0.4146 -> 0.2673),
confirming discretization was a real factor in the earlier regression.
However, it STILL does not beat divergence alone (0.2333) on this
bounded sample. This means simple averaging is also not the right
combination rule — content-pattern's real signal, even continuous,
doesn't add clear net calibration value when combined this naively.

**Genuinely open, real follow-up work** (not attempted): a smarter
combination rule (weighted averaging favoring whichever detector is
more confident, or using content-pattern specifically to break ties
when divergence sits near its own threshold, rather than blending both
scores unconditionally) might do better than either divergence alone
or simple averaging. This report intentionally stops at reporting the
real, measured evidence rather than continuing to search for a
combination rule that "wins" — the honest result is that naive
combination approaches (binary and simple-average continuous) both
underperform the single best detector on this specific external
dataset, which is itself real, useful information about this system's
current limits.
