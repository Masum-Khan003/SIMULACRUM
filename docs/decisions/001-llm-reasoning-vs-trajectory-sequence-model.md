# Decision 001 — LLM reasoning as the §10 trajectory-sequence-model substitute

**Status:** Accepted, for the current project stage. Revisit if real
production trajectory data accumulates at volume (see "Revisit
conditions" below).

## Context

§10 of the blueprint specifies a trajectory sequence model: an ML
model processing sequences of `(tool, param-embedding, timestamp, ...)`
tuples to detect goal drift across a session. What was actually built
(`attribution/goal_drift.py`) is `GroqDriftDetector` — an LLM reasoning
over a textual trajectory description, with a deterministic
`NullDriftDetector` fail-open fallback.

This is a genuine architectural substitution, not an incremental
implementation detail, and deserves an explicit, permanent decision
record rather than an implicit gap sitting in the backlog indefinitely.

## Decision

LLM-based trajectory reasoning is accepted as the goal-drift detection
mechanism for this project's current stage, in place of a literally
trained sequence model.

## Rationale

**No real training data exists.** A trajectory sequence model needs
real, labeled (drift / no-drift) session sequences at meaningful
volume to train against. This project has real, ground-truth-labeled
attack corpora (`attack_suite/`) and real external validation data
(AgentDojo), but neither is remotely the right shape or volume for
training a sequence model — that requires thousands of real,
diverse, labeled trajectories, which only accumulates from real
production traffic over time, not from a single development session.

**The LLM approach is extensively, genuinely tested.** Real evidence
this project has already gathered: 6/6 real calibration cases passing
after finding and fixing a genuine prompt-design bug (forced one-word
verdicts suppressing reasoning, `docs/BACKLOG.md`/goal_drift.py's own
history); a statistically-grounded majority-vote test for one
genuinely ambiguous case (finding 009); real testing against
externally-sourced attack shapes via the closely related
content-pattern detector (95% recall on real AgentDojo travel-suite
attacks). This is a real, evidence-backed detection mechanism, not an
untested placeholder.

**Interpretability is a genuine, not incidental, advantage.** Every
LLM-based decision in this project comes with real, human-readable
reasoning (visible throughout every finding this session). A trained
sequence model is an opaque classifier — closing that gap would
require separate, real explainability work (SHAP, attention
visualization, etc.) that doesn't currently exist and isn't
scoped anywhere in this project.

**Building training infrastructure now would be premature complexity.**
Per §00b's own stated lessons (documented specifically to avoid
repeating Palimpsest's mistakes): building real ML training
infrastructure (data pipeline, training loop, model versioning,
retraining triggers) with no real training data to actually train
against would be exactly the kind of speculative, ahead-of-need
engineering this project's own principles argue against.

## Consequences

- Goal-drift detection has a real, stated external dependency (Groq
  API) for its PRIMARY mechanism, with a documented, tested fail-open
  fallback (`NullDriftDetector` — never flags, the correct
  conservative default for this least-certain detector).
- Real per-call latency and cost exist for drift checks (mitigated by
  §12's own async/rolling-interval scoping, not per-call — see
  `drift_scheduler.py`), unlike a trained model's near-zero marginal
  inference cost.
- §17's drift/re-baselining pipeline (PSI, promotion gate) was built
  and verified for the EXPLICIT, threshold-based detectors. It was NOT
  designed with a trainable sequence model's retraining cycle in mind
  — if a real sequence model is built later, the promotion-gate
  pattern would need real adaptation (a "champion" trained model vs. a
  "challenger" retrained model, not just a threshold sweep).

## Revisit conditions

Reconsider this decision if ANY of the following become true:
1. Real production traffic accumulates labeled trajectory data at
   genuine volume (hundreds to thousands of real, diverse sessions
   with confirmed drift/no-drift outcomes) — at that point, a trained
   sequence model becomes a real, buildable option rather than
   speculative infrastructure.
2. Groq API cost or latency becomes a genuine operational constraint
   at real production scale — a trained model's near-zero marginal
   cost becomes meaningful at that point.
3. A regulatory or contractual requirement emerges for fully
   deterministic, auditable (non-LLM) decision logic for this specific
   detection class.

None of these conditions are currently true. This decision should be
revisited, not silently maintained forever — tracked in
`docs/BACKLOG.md`.
