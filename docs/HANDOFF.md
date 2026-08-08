# Simulacrum — Handoff Document

**Purpose of this file:** this conversation has become too long to
continue productively. This document lets a fresh conversation pick
up the project with zero loss of context, understanding, or working
discipline. Read this ENTIRE file before doing anything else.

---

## 1. What This Project Is

Simulacrum is a **behavioral guardrails system for tool-calling AI
agents** — a framework-agnostic interception layer that watches an
agent's full action trajectory (not just one prompt) and catches the
moment a legitimate-looking tool call is actually driven by an
instruction the user never gave (prompt injection, permission
escalation, exfiltration, goal drift, etc.).

The canonical specification is `simulacrum-blueprint-v2.html`,
available in the project files. **Read it if you need to check a
requirement's exact original wording** — this session's own biggest
findings came from re-reading it carefully against what was actually
built, not from working off memory of an evolving backlog.

This is a **portfolio engineering project**, explicitly held to a
production-grade standard: no shortcuts, no assumed success, every
claim backed by a runnable script and real output, honest negative
results treated as first-class findings rather than hidden.

---

## 2. Working Method — Read This Carefully, It Is Not Optional

This is the exact collaboration pattern used throughout this project.
Deviating from it (skipping verification, assuming file contents,
declaring success without proof) is the single most common way this
session produced real bugs, so follow it precisely.

### The core loop
1. Claude proposes ONE real, runnable bash command (or a small,
   focused batch).
2. The user (Masum) runs it on his real machine and pastes back the
   REAL output.
3. Claude reads that real output and decides the next step from it —
   never from an assumption about what the output "should" be.
4. Repeat. One step at a time. No bundling unrelated changes.

Claude has NO direct access to Masum's machine — it can only give
bash commands and read back what's pasted. There is no tool that lets
Claude read or write files on Masum's real filesystem directly.

### Never assume file contents — always view first
This is the single most repeated lesson of this whole session. Before
editing ANY file:
1. Give a command to `cat` or `grep -n` the REAL current file content.
2. Wait for the real paste-back.
3. Only then write the edit, based on the exact real text just seen.

**Why this matters so much:** many `python3 -c "... str.replace(old,
new) ..."` attempts this session failed because the assumed `old`
string didn't byte-for-byte match the real file (extra whitespace, a
blank line, slightly different wording remembered incorrectly). Every
one of these failures was caught safely because the script's own
`assert old in content` failed BEFORE writing anything — so no
corruption occurred, but real time was wasted. The fix, every time,
was to view the real file first.

### When a string-replace edit fails or risks failing
Do not retry the same approach with a slightly-different guess. Use
one of these instead, in order of preference for the situation:
- **Full-file rewrite via bash heredoc** (`cat > file.py << 'PYEOF' ...
  PYEOF`) — safest for files under ~150 lines. A quoted heredoc
  delimiter (`'PYEOF'`, not `PYEOF`) passes all content through
  completely literally — no shell/Python escaping issues at all. This
  was the most reliable method whenever `python3 -c` string-replace
  hit escaping trouble (which happened repeatedly with nested quotes
  in docstrings/comments).
- **`sed` with an exact line number**, confirmed via `grep -n` first.
- **Python script reading the file into a `lines` list**, finding the
  exact target line by exact string match, and inserting/replacing at
  that index — reliable for precise single-line insertions in larger
  files.

### Verification discipline
- After EVERY code change: run `python3 -m pytest tests/unit/` and
  read the real pasted-back result. Never proceed on an assumption
  that a change "should" work.
- Every new claim needs a runnable script proving it, with real
  output pasted back — not reasoning alone.
- Real API calls (Groq, OpenAI) are used for genuine verification
  where relevant, not mocked. Be cost-and-time-conscious: run a small
  real sample first, confirm behavior, THEN scale up if a larger real
  run is warranted. (Real example: before running AgentDojo's full
  984-test benchmark, one single task was run first to get a real,
  measured per-task cost, which was then extrapolated honestly.)
- When something looks wrong or surprising, re-verify with real,
  direct evidence (read the actual library source code, run a small
  isolated script, cross-check against a second real data point)
  rather than assume the first plausible explanation is correct. This
  session had two real, serious self-corrections from doing this
  properly (see finding 010's three-round correction history) — being
  willing to say "I was wrong, here's the real fix" is part of the
  standard, not a failure of it.

### Documentation discipline
- **`docs/findings/NNN-short-description.md`** — a numbered,
  permanent record whenever something notable is found: a real bug, a
  real limitation, a real surprising result. Includes root cause, real
  evidence, the fix (or honest statement that it wasn't fully fixed),
  and — critically — if a finding is later found to be WRONG or
  incomplete, the file is APPENDED with a clearly-marked correction
  section (e.g. "MAJOR UPDATE", "SECOND CORRECTION"), never silently
  edited to hide the original mistake. Finding 010 has three real
  correction rounds, all visible in the file, because the ground-truth
  polarity was genuinely wrong twice before being verified correct.
- **`docs/decisions/NNN-short-description.md`** — ADR-style, for
  deliberate architectural choices (e.g. "LLM reasoning instead of a
  trained sequence model"). Always includes real rationale AND
  explicit, real revisit conditions — never a silent, unexplained
  substitution.
- **`docs/BACKLOG.md`** — the single, authoritative source of truth
  for open work. Resolved items are marked `~~struck through~~ —
  RESOLVED` with a real summary, never deleted (preserves the
  history), but genuinely open items must stay accurate. This file
  was rewritten from scratch once this session after it accumulated
  537 lines of stale, contradictory, append-only text — a real
  cautionary tale. If it ever starts looking bloated or self-
  contradictory again, audit and rewrite it, don't let it rot.
- **Commit after every logical unit of completed, tested work.**
  Commit messages are detailed: what was done, why, and the real key
  numbers/results — these messages are themselves a readable project
  history (see `git log --oneline` for 76 real examples of the
  expected format and detail level).

### Interaction style
- Present real forks/decisions with a clear recommendation; don't
  make large unilateral architectural calls silently — but for small,
  clearly-correct fixes, just proceed.
- After any break in the conversation, confirm real environment state
  before resuming: `docker compose ps`, `git log --oneline -1`, run
  the real test suite, confirm `GROQ_API_KEY`/`OPENAI_API_KEY` are
  sourced (watch for **leftover exported env vars from earlier in a
  long shell session** — this caused two real, confusing false alarms
  this session: `SIMULACRUM_USE_REAL_EMBEDDINGS=1` staying exported
  across unrelated commands, and once needing an explicit `unset`).
- Report real negative/uncomfortable results exactly as measured —
  never soften a bad number. Some of the most valuable work this
  session was reporting that a naive baseline beat our own detector,
  or that a proposed fix regressed on our own held-out data. That
  honesty is a feature of this project, not an embarrassment to hide.

---

## 3. Real Architecture Overview

### Core request flow
Every tool call goes through `intercept_and_call()`
(`src/simulacrum/interception/interceptor.py`). It runs **6
detectors** through a circuit breaker as one scoring unit, computes a
`response_tier` (`ALLOW` / `FLAG` / `REQUIRE_APPROVAL` / `BLOCK`) via
`decide_response_tier()`, and either executes the tool call or holds/
blocks it depending on tier and risk classification.

**The 6 detectors** (`src/simulacrum/detectors/`):
1. `schema.py` — parameter schema conformance
2. `param_divergence.py` — cosine-similarity between a call's real
   meaning and the evolving task representation (embedder-backed;
   this is the detector at the center of finding 010's whole
   investigation)
3. `permission_escalation.py` — tool-category footprint vs. task-type
   baseline
4. `loop_rate.py` — tool-call rate/repetition, with a retry-vs-evasion
   split
5. `exfiltration.py` — outbound-tool content/frequency vs. baseline
6. `content_pattern.py` — LLM-based (Groq) content-exfiltration
   reasoning, with a deterministic regex-based fallback; the detector
   that closed finding 007's "complete blind spot" and generally
   outperforms the mechanical detectors in every real comparison this
   session made

**Embedders** (`src/simulacrum/attribution/`): `FakeSemanticEmbedder`
(bag-of-words, dim=256, the DEFAULT production embedder) and
`MiniLMEmbedder` (real `all-MiniLM-L6-v2`, opt-in via
`SIMULACRUM_USE_REAL_EMBEDDINGS=1` env var + `[ml]` install extra).
Two SEPARATE calibrated thresholds exist for these
(`FAKE_DIVERGENCE_THRESHOLD=0.15`, `MINILM_DIVERGENCE_THRESHOLD=0.3030`)
— they are NOT interchangeable, each has its own real calibration
history in `param_divergence.py`'s own comments.

**Real LLM reasoning** (Groq, `llama-3.3-70b-versatile`) backs FOUR
separate components, each with a deterministic fail-open fallback:
`GroqExplainer` (§14 explanations), `GroqBoundaryClassifier` (§06
sub-task boundary detection), `GroqDriftDetector` (§04/§10 goal
drift), `GroqContentPatternDetector` (content-pattern detector #6
above).

**Risk tiers** (`src/simulacrum/risk_tiers/`): every tool must be
registered with a tier (`READ_ONLY`, `REVERSIBLE_WRITE`,
`IRREVERSIBLE_LOW_VALUE`, `IRREVERSIBLE_HIGH_VALUE`) before it can be
called at all — this governs fail-open/fail-closed behavior when the
guardrail itself is degraded (circuit breaker open).

**Session storage**: `SessionStore` protocol
(`src/simulacrum/session/`) with two implementations —
`InMemorySessionStore` (tests) and `RedisSessionStore` (production,
now with a real, configurable TTL, default 24h, refreshed on every
write — see §19 in the completed-work list below).

**Real HTTP API** (`src/simulacrum/api/app.py`, `state.py`): FastAPI
app with `/health`, `/metrics` (Prometheus), `POST /sessions`, `POST
/sessions/{id}/turn`, `POST /sessions/{id}/intercept`, `GET/POST
/approvals/{id}`, `POST /sessions/{id}/check-drift` (on-demand goal-
drift check), `GET /sessions/{id}/drift-status` (retrieves the
background scheduler's standing decision without triggering a new
check). Real FastAPI `lifespan` events start/stop a genuine async
background `DriftScheduler` (`attribution/drift_scheduler.py`).

**Task simulation** (`src/simulacrum/task_sim/`): the ONE shared
normal-session generator (§08's own rule — never reimplemented
independently by any other script). **5 task types** currently:
`INBOX_TRIAGE`, `FLIGHT_BOOKING`, `CALENDAR_SCHEDULING`,
`FILE_SHARING`, `CONTACT_UPDATE` (meets §08's 5-8 minimum target).
Adding a new task type requires touching **5 files consistently**:
`task_sim/session.py`, `task_sim/task_text.py`,
`interception/fake_tools.py` (tier registration + stub impl),
`detectors/schema.py` (schema registration), `attribution/call_text.py`
(call-topic verbalizer template) — missing any one of these causes
real, immediate test failures (`UnregisteredSchemaError`,
`UnregisteredToolError`, or `KeyError`), which is exactly what
happened (and was fixed) when file_sharing/contact_update were added.

**Attack corpus** (`src/simulacrum/attack_suite/`): all 6 blueprint
§04 attack classes — injection, param_tampering (missing/unexpected),
permission_escalation, exfiltration (frequency/content), loop_evasion.
(Goal drift is the 6th "attack class" conceptually but is implemented
as a detector, `GroqDriftDetector`, not a corpus generator — see
decision 001.)

**§16 adversarial suite** (`src/simulacrum/adversarial/`):
`gradual_escalation.py`, `adaptive_evasion.py`,
`calibration_poisoning.py` — all three built, all three produced real
findings (007, and the calibration-poisoning work behind finding 008).

**§08 Layer 3/4 — generalization & external validation**
(`src/simulacrum/generalization_set/`): `mutated_attacks.py` (Layer
3, held-out internal set) and `agentdojo_adapter/` (Layer 4, REAL
external validation against the AgentDojo benchmark framework — see
§5 below for the real data that already exists on disk).

**§17 drift/re-baselining pipeline** (`src/simulacrum/drift/`):
`psi.py` (Population Stability Index), `version_trigger.py`
(event-driven immediate recalibration on model/version change),
`promotion_gate.py` (champion/challenger promotion, real and tested —
correctly REJECTED an appealing-looking fix this session, see finding
010's third correction round).

**Evaluation & reporting** (`src/simulacrum/evaluation/`):
`calibration_report.py` (Brier score + reliability diagram),
`calibration_manifest.py` (§11 Palimpsest-bug-#2 guard — catches
threshold drift between documented calibration and live config),
`task_completion_report.py` (§02's required metric — found a real 20%
false-positive task-cost rate, root-caused and fixed this session),
`input_only_baseline.py` (§10's required baseline — found this
session's most philosophically significant result: it OUTPERFORMED
the session-aware divergence detector on real external data).

**Redaction** (`src/simulacrum/redaction/`): `redactor.py`, §19's
"day-one requirement" that had never been built until this session's
blueprint re-audit found the gap — wired into the API's
explanation/reasoning fields, which previously leaked real sensitive
content (emails, SSNs) via LLM reasoning text verbatim.

**Shadow mode**: `intercept_and_call()` has a real `shadow_mode: bool
= False` parameter — when active, the real tier decision is still
computed and recorded, but the action ALWAYS executes (never actually
blocked/held). Core mechanism only; full graduation-criteria
automation (volume/time tracking) is NOT built — see remaining work.

**Config** (`src/simulacrum/config/settings.py`): `Settings`
dataclass, eagerly validated, NO default resource URLs ever (the
project's own hard rule, from Palimpsest's bug #1). `redis_url` is
required; `groq_api_key`, `hf_token` are the two deliberate,
documented optional exceptions.

---

## 4. Complete Real Work History (What's Done)

**Phase 0 (Foundations): 100%.** Config, risk tiers, task_sim, sub-
task boundary logic, sample-size gates.

**Phase 1 (MVP): ~99%.** All 6 detectors, all 6 attack classes, full
tier engine, real HTTP API, real Redis, real observability, Docker
Compose, real async background drift scheduling. Only the documented
per-detector-circuit-breaker tradeoff remains (deliberate, not an
oversight).

**Phase 2 (Hardening): the large majority of this whole session's
work.** In rough chronological order across this conversation:
- Goal-drift detector built, found+fixed a real prompt-design bug
  (forced one-word verdicts suppressed reasoning and gave wrong
  answers)
- §16's full adversarial suite (gradual escalation → finding 007's
  complete-blind-spot discovery and the content-pattern detector built
  to close it; adaptive evasion; calibration poisoning → finding 008's
  discovery that min-margin calibration is vulnerable to single-sample
  poisoning, fixed via percentile derivation)
- Finding 008's percentile threshold adopted in production
  (`MINILM_DIVERGENCE_THRESHOLD=0.3030`), evidence-based percentile
  sweep, ~65x more poisoning-resistant
- §08 Layer 3 (held-out generalization: 100% recall, 0% FP on our own
  internal held-out corpus) and Layer 4 (REAL AgentDojo external
  benchmark: 984 real tests, real GPT-4o-mini API cost ~$0.56, real
  data on disk in `./runs/` — gitignored but present)
- **Finding 010** (the single most-corrected, most-scrutinized result
  in the project): a three-round investigation into why MiniLM
  underperforms on real external data. Round 1 used a flawed ground-
  truth proxy. Round 2's "correction" had the ground-truth polarity
  INVERTED (a real, serious mistake, caught by reading AgentDojo's own
  source code and cross-checking 19 real files). Round 3 is the
  verified-correct final state: MiniLM 78.4% recall / 74.7% FP,
  fake embedder 90.0% / 85.2% on real attacks vs. real resisted
  trajectories. A real, tested partial fix (exclude low-param calls
  from aggregation) was found, formally verified via the §17
  promotion gate, ported to production, then CAUGHT AS A REGRESSION
  by our own §08 Layer 3 test (broke the previously-verified 0%
  internal false-positive guarantee) — correctly reverted. This
  remains the single most important open item (see §5 below).
- §17's full drift/re-baselining pipeline (PSI, version trigger,
  promotion gate)
- §05/§15 formal calibration reporting: single-detector Brier score
  (0.2333, barely above coin-flip — honest, sobering), system-level
  combination attempts (binary flags: 0.4146, WORSE; continuous
  confidence: 0.2673, better but still short of single-detector alone)
- Decision 001: LLM reasoning formally accepted as the §10 substitute
  for a literal trajectory sequence model, with explicit revisit
  conditions
- 5 task types (meeting §08's minimum), with real MiniLM calibration
  work required for the new tools (not just plumbing)
- Real CI (`.github/workflows/ci.yml`): Redis service container,
  import-order check (finding 003), full suite, fresh-venv
  reproducibility check
- Real calibration manifest (§11, Palimpsest bug #2 guard)
- **A full blueprint re-audit** (re-reading the source spec against
  the built system) found FIVE more real, previously-unnoticed gaps,
  all fixed this session:
  1. §19 redaction — was completely unbuilt; real sensitive content
     was leaking through LLM reasoning into HTTP API responses
  2. §19 session-data TTL — `RedisSessionStore` had zero expiry,
     contradicting the stated "used transiently... then discarded"
     requirement
  3. §02 task-completion-rate reporting — building and running this
     for the first time found a REAL 20% false-positive task-cost
     rate, root-caused to a genuine regex bug (flagged any single
     email address instead of genuine bulk-data shape), fixed and
     re-verified at 0%
  4. §13 shadow mode — core enforcement-bypass mechanism was entirely
     missing
  5. §10 input-only classifier baseline — building and running this
     produced the session's most philosophically significant result:
     it OUTPERFORMED our own session-aware divergence detector on
     real external data, directly challenging the project's own core
     stated thesis (see §5 below — this is now the SECOND most
     important open item)

**Phase 3 (Stretch): ~5%, untouched by design.** Multi-instance
circuit-breaker state, independent ops/security-approver role, second
agent-framework integration, exportable investigation report, web UI —
all explicitly out of MVP scope per the blueprint's own §23.

**Current real state:** 76 commits, 306 tests passing (fewer without
`GROQ_API_KEY`/`[ml]` extras — those tests skip cleanly, this is
expected and correct), 10 documented findings, 1 formal decision
record.

---

## 5. Remaining Work — Real, Current, Prioritized

This is a real summary of `docs/BACKLOG.md`'s actual current state —
but **always re-read the real file directly** (`cat docs/BACKLOG.md`)
before starting work, since it may have changed.

### Priority 1 — Finding 010's core generalization gap (STILL OPEN)
The real, fundamental question: our divergence detector's real recall/
FP numbers on external data (78.4%/74.7% MiniLM) are worse than they
should be, and a tested partial fix was found to regress our own
internal held-out guarantee when ported to production. **Genuinely
unresolved.** Real candidate directions, none fully attempted: a
larger/more structurally diverse internal calibration corpus; treating
divergence's role differently for long/complex sessions (leaning more
on content-pattern, which consistently outperforms it); accepting the
current numbers as a stated, honest limitation.

### Priority 2 — §10's input-only-baseline finding (STILL OPEN, newly significant)
A real, uncomfortable finding: a naive single-message LLM classifier
with NO session context (90.0% recall) beat our session-aware
divergence detector (78.4% recall) on the same real data. The honest
interpretation (documented in `docs/CALIBRATION_REPORT.md`) is that
this likely conflates reasoning-sophistication with context-
availability rather than cleanly testing whether session-awareness
itself helps. **Real, valuable, NOT-yet-attempted follow-up:** a
cleaner test — LLM reasoning WITH session/task context vs. WITHOUT,
holding the underlying mechanism constant — would actually isolate the
variable this project's core thesis depends on. Also worth testing:
goal drift specifically requires trajectory awareness by definition
(an input-only classifier structurally cannot evaluate "does this
SEQUENCE deviate from the goal" one call at a time) — this may be
where session-awareness's real value actually lives, and it's
untested.

### Priority 3 — §10's remaining two required baselines
1. **"Explicit-detectors-only baseline"** — concrete, well-scoped, NOT
   yet built: does the LLM-based goal-drift detector earn its real
   cost/complexity over the explicit detectors alone? Run real
   AgentDojo trajectories through the explicit-detector set with and
   without goal-drift, compare recall/FP.
2. **"Earliest-anomaly-onset baseline"** — genuine ambiguity in the
   source blueprint itself (verified via direct text search — the
   phrase appears exactly once, with no further specification
   anywhere in the document). Cannot be built with confidence without
   guessing at unstated intent. A reasonable but unverified
   interpretation is noted in the backlog.

### Lower priority, real, well-understood
- Per-detector circuit breakers (currently one breaker wraps all 6
  detectors — a documented, deliberate scope tradeoff, not an
  oversight)
- `FAKE_DIVERGENCE_THRESHOLD` was never given the same joint-
  recalibration treatment as MiniLM's threshold — deprioritized, since
  finding 010 already showed this exact class of joint recalibration
  is genuinely hard even for the primary embedder
- System-level calibration: a smarter, non-naive combination rule
  across detectors (weighted by confidence, or using content-pattern
  to break ties near divergence's threshold) — both binary and
  simple-average continuous combination were tried and both
  underperformed single-detector divergence alone; a real, open
  problem
- Shadow mode's full graduation-criteria automation (volume/time
  tracking to auto-recommend leaving shadow mode) — only the core
  enforcement-bypass mechanism is built
- `APPROVAL_QUEUE_DEPTH` is a single unlabeled global gauge — correct
  for the current architecture, would need per-queue labeling only if
  a future ops/security-approver role introduces genuinely separate
  queues

### Explicitly out of scope (Phase 3 / correctly deferred, not gaps)
- Cross-agent/multi-agent injection propagation (needs a real
  multi-agent framework decision first)
- Multi-instance circuit-breaker state, independent ops/security-
  approver role, second agent-framework integration, exportable
  investigation report, polished web UI — all explicitly Phase 3 per
  the blueprint's own §23

### README.md — deliberately deferred
Masum has explicitly requested the README be written LAST, once the
project is complete, so it can include real screenshots, graphs, and
tables rather than being written prematurely. Do not write it until
told to.

---

## 6. Environment Setup (Real, Verified)

- **Redis**: `docker compose ps` to check; `docker compose up -d` if
  down. Container: `simulacrum-redis-1`, port 6379.
- **`.env` file** (gitignored, real secrets): contains
  `SIMULACRUM_REDIS_URL`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `HF_TOKEN`.
  Source with `set -a; source .env; set +a` before any command needing
  these.
- **`SIMULACRUM_USE_REAL_EMBEDDINGS=1`** — opt-in env var for real
  MiniLM instead of the default fake embedder. **Always `unset` this
  explicitly after use** — it has caused real, confusing false alarms
  this session by staying exported across unrelated later commands in
  the same shell.
- **`./runs/` directory** — real AgentDojo benchmark data (984 real
  test result files), gitignored but present on disk. Required for
  any finding-010-related or `agentdojo_adapter`-related work. Do NOT
  delete it.
- **Fresh-venv verification pattern** (used repeatedly this session to
  catch real environment-dependent bugs):

python3 -m venv /tmp/check
/tmp/check/bin/pip install --upgrade pip --quiet
/tmp/check/bin/pip install -e ".[dev]" --quiet
/tmp/check/bin/python -m pytest tests/unit/ 2>&1 | tail -10
rm -rf /tmp/check

- **Full test suite**: `python3 -m pytest tests/unit/` — expect
  306 passed with `GROQ_API_KEY` sourced, fewer + skips without it
  (this is correct, not a bug).

---

## 7. A Few Hard-Won Specific Lessons Worth Remembering

- **Stale hardcoded test totals**: when adding a new task type or
  attack variant, tests that hardcode a total count (e.g. `assert
  total == 180`) will break — replace with a computed formula (e.g.
  `len(TaskType) * len(ATTACK_TOOLS) * 20`), don't just update the
  magic number.
- **LLM non-determinism is real but should be MEASURED, not
  hand-waved.** Finding 009: a test case was dismissed as "flaky" three
  times before actually measuring its real inconsistency rate (30%,
  via 10 independent real calls) and fixing the test properly with a
  statistically-grounded majority-vote assertion instead of asserting
  single-call determinism the case didn't actually have.
- **AgentDojo's own `--max-workers` has a real bug** (multiprocessing
  path crashes with `AttributeError: 'str' object has no attribute
  'name'`) — run sequentially, this is not our bug to fix.
- **Groq has a daily token quota** on the free tier — real, hit once
  this session during heavy testing. A new API key does NOT help
  (quota is per-organization). Either wait for reset or upgrade tier.
- When editing a file and a `python3 -c` string-replace assertion
  fails, the script aborts WITHOUT writing anything (safe), but this
  wastes a turn — go straight to viewing the real file and using
  heredoc/sed/line-based editing instead of guessing again.

---

## 8. First Steps For The New Conversation

1. Confirm real environment state (Redis, git log, test suite, env
   vars) per §6 above.
2. Re-read `docs/BACKLOG.md` directly (`cat docs/BACKLOG.md`) — it is
   the real, current source of truth, more current than this handoff
   document's §5 summary if any drift has occurred.
3. Ask Masum which of the remaining items (§5 above) to prioritize —
   most likely candidates given the real state: either continuing
   finding 010's investigation (the session-context-isolation
   experiment), building the explicit-detectors-only baseline, or
   moving toward Phase 3 stretch goals.
4. Proceed using the exact working method in §2 — one real step at a
   time, view before editing, verify with real output after every
   change, document findings/decisions as they occur, commit after
   each completed unit of work.
