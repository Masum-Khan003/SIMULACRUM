# Real README Table Data — compiled from docs/findings/001-021.md

## Table 1: Project summary (real, current state)

| Metric | Value |
|---|---|
| Total commits | 89+ |
| Tests passing | 331 |
| Documented findings | 21 |
| Formal decision records | 2 |
| Attack classes implemented | 6/6 (§04) |
| Task types | 5/5-8 (§08 minimum met) |
| Blueprint phases complete | 0, 1, 2 fully; 3's three approved items complete |

## Table 2: Findings index

| # | Title | Category |
|---|---|---|
| 001 | Fake-embedder similarity bias | Calibration |
| 002 | Divergence-threshold direction confusion | Bug fix |
| 003 | Detectors/interception circular import | Bug fix |
| 004 | Shared Prometheus gauge test isolation | Bug fix |
| 005 | Attack-target tool missing call-template collision | Bug fix |
| 006 | Task-anchor drift across refinements | Design |
| 007 | Divergence camouflage margin caught by escalation | Security gap closed |
| 008 | Calibration-poisoning min-margin vulnerability | Security hardening |
| 009 | Goal-drift real non-determinism rate | LLM behavior |
| 010 | MiniLM underperforms fake embedder on external benchmark | Generalization gap (closed by 014/015) |
| 011 | Explicit-detectors-only baseline | §10 baseline |
| 012 | Earliest-onset baseline — no signal | §10 baseline (honest negative) |
| 013 | Content-pattern rescue-rate analysis | Combination analysis |
| 014 | task_sim variable-length recalibration | **Root-cause fix** |
| 015 | Content-pattern FP audit — closes finding 010 | Ground-truth analysis |
| 016 | Context-isolation — session-awareness confirmed | Core thesis validation |
| 017 | Goal-drift input-only structural test | Core thesis validation |
| 018 | Tiebreak combination — closes system calibration | Combination analysis |
| 019 | Multi-instance circuit breaker | Phase 3 |
| 020 | Independent ops-approver role | Phase 3 |
| 021 | Exportable investigation report | Phase 3 |

## Table 3: Divergence detector — real recall/FP history

| Stage | Recall | FP rate | Source |
|---|---|---|---|
| Original (finding 010, MiniLM) | 78.4% | 74.7% | finding 010 |
| Fake embedder (finding 010) | 90.0% | 85.2% | finding 010 |
| Low-param exclusion (tested, reverted) | 73.1% | 59.7% | finding 010 |
| Threshold+exemption (tested, reverted — broke internal FP=0) | 78.8% | 66.2% | finding 010 |
| **After root-cause fix (finding 014)** | **81.6%** | **75.9%** | finding 014 |

## Table 4: Threshold recalibration history

| Constant | Original | Post-014 | Basis |
|---|---|---|---|
| `FAKE_DIVERGENCE_THRESHOLD` | 0.15 | 0.1581 | 1st-percentile, n=2730 |
| `MINILM_DIVERGENCE_THRESHOLD` | 0.20 → 0.3030 | 0.3307 | 1st-percentile, poisoning-resistant (finding 008 methodology) |
| `DEFAULT_RATE_THRESHOLD` (loop_rate) | 3 | 7 | 1 above real max legitimate repeat count (6) |
| `DEFAULT_OUTBOUND_FREQUENCY_THRESHOLD` (exfiltration) | 3 | 7 | Same evidence-based method |

## Table 5: System-level calibration — every combination rule tried

| Approach | Brier Score | Verdict |
|---|---|---|
| Divergence alone | 0.2333 | Best single detector |
| Binary-flag OR combination | 0.4146 | Worse |
| Continuous-confidence averaging | 0.2673 | Better than binary, still worse than alone |
| Targeted tiebreak (finding 018) | 0.2433 | Best combination attempt, still short of alone |

## Table 6: Core thesis validation (session-awareness)

| Test | Input-only | Context-aware / sequence-aware | Delta |
|---|---|---|---|
| Single-call classification (finding 016) | 61.7% recall / 55.0% FP | 83.3% recall / 58.3% FP | +21.7pp recall / +3.3pp FP |
| Goal-drift structural test (finding 017) | 0/5 real cases correctly cleared (flagged all, incl. legitimate) | 5/5 real cases correct | Structural, not just empirical |

## Table 7: §10 baselines (all three required, all resolved)

| Baseline | Result | Finding |
|---|---|---|
| Input-only classifier | 90.0% recall vs. divergence's 78.4% — significant, honestly reported | CALIBRATION_REPORT.md |
| Explicit-detectors-only | Goal-drift adds +3.3% recall at +0.0% FP cost | 011 |
| Earliest-anomaly-onset | No discriminative signal (honest negative) | 012 |

## Table 8: Content-pattern rescue analysis (finding 013)

| | Count | Rate |
|---|---|---|
| Real attacks divergence misses | 11 | — |
| ...rescued by content-pattern | 6 | 54.5% |
| Real resisted trajectories divergence clears | 14 | — |
| ...newly flagged by content-pattern | 5 | 35.7% |

## Table 9: Phase 3 delivery

| Item | Status | Finding |
|---|---|---|
| Multi-instance circuit-breaker state | Delivered, verified across replicas | 019 |
| Independent ops/security-approver role | Delivered, real API-key auth | 020 |
| Exportable per-session investigation report | Delivered, JSON + redaction | 021 |
| Second agent-framework integration | Deferred (decision 002) | — |
| Human-approval web UI | Out of scope per §02 (confirmed) | — |

## Table 10: Real test/finding growth (approximate session milestones)

| Milestone | Tests | Findings | Commits |
|---|---|---|---|
| Session start (handoff) | 306 | 10 | 76 |
| §10 baselines complete | 311 | 12 | 79 |
| Finding 010 closed | 316 | 15 | 84 |
| Session-awareness validated | 318 | 17 | 85 |
| System calibration closed | 318 | 18 | 85 |
| Phase 3 complete | 331 | 21 | 89 |
