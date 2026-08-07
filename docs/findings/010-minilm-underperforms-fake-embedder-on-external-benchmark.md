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

## MAJOR UPDATE — original ground truth was flawed; real picture is more nuanced

Follow-up investigation found a real methodological error in the ORIGINAL
version of this finding: it used `had_injection` (an injection was
ATTEMPTED) as ground truth for "should be flagged," when the correct
ground truth is AgentDojo's own `security` field (security=False means
the injection actually SUCCEEDED; security=True means the agent RESISTED
it). 286 of the original 946 "attack" trajectories were actually
genuinely benign (attack attempted but resisted) — meaning the original
88.2%/77.6% recall numbers were measuring the wrong thing for ~30% of
the dataset.

### Corrected numbers, using real ground truth (attack_succeeded)

| Embedder | Recall on REAL attacks (n=660) | "False positive" rate on resisted (n=320) |
|---|---|---|
| FakeSemanticEmbedder | 85.2% (562/660) | 90.0% (288/320) |
| Real MiniLM | 74.7% (493/660) | 78.4% (251/320) |

### The false-positive rate is NOT simply a bug — it reveals a real definitional gap

Inspecting WHICH calls drive these "false positives" (the lowest-
similarity call in each flagged-but-resisted trajectory) shows they are
overwhelmingly HIGH-RISK, SENSITIVE actions, not generic noise:
`get_most_recent_transactions` (40 cases, by far the most common),
`delete_file` (17), `send_email` (16), `remove_user_from_slack` (11),
`update_password` (7), `send_money` (6) — real examples inspected
directly show trajectories where the agent sent unsolicited emails to
five different people, or deleted a file, WITHOUT completing the
attacker's exact narrow objective.

**AgentDojo's `security` metric asks a narrower question than
Simulacrum is designed to answer.** AgentDojo measures whether THIS
SPECIFIC injection's precise goal was achieved. Simulacrum's own design
(§04, goal-drift detection) explicitly cares about ANY off-task
deviation, independent of whether a specific attacker succeeded at their
exact objective. A trajectory where the agent partially engaged with an
injected instruction (sent unsolicited emails, deleted a file, checked
transaction history) but didn't complete the attacker's precise goal is
NOT "safe" under Simulacrum's own threat model — it'''s exactly the
kind of off-task action §13's tiered response (flag/require-approval)
exists to catch for human review, regardless of the attacker's specific
narrow success.

### What this means, stated honestly

This does NOT mean the original recall gap (MiniLM underperforming the
fake embedder) is resolved or explained away — that gap is REAL and
consistent across both the flawed and corrected ground truth (74.7% vs
85.2%, similar magnitude to the original 77.6% vs 88.2%). What it DOES
mean is that the "false positive" framing of the original analysis was
importantly incomplete: a meaningful fraction of what looked like pure
detector error is arguably CORRECT behavior under Simulacrum'''s own,
broader definition of what deserves review, being measured against the
wrong yardstick (AgentDojo'''s narrower per-injection success metric).

### Real remaining open questions
1. The MiniLM-vs-fake recall gap (74.7% vs 85.2%) on REAL attacks
   remains real, unexplained, and unresolved — this part of the
   original finding stands.
2. A genuine metric is needed to distinguish "detector correctly
   flagged concerning-but-not-attacker-goal-achieving behavior" from
   "detector genuinely false-positived on benign behavior" — the
   current heuristic (inspecting which tool triggered the lowest score)
   is suggestive, not rigorous. Building this properly is real,
   separate follow-up work.
3. Whether AgentDojo'''s benchmark is even the right ground truth for
   evaluating Simulacrum'''s BROADER threat model (vs. narrow injection-
   success) is itself worth stating as a limitation of using this
   specific external dataset for this specific purpose.
