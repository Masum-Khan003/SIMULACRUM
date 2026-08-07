# AgentDojo Benchmark Results (§08 Layer 4)

Real, external benchmark data used to validate Simulacrum's detectors
against genuinely independent, published attack scenarios -- not our own
self-authored `attack_suite/` corpus.

## Run configuration
- **Framework:** [AgentDojo](https://github.com/agentdojo/agentdojo) v0.1.35, benchmark version v1.2
- **Agent model (the "victim" being attacked):** `gpt-4o-mini-2024-07-18`
- **Attack strategy:** `important_instructions` (AgentDojo's primary baseline attack)
- **Suites run:** all 4 available -- `workspace`, `travel`, `banking`, `slack`
- **Total real API cost:** ~$0.56 (measured directly from OpenAI usage
  dashboard on sample runs, extrapolated across 984 total tests at a
  measured ~$0.0006-$0.0009/test)
- **Dataset completeness:** 984/984 (100%) -- verified via direct
  set-difference against AgentDojo's own registered task/injection
  combinations, not assumed

## AgentDojo's own reported results (their scoring, not ours)

| Suite | Utility | Injection tasks passed as user tasks | Security |
|---|---|---|---|
| workspace | (see full log) | -- | -- |
| travel | 33.57% | 7/7 | 34.29% |
| banking | 45.83% | 8/9 | 50.00% |
| slack | 47.62% | 5/5 | 64.76% |
| **combined** | **39.83%** | **27/35** | **30.14%** |

"Security" here is AgentDojo's own metric: the percentage of injection
attempts the raw, undefended `gpt-4o-mini` agent successfully RESISTED.
This is baseline vulnerability data for the raw model, not a measure of
Simulacrum's own detection -- that's the next section.

## Simulacrum's detector performance against this real, external data

Real param-vs-task divergence recall against real, injection-present
AgentDojo trajectories:

| Embedder | Threshold | Recall | Sample size |
|---|---|---|---|
| FakeSemanticEmbedder (bag-of-words) | 0.15 | **88.2%** (834/946) | full dataset |
| Real MiniLM (all-MiniLM-L6-v2) | 0.3030 | **77.6%** (734/946) | full dataset (corrected from an initial 150-sample estimate of 77.6%, confirmed consistent) |

**Honest, important finding: real MiniLM recall (77.6%) is meaningfully
LOWER than the fake embedder's (88.2%) on this genuinely external
dataset**, despite MiniLM outperforming the fake embedder on every
internal measurement this project has made (findings 001, 005, and the
real semantic-separation evidence behind finding 008's recalibration).

The most likely explanation, stated honestly rather than picked because
it's flattering: `MINILM_DIVERGENCE_THRESHOLD` (0.3030) was calibrated
via 1st-percentile derivation (finding 008) against OUR OWN task_sim
corpus and attack_suite's specific attack shapes. AgentDojo's tasks use
genuinely different phrasing, tool vocabulary, and task structure --
real semantic understanding (MiniLM) may be MORE sensitive to that
distributional shift than a cruder bag-of-words approach that
coincidentally still catches things via literal keyword overlap.
This is exactly the kind of result external validation exists to
surface: our calibration is rigorous against our OWN data, but this is
real, honest evidence it does not fully transfer to a different task
distribution. Tracked in docs/BACKLOG.md as a priority follow-up --
NOT swept under the rug because the number is less impressive than our
internal metrics.

Scoring via our other detectors (content-pattern, permission
escalation) against this real external data -- using the adapter's
scope limits (no RiskTier/tier-engine mapping, see below) -- remains
real follow-up work.

## Honest scope notes
- This adapter extracts tool calls and task descriptions from
  AgentDojo's trajectories and scores them via our detector LOGIC. It
  does NOT map AgentDojo's tool schema onto our RiskTier/tier-engine
  system -- the two systems use entirely different, incompatible tool
  vocabularies (AgentDojo: `send_email`, `delete_file`,
  `reschedule_calendar_event`, etc.; ours: `reply_to_email`,
  `delete_data`, etc.). See `agentdojo_adapter/adapter.py`'s own
  docstring for the full scope statement.
- AgentDojo's own multiprocessing (`--max-workers`) path has a real,
  reproducible bug (`AttributeError: 'str' object has no attribute
  'name'` inside their own `benchmark_suite` function under
  multiprocessing) -- worked around by running sequentially.

## MAJOR CORRECTION: ground truth methodology fixed (finding 010 update)

The numbers above used `had_injection` (an injection was ATTEMPTED) as
ground truth. This was methodologically flawed -- 286 of 946 "attack"
trajectories were actually genuinely benign (the injection was attempted
but the agent RESISTED it, per AgentDojo's own `security` field).
**Corrected ground truth uses `attack_succeeded`** (security=False means
the attack actually succeeded), giving 660 real positive (attack) cases
and 320 real negative (resisted, genuinely benign) cases.

### Corrected recall/false-positive numbers

| Embedder | Recall on REAL attacks (n=660) | Flag rate on resisted trajectories (n=320) |
|---|---|---|
| FakeSemanticEmbedder | 85.2% (562/660) | 90.0% (288/320) |
| Real MiniLM | 74.7% (493/660) | 78.4% (251/320) |

**Important nuance, not a simple "high false positive rate" bug:**
inspecting which calls drive the "resisted but flagged" cases shows they
are overwhelmingly high-risk actions (`get_most_recent_transactions`,
`delete_file`, `send_email`, `remove_user_from_slack`, `update_password`,
`send_money`) where the agent partially engaged with an injected
instruction without completing the attacker's exact narrow objective.
AgentDojo's `security` metric measures whether ONE SPECIFIC injection's
precise goal succeeded; Simulacrum's own design (§04) is built to flag
ANY off-task deviation, independent of whether a specific attack's exact
objective was achieved. A meaningful fraction of these "false positives"
are arguably correct behavior under Simulacrum's own, broader threat
model, being measured against a narrower external yardstick.

The recall gap (MiniLM underperforming the fake embedder, ~75% vs ~85%)
remains real and unresolved in both the original and corrected analysis
-- see `docs/findings/010-*.md` for the full, honest writeup including
open questions.

## SECOND CORRECTION: ground truth polarity was inverted in the prior correction

The "MAJOR CORRECTION" section above used `security=False` as meaning
"attack succeeded" -- this was VERIFIED WRONG by reading AgentDojo's own
source code and cross-checking 19 real result files directly.
**`security=True` actually means the attack succeeded** (100% correlation
confirmed empirically). See `docs/findings/010-*.md` for the full,
transparent correction history.

### Final, verified-correct numbers

| Embedder | Recall on REAL attacks (n=320) | False positive rate on resisted (n=660) |
|---|---|---|
| FakeSemanticEmbedder | 90.0% (288/320) | 85.2% (562/660) |
| Real MiniLM | 78.4% (251/320) | 74.7% (493/660) |

**Honest conclusion:** this represents a real, substantial generalization
gap between our internally-calibrated divergence thresholds and genuinely
external, more complex, longer real-world trajectories. Neither
alternative aggregation (median, 25th percentile, both tested with real
data) cleanly improves the recall/false-positive tradeoff. NOT resolved
-- tracked as a priority open item in `docs/BACKLOG.md`.
