# Finding 012: §10 earliest-anomaly-onset baseline — real, honest negative result, no discriminative signal

**Status:** Resolved (measured, negative result documented). §10's three required baselines are now all closed:
input-only classifier (built, significant finding), explicit-detectors-only (built, finding 011), earliest-anomaly-onset (this finding).

## Background

§10's third required baseline references "the cheap heuristic
identified during this project's own scoping review" — but no such
heuristic is specified anywhere in the actual blueprint (verified via
direct text search: the phrase appears exactly once, no further
detail). Rather than leave this permanently unbuilt on ambiguity
alone, a reasonable, explicitly-stated interpretation was built and
measured: does the position (turn-index) of a trajectory's FIRST
flagged call, alone, discriminate real attacks from false positives —
without needing full-trajectory aggregation.

## Real, honest scope notes

- **Turn-index = tuple position.** `ExtractedToolCall` (AgentDojo
  adapter) has no `turn_index` field, unlike Simulacrum's own
  `ToolCall`. AgentDojo trajectories are strictly sequential in their
  own JSON (no parallel-call structure), so tuple position was used
  directly — stated explicitly, not silently assumed equivalent to
  Simulacrum's own richer `turn_index` concept.
- Same detector-vocabulary scope as finding 011: only divergence and
  content-pattern can evaluate AgentDojo's tool set.
- Reused `score_trajectory_divergence`'s existing `per_call_similarities`
  — no new detector calls needed for divergence, only content-pattern
  needed a fresh per-call check.

Built `src/simulacrum/evaluation/earliest_onset_baseline.py`
(`find_onset_index()`, `summarize_onsets()`, CLI wrapper), with 2 real
tests in `tests/unit/test_earliest_onset_baseline.py`.

## Method

Same real, seeded AgentDojo sample as finding 011 (n=120, seed=42: 60
real attacks, 60 real resisted trajectories). For each trajectory,
found the index of the first call flagged by divergence OR
content-pattern, then compared the onset-position distribution
(normalized as `onset_index / call_count`, to account for varying
trajectory lengths) between the two real ground-truth groups.

**Real discipline note:** an initial n=10 smoke test showed an
apparently strong effect (mean onset fraction: attacks 0.496 vs. FPs
0.088, diff +0.407) — this looked like a genuine, usable signal.
Scaling to the full real n=120 sample was necessary before trusting
it, per this project's own cost-conscious verification pattern (small
sample first, confirm behavior, then scale).

## Real result

| | n | Flagged | Mean onset fraction | Median onset index |
|---|---|---|---|---|
| Real attacks | 60 | 54/60 | 0.207 | 1.0 |
| Real resisted (→ false positives) | 60 | 50/60 | 0.179 | 1.0 |
| **Delta (attack − FP)** | | | **+0.028** | **0.0** |

The apparent n=10 effect (+0.407) essentially disappeared at n=120
(+0.028) — a textbook case of small-sample noise, exactly the kind of
result this project's own discipline (documented minimum sample
sizes, §11) exists to catch before it ships as a false conclusion.
Medians are identical (1.0) between both groups.

## Honest conclusion

**Turn-index of first onset, alone, carries no meaningful
discriminative signal between real attacks and false positives on
this data.** Both groups get flagged at almost exactly the same
point in a trajectory (typically the 2nd call). This is a real,
honest negative result — not a failure of the heuristic's
implementation, but evidence that "how early a flag fires" is not,
by itself, informative about whether the flag is correct. This tracks
with intuition in hindsight: a false positive and a true positive can
both trigger on an early, superficially-similar-looking call; only
the call's actual content (which divergence/content-pattern already
evaluate) distinguishes them, not its position.

## What this means for §10

All three required §10 baselines are now built and measured:

1. **Input-only classifier** — significant finding, outperformed
   session-aware divergence on recall (see prior work, `docs/CALIBRATION_REPORT.md`)
2. **Explicit-detectors-only** — goal-drift earns a small, real, free
   recall lift (finding 011)
3. **Earliest-anomaly-onset** — no discriminative signal (this finding)

§10 is now honestly, fully closed. No further baseline work is
required unless the blueprint itself is revised to specify a
different heuristic than the one interpreted here.

## Reproducing this result

```bash
set -a && source .env && set +a
python3 -c "from simulacrum.evaluation.earliest_onset_baseline import _run_cli; _run_cli()" --n 120 --seed 42
```
