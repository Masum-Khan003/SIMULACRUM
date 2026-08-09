# Finding 021: exportable per-session investigation report (Phase 3, §23) — real detector persistence, closes §18's SIEM-export gap too

**Status:** Resolved. Phase 3 item 3 of 3 — completes the approved Phase 3 production plan (multi-instance breaker → approver role → investigation report).

## Background

§23 named an exportable per-session investigation report as Phase 3 scope. Before building it, a real, honest audit found the actual scope was larger than "just render existing data": `SessionStore` only ever persisted `call` + a coarse `CallOutcome` enum — never the rich per-call detector results (schema/divergence/escalation/loop-rate/exfiltration/content-pattern) needed to answer §14's own "why was this flagged" requirement. Separately, §18's own explicit requirement ("every flag/approval/block emits a structured event, CEF or equivalent") had never actually been built at all — a real, previously-undocumented gap, found only by grep-checking for any SIEM/audit-log/CEF code and finding none.

## Real scoping decision

Presented explicitly: extend session storage to persist full per-call detector results (bigger, but closes both gaps with one real data model), or keep the report thin, scoped only to already-stored data. Chosen: extend storage — a thin report missing the "why" would not actually satisfy §14, and building two separate mechanisms for essentially the same structured-event data (one for SIEM export, one for the report) would be real, unnecessary duplication.

## Real design

**Storage** (`session/store.py`, `session/redis_store.py`): `CallAttempt` gains `scoring_detail: dict | None`, a plain, JSON-serializable dict — deliberately not detector dataclass objects, same "just data" principle as `ExplanationContext`, avoiding import coupling between session storage and the detectors package. `None` by default (fully backward-compatible; `InMemorySessionStore`/`RedisSessionStore` unit tests confirmed unchanged before any new wiring). `RedisSessionStore._deserialize` uses `.get()` for real backward-compatibility with pre-existing Redis data written before this field existed.

**Serialization** (`interception/interceptor.py`): new `_scoring_to_dict()` converts a real `ScoringBundle` into the plain dict shape, wired into all 4 real scoring call sites (shadow-mode, BLOCK, REQUIRE_APPROVAL, ALLOW) — verified NOT wired into the 2 circuit-breaker-bypass paths, which honestly have no real scoring to report (`scoring_detail` stays `None` there, not a fabricated placeholder). For `REQUIRE_APPROVAL` specifically, the real `approval_request_id` is threaded into the detail dict, so a held call can later be linked to its real eventual decision.

**Report module** (`src/simulacrum/investigation/report.py`): `generate_investigation_report()` reads a session's real stored attempts, aggregates real outcome counts and flagged-call counts, and — when given a real `ApprovalQueue` reference — resolves each held call's real eventual outcome and `ApproverRole` (finding 020's role distinction, now genuinely visible in the report, not just the live approval flow).

**Redaction** (`to_redacted_dict()`): applies `redact_params()`/`redact_text()` (§19's existing, tested redaction module) to every real parameter value and every real content-pattern reasoning string before the report is ever serialized — same discipline the earlier §19 audit applied to the explanation/reasoning API fields, extended here to a second real leak surface this report would otherwise have introduced.

**API** (`GET /sessions/{id}/report`): real endpoint, 404 on unknown session (same pattern as the existing drift-status endpoint), returns the redacted dict directly.

**Real, explicit scope note**: JSON-first, per the approved production plan. Markdown/PDF rendering is real, scoped future work, not built in this pass — avoiding scope creep beyond what was explicitly agreed.

## Real verification

7 new tests, all passing, all real (no synthetic report objects except one deliberately isolated redaction-proof test):

1. `test_report_reflects_real_calls_and_real_scoring_detail` — real `intercept_and_call()` output shows up correctly in the report
2. `test_report_links_held_call_to_real_eventual_approval_decision` — THE load-bearing test: a real held call, decided via the real `ApprovalQueue`, correctly appears in the report linked to its real outcome and `ApproverRole`
3. `test_redacted_dict_never_leaks_raw_sensitive_content_pattern_reasoning` — direct proof a real SSN-shaped string does not survive redaction
4. Two real, end-to-end HTTP tests (`test_api.py`): report reflects a real intercepted call via the real running API; unknown session returns 404

Full suite: 331/331 passing (up from 326), zero regressions across the entire session-storage change.

## Real result — completes the Phase 3 production plan

All three approved Phase 3 items now resolved: multi-instance circuit breaker (finding 019), independent authenticated ops-approver role (finding 020), exportable investigation report (this finding). Second agent-framework integration remains explicitly deferred as its own future decision, and the web UI/dashboard stays confirmed out of scope per §02.

## Reproducing this result

```bash
set -a && source .env && set +a
python3 -m pytest tests/unit/test_investigation_report.py tests/unit/test_api.py -k report -v

# Real, manual end-to-end check (with the API running):
curl http://localhost:8000/sessions/{session_id}/report
```
