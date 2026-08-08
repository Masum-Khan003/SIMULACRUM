# Finding 011: §10 explicit-detectors-only baseline — goal-drift earns a small, real, free recall lift

**Status:** Resolved (baseline built and measured for real). No further action required unless Priority 1/2 work changes the underlying detectors.

## Background

§10 of the blueprint requires an "explicit-detectors-only baseline" —
does the LLM-based goal-drift detector (`GroqDriftDetector`, accepted
as §10's substitute for a literal trajectory sequence model per
`docs/decisions/001-*.md`) earn its real cost/complexity over the
explicit detectors alone? Found not-yet-built via a `docs/BACKLOG.md`
re-audit.

## Real, honest scoping correction

Only two of Simulacrum's six detectors are tool-vocabulary-agnostic
enough to score AgentDojo's external tool set at all: **param-vs-task
divergence** and **content-pattern**. Schema, permission-escalation,
loop-rate, and exfiltration are all keyed to Simulacrum's own tool
names/baselines and structurally cannot evaluate AgentDojo's different
tools (see `agentdojo_adapter/adapter.py`'s own scope docstring — the
same real limitation `docs/CALIBRATION_REPORT.md`'s system-level
section already documents).

So, for this external dataset, "explicit-detectors-only baseline"
concretely means:

- **Baseline A (explicit only):** divergence OR content-pattern flags
- **Baseline B (explicit + drift):** A OR goal-drift flags

Comparing A vs B answers §10's real question on the data actually
available to us.

## Real gap also fixed

No runnable script existed anywhere for the sampling/scoring
methodology `docs/CALIBRATION_REPORT.md`'s earlier numbers (n=120,
seed=42) were generated with — a real violation of this project's own
"every claim backed by a runnable script" rule. Built
`src/simulacrum/evaluation/explicit_detectors_baseline.py`
(importable `build_sample()` / `run_baseline()` / `score_trajectory()`,
thin CLI wrapper, same shape as `input_only_baseline.py` and
`task_completion_report.py`), with a real test file
(`tests/unit/test_explicit_detectors_baseline.py`, 3 tests, all real
Groq calls, all passing).

## Method

Real MiniLM embedder, real `GroqContentPatternDetector` (with
heuristic fallback), real `GroqDriftDetector` (with null fallback).
Real, seeded sample (n=120, seed=42) from the real 984-trajectory
AgentDojo `runs/` corpus: 60 real successful attacks
(`attack_succeeded=True`), 60 real resisted trajectories
(`attack_succeeded=False`) — same corpus and ground-truth methodology
verified in finding 010.

Smoke-tested first at n=10 (real cost/timing check, ~2.76s/trajectory)
before scaling to the full n=120 real run (~312.8s total, ~2.61s/
trajectory), per this project's own cost-conscious verification
discipline.

## Real result

| | Recall | FP rate |
|---|---|---|
| Baseline A — explicit only (divergence OR content-pattern) | 90.0% | 83.3% |
| Baseline B — explicit + goal-drift | 93.3% | 83.3% |
| **Delta** | **+3.3%** | **+0.0%** |

Goal-drift caught 2 additional real attacks (out of 60) that neither
divergence nor content-pattern flagged, at **zero** measured FP cost
on this sample (0 additional false positives among the 60 resisted
trajectories).

## Honest interpretation

**Goal-drift earns its keep, modestly.** The lift is real but small —
this is not a dramatic result, and n=60/60 is not large enough to
rule out the lift being noise (2 trajectories is a thin margin). It's
a genuine, free improvement with no observed FP tradeoff, which is
enough to justify keeping `GroqDriftDetector` in the pipeline as
currently scoped (§10 decision 001 stands, no revisit triggered).

**A separate, honest observation not directly part of §10's question:**
Baseline A's own FP rate here (83.3%) is markedly higher than
divergence-alone's previously reported 74.7% (finding 010). This is
consistent with `docs/CALIBRATION_REPORT.md`'s own earlier finding
that naive OR-combination across detectors tends to raise FP rate
even when it also raises recall — not a new phenomenon, but worth
restating plainly rather than let a favorable recall number obscure
it. This does NOT reopen finding 010's core generalization gap
(Priority 1) — divergence's own real numbers are unchanged — but it
does mean Baseline A/B's absolute FP rates should not be read as
"the system's" FP rate; they reflect a 2-detector OR-combination
specifically, on a small sample.

## What this does not answer

- Does not test the "earliest-anomaly-onset baseline" (§10's third
  required baseline) — still genuinely ambiguous in the source
  blueprint, unchanged from prior documentation.
- Does not re-run the full 984-trajectory corpus — n=120 matches the
  existing calibration-report sample size for direct comparability,
  not a claim that a larger run wouldn't shift the exact numbers.
- Does not change finding 010's status — that remains Priority 1,
  open.

## Reproducing this result

```bash
set -a && source .env && set +a
python3 -c "from simulacrum.evaluation.explicit_detectors_baseline import main; main()" --n 120 --seed 42
```
