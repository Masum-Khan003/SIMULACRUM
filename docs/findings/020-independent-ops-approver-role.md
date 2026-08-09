# Finding 020: independent ops/security-approver role (Phase 3, §13) — real, genuinely-authenticated, not self-reported

**Status:** Resolved. Phase 3 item 2 of 3.

## Background

§13's original MVP scope explicitly named a real, honest limitation: the approver is the task-initiating user, synchronous, embedded in the same conversational channel the agent is already using — this does NOT defend against an agent socially engineering the same user it's asking for approval from ("please approve this urgent transfer"). A separate, independent ops/security-approver role — genuinely out-of-band from the potentially-compromised session — was named explicitly as Phase 3+, not implied to already exist.

## Real scoping decision, made explicitly before building

Two honest options were presented: (1) a structural role distinction with self-reported claims only (no real auth — matches the existing MVP's honesty pattern, smaller scope), or (2) real, minimal authentication closing the gap for real (bigger scope). Explicitly chosen: **option 2** — a self-reported-only "role" field would not actually be out-of-band from a compromised session (nothing would stop a compromised agent/session from simply claiming the ops role), so it would not have resolved §13's stated limitation, only relabeled it.

## Real design

**Config** (`Settings`): added `ops_approver_api_key: str | None` as a third deliberate optional exception to the "no default, ever" rule (same pattern as `groq_api_key`/`hf_token`) — absence is valid, expected configuration for deployments not using this optional feature, not a misconfiguration.

**Data model** (`ApprovalQueue`): added `ApproverRole` enum (`TASK_INITIATING_USER` / `OPS_SECURITY_APPROVER`) and `ApprovalRequest.decided_by_role`. `decide()` gained an `approver_role` parameter defaulting to `TASK_INITIATING_USER` — the original MVP behavior is completely unchanged for existing callers; auth itself is NOT this method's job (kept cleanly separated from queue logic — this method only records which already-authenticated role decided).

**Real, genuine auth** (`api/app.py`): new `POST /approvals/{request_id}/ops-decide` endpoint, separate from the original `/decide`. Requires a real `X-Ops-Approver-Key` header matching `settings.ops_approver_api_key` exactly:
- If the setting is unconfigured (`None`): **503**, endpoint honestly disabled — never silently permissive, never treats an unset/empty key as valid.
- If the header doesn't match: **401**.
- Only on a genuine match does the decision get recorded with `ApproverRole.OPS_SECURITY_APPROVER`.

## Real, direct verification via HTTP (not just unit-level)

4 new tests in `tests/unit/test_api.py`, all real, all passing:
1. `test_ops_decide_returns_503_when_not_configured` — confirms honest disablement, not silent acceptance
2. `test_ops_decide_returns_401_with_wrong_key` — confirms a configured-but-wrong key is rejected
3. `test_ops_decide_succeeds_with_real_correct_key` — the load-bearing test: a genuinely correct key succeeds AND the decision is recorded with `ApproverRole.OPS_SECURITY_APPROVER`, proving the role distinction threads through end-to-end via real HTTP, not just at the class level
4. `test_regular_decide_still_records_task_initiating_user_role` — structural regression guard confirming the original endpoint's behavior is completely unchanged

Real, honest test-design note: `get_settings()` is `@lru_cache`'d — tests explicitly call `get_settings.cache_clear()` around `monkeypatch.setenv/delenv` to genuinely exercise both configured and unconfigured states within one test process, rather than relying on import-time state that wouldn't actually test the toggle.

## Real result

326/326 tests passing (up from 322), 4 new HTTP-level tests, zero regressions on the original approval flow (12 pre-existing approval-related tests confirmed still passing unchanged before any new code was added).

## Honest scope note

This closes the AUTHENTICATION gap in §13's stated limitation — decisions from the ops-approver role are now genuinely, cryptographically distinguishable from the task-initiating user's own channel, not just self-labeled. It does NOT build a full ops-approver *workflow* (e.g., a real notification/dashboard for ops staff to see pending requests) — that remains real, separate, un-scoped future work if ever needed; this finding closes the specific gap named in §13 (a genuinely independent, authenticated approval channel), not a broader ops-tooling product.

## Reproducing this result

```bash
set -a && source .env && set +a
python3 -m pytest tests/unit/test_api.py -k ops_decide -v

# Real, manual end-to-end check:
export SIMULACRUM_OPS_APPROVER_API_KEY="a-real-secret-key"
# start the API, then:
curl -X POST http://localhost:8000/approvals/{request_id}/ops-decide \
  -H "X-Ops-Approver-Key: a-real-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"approved": true}'
```
