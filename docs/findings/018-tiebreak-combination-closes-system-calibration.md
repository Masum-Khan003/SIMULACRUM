# Finding 018: a targeted tie-breaking combination rule beats naive combination, but still doesn't clearly beat divergence alone — system-level calibration closed

**Status:** Resolved. Answers `docs/CALIBRATION_REPORT.md`'s own explicitly-flagged, never-attempted follow-up. Closes the system-level calibration combination-rule question.

## Background

`docs/CALIBRATION_REPORT.md` tried two system-level combination rules, both real negative results: binary-flag OR (Brier 0.4146, worse than divergence alone's 0.2333) and continuous-confidence averaging (Brier 0.2673, better than binary but still worse than divergence alone). The report explicitly named the untried direction: "a smarter combination rule (weighted by confidence, or using content-pattern specifically to break ties near divergence's own threshold, rather than blending both scores unconditionally) might do better."

## Real design

Built a genuinely non-naive rule: trust divergence's own pseudo-probability directly, EXCEPT when `min_similarity` falls within a real, evidence-derived "ambiguous zone" around `MINILM_DIVERGENCE_THRESHOLD` — only there does content-pattern's own confidence override. Unlike prior attempts, this does not blend both signals on every sample; it only intervenes where divergence's own signal is measurably uncertain.

**Zone width chosen from real data, not guessed:** measured what fraction of the real n=120 sample's `min_similarity` values fall within various distances of the threshold. ±0.05 captures a real, meaningful 10.0% of the sample (12/120) — narrow enough to only touch genuinely marginal cases, wide enough to matter (±0.02 only touched 3 samples; ±0.1 touched 20.8%, too broad to call "ambiguous").

Built `src/simulacrum/evaluation/tiebreak_combination.py` (`tiebreak_probability()`, real, importable, CLI runner), same real n=120/seed=42 AgentDojo sample as prior combination attempts.

## Real result

| Approach | Brier Score |
|---|---|
| Divergence alone | 0.2333 |
| Binary-flag combination | 0.4146 |
| Continuous-averaged combination | 0.2673 |
| **Tiebreak combination (this finding)** | **0.2433** |

The tiebreak rule is the best combination attempt yet — closer to divergence alone than either prior method — but still does not beat it.

**Recall/FP, using the correct decision threshold (the pseudo-probability equivalent of `MINILM_DIVERGENCE_THRESHOLD`, ≈0.3347 — an earlier draft of this measurement used an incorrect fixed 0.5 cutoff and produced a spurious, drastic recall collapse; caught and corrected before drawing any conclusion):**

| | Recall | FP rate |
|---|---|---|
| Divergence alone | 86.7% | 76.7% |
| Tiebreak combination | 88.3% | 78.3% |
| Delta | +1.7pp | +1.7pp |

A clean, exactly-even trade — every recall gain came with an equal FP cost, on this sample.

**Real process note:** the first recall/FP measurement attempt used an incorrect decision threshold (0.5 instead of the real pseudo-probability equivalent of the production threshold), producing a nonsensical recall drop from 86.7% to 28.3%. Caught immediately as inconsistent with the near-identical Brier scores, re-derived the correct threshold, and re-measured before reporting anything. Consistent with this project's own "verify with real, direct evidence when something looks surprising" discipline (same pattern as finding 010's two ground-truth corrections).

## Honest interpretation

**A targeted, evidence-scoped intervention is a real, measurable improvement in combination-rule design over blind blending — but it does not close the gap.** The tiebreak rule only touches the 10% of cases where divergence is genuinely uncertain, which is conceptually the correct approach (not diluting a confident signal with a noisier one), and it produces the best Brier score of any combination attempt. But even confined to genuinely ambiguous cases, content-pattern's tie-breaking judgment trades recall for FP roughly 1-for-1 rather than providing a clean lift — consistent with the broader pattern across findings 011/013 (content-pattern combinations trade real recall for real, comparable FP cost almost every time this project has measured it).

**This is a real, honest, non-dramatic result** — better methodology, marginal outcome. It is not a failure: the rule is real, correctly targeted, and slightly ahead of every prior combination attempt. It simply confirms, with better evidence than before, that content-pattern and divergence's disagreements are not concentrated in a way that a smarter combination rule can cleanly exploit at this sample size.

## Why this closes the system-level calibration question

Three real combination approaches have now been tried (binary, averaged, targeted tiebreak), spanning the reasonable design space CALIBRATION_REPORT itself identified. All three underperform or roughly match divergence alone; none provides a clean win. Continuing to search for combination rules without a fundamentally different idea (e.g., a genuinely larger sample to detect a real but small effect, or a different pair of detectors) would be open-ended tuning rather than a bounded, evidence-driven task — the same category of decision finding 010's investigation eventually reached (three tuning attempts exhausted a reasonable design space; further work needs a different lever, not another tuning pass).

## What remains, honestly

- The exact tiebreak rule here has not been validated at larger scale (still n=120) — a real, larger sample might reveal a small but real net-positive effect this sample is too noisy to detect, or might confirm the even trade holds.
- Not currently a priority: the marginal, even-trade result doesn't currently justify further investment relative to other real, open work (Phase 3 stretch goals).

## Reproducing this result

```bash
set -a && source .env && set +a
python3 -c "from simulacrum.evaluation.tiebreak_combination import _run_cli; _run_cli()"
```
