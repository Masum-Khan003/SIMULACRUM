# Finding 010 — real MiniLM underperforms the fake embedder on genuinely external (AgentDojo) attack data

**Component:** `detectors/param_divergence.py`, both `MINILM_DIVERGENCE_THRESHOLD`
and `FAKE_DIVERGENCE_THRESHOLD`, discovered scoring real AgentDojo
trajectories (§08 Layer 4).

**Severity:** Real, significant, and genuinely humbling — not dismissed
because it contradicts the narrative of every prior finding this session
(MiniLM outperforming the fakes on every INTERNAL measurement).

## What happened
Scored real, external AgentDojo attack trajectories (independently authored,
never seen during any of this project's calibration work) against our
param-vs-task divergence detector, using both embedders and their real
production thresholds:

- FakeSemanticEmbedder (threshold 0.15): 88.2% recall (834/946, full dataset)
- Real MiniLM (threshold 0.3030): 77.6% recall (734/946, full dataset --
  confirmed via complete re-run after an initial 150-sample estimate of
  77.6% showed the same gap, ruling out sampling noise as the explanation)

Real MiniLM performs WORSE on this external dataset than the cruder
bag-of-words fake, despite outperforming it on every measurement this
project has made against our OWN data (findings 001, 005, and finding
008's own calibration evidence).

## Why this is a real, important finding — not a contradiction to explain away
`MINILM_DIVERGENCE_THRESHOLD` was calibrated (finding 008) via 1st-percentile
derivation against 420 real MiniLM samples from OUR task_sim corpus, using
OUR attack_suite's specific attack shapes. This is a textbook case of
calibration not fully transferring to a different data distribution:
AgentDojo's tasks use different phrasing conventions, a different (larger)
tool vocabulary, and different task structures than our self-authored
corpus. Real semantic understanding (MiniLM) may be MORE sensitive to this
distributional shift precisely because it's actually reasoning about
meaning rather than crudely matching surface vocabulary overlap — the fake
embedder's cruder mechanism may coincidentally generalize better here
simply by luck of keyword overlap, not because it's actually a better
detector.

## Not yet fixed — real follow-up work, honestly scoped
This requires either:
  1. A larger, more diverse internal calibration corpus (more task types,
     closer to §08's target of 5-8, reducing distributional narrowness)
  2. Recalibrating MINILM_DIVERGENCE_THRESHOLD using a MIX of internal AND
     external (AgentDojo) data, if that's methodologically sound (real
     question: should external benchmark data ever inform production
     thresholds, or should it remain purely a held-out validation set per
     §08's own Layer 3/4 separation? Worth deciding deliberately, not
     defaulting either way.)
  3. Accepting this as a stated, honest limitation of the current
     calibration's generalization scope, documented rather than silently
     shipped as if it doesn't exist.

Not resolved in this session — tracked in docs/BACKLOG.md as a priority
item specifically because it's the kind of result easy to want to bury.

## Why this matters beyond this one number
This is the single most important piece of evidence this session's
external-validation work produced: it directly tests whether ALL the
careful internal calibration work (finding 008's percentile methodology,
the generalization-set testing that showed 100% recall on OUR held-out
data) actually holds up against data we didn't design our corpus around.
The honest answer is: partially. That's real, valuable information a
project claiming production-readiness needs to know and state plainly,
not a result to minimize because it's less flattering than our internal
numbers.
