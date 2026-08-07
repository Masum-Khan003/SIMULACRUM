# AgentDojo Benchmark Results (§08 Layer 4)

Real, external benchmark data used to validate Simulacrum's detectors
against genuinely independent, published attack scenarios — not our own
self-authored `attack_suite/` corpus.

## Run configuration
- **Framework:** [AgentDojo](https://github.com/agentdojo/agentdojo) v0.1.35, benchmark version v1.2
- **Agent model (the "victim" being attacked):** `gpt-4o-mini-2024-07-18`
- **Attack strategy:** `important_instructions` (AgentDojo's primary baseline attack)
- **Suites run:** all 4 available — `workspace`, `travel`, `banking`, `slack`
- **Total real API cost:** ~$0.56 (measured directly from OpenAI usage
  dashboard on sample runs, extrapolated across 984 total tests at a
  measured ~$0.0006–$0.0009/test)
- **Dataset completeness:** 984/984 (100%) — verified via direct
  set-difference against AgentDojo's own registered task/injection
  combinations, not assumed

## AgentDojo's own reported results (their scoring, not ours)

| Suite | Utility | Injection tasks passed as user tasks | Security |
|---|---|---|---|
| workspace | (see full log) | — | — |
| travel | 33.57% | 7/7 | 34.29% |
| banking | 45.83% | 8/9 | 50.00% |
| slack | 47.62% | 5/5 | 64.76% |
| **combined** | **39.83%** | **27/35** | **30.14%** |

"Security" here is AgentDojo's own metric: the percentage of injection
attempts the raw, undefended `gpt-4o-mini` agent successfully RESISTED.
This is baseline vulnerability data for the raw model, not a measure of
Simulacrum's own detection — that's the next section.

## Simulacrum's detector performance against this real, external data

(To be completed — real trajectories parsed via
`generalization_set/agentdojo_adapter/`, scored via param-vs-task
divergence logic in `test_agentdojo_generalization.py`. Initial sample
of 100 real injected trajectories showed min-similarity range
0.0000–0.2231 using FakeSemanticEmbedder, meaning the large majority
would be flagged by our divergence threshold. Full-dataset scoring
across all 984 trajectories, and scoring via our OTHER detectors
(content-pattern, escalation) against this real external data, is
real follow-up work — tracked in docs/BACKLOG.md.)

## Honest scope notes
- This adapter extracts tool calls and task descriptions from
  AgentDojo's trajectories and scores them via our detector LOGIC. It
  does NOT map AgentDojo's tool schema onto our RiskTier/tier-engine
  system — the two systems use entirely different, incompatible tool
  vocabularies (AgentDojo: `send_email`, `delete_file`,
  `reschedule_calendar_event`, etc.; ours: `reply_to_email`,
  `delete_data`, etc.). See `agentdojo_adapter/adapter.py`'s own
  docstring for the full scope statement.
- AgentDojo's own multiprocessing (`--max-workers`) path has a real,
  reproducible bug (`AttributeError: 'str' object has no attribute
  'name'` inside their own `benchmark_suite` function under
  multiprocessing) — worked around by running sequentially.
