"""
Verifies the champion/challenger promotion gate (§17). Includes a real
scenario built from THIS SESSION's actual finding-010 data: does the
gate correctly evaluate the real min-param-exclusion fix against the
real baseline recall/FP numbers we measured?
"""
from simulacrum.drift.promotion_gate import DetectorMetrics, evaluate_promotion


def test_challenger_matching_champion_on_everything_is_promoted():
    champion = DetectorMetrics(recall_by_attack_class={"injection": 0.9}, false_positive_rate=0.05)
    challenger = DetectorMetrics(recall_by_attack_class={"injection": 0.9}, false_positive_rate=0.05)
    decision = evaluate_promotion(champion=champion, challenger=challenger)
    assert decision.should_promote is True


def test_challenger_exceeding_champion_is_promoted():
    champion = DetectorMetrics(recall_by_attack_class={"injection": 0.85}, false_positive_rate=0.05)
    challenger = DetectorMetrics(recall_by_attack_class={"injection": 0.92}, false_positive_rate=0.03)
    decision = evaluate_promotion(champion=champion, challenger=challenger)
    assert decision.should_promote is True


def test_challenger_with_recall_regression_on_one_class_is_rejected():
    champion = DetectorMetrics(
        recall_by_attack_class={"injection": 0.9, "escalation": 0.95}, false_positive_rate=0.05
    )
    challenger = DetectorMetrics(
        recall_by_attack_class={"injection": 0.9, "escalation": 0.80}, false_positive_rate=0.05
    )
    decision = evaluate_promotion(champion=champion, challenger=challenger)
    assert decision.should_promote is False
    assert any("escalation" in r for r in decision.reasons)


def test_challenger_with_fp_regression_is_rejected_even_with_better_recall():
    champion = DetectorMetrics(recall_by_attack_class={"injection": 0.85}, false_positive_rate=0.05)
    challenger = DetectorMetrics(recall_by_attack_class={"injection": 0.99}, false_positive_rate=0.20)
    decision = evaluate_promotion(champion=champion, challenger=challenger)
    assert decision.should_promote is False
    assert any("False-positive" in r for r in decision.reasons)


def test_challenger_missing_an_attack_class_champion_covers_is_rejected():
    champion = DetectorMetrics(
        recall_by_attack_class={"injection": 0.9, "exfiltration": 0.8}, false_positive_rate=0.05
    )
    challenger = DetectorMetrics(recall_by_attack_class={"injection": 0.95}, false_positive_rate=0.03)
    decision = evaluate_promotion(champion=champion, challenger=challenger)
    assert decision.should_promote is False
    assert any("exfiltration" in r for r in decision.reasons)


def test_real_finding_010_scenario_min_aggregation_vs_low_param_exclusion():
    """
    REAL data from this session: does the min-param-exclusion fix
    (finding 010) pass the promotion gate? Using the REAL measured
    numbers: champion (raw min) recall=78.4%/FP=74.7%, challenger
    (filtered) recall=73.1%/FP=59.7% (MiniLM, real AgentDojo data).

    This is a genuinely INTERESTING real case: FP improves a lot, but
    recall REGRESSES (78.4% -> 73.1%) -- per the gate's own strict
    rule (recall must not regress on ANY measured class), this should
    be REJECTED, even though the overall tradeoff looks appealing.
    This is the gate doing its job: catching a real recall regression
    that a human might be tempted to wave through because the FP
    improvement looks good.
    """
    champion = DetectorMetrics(
        recall_by_attack_class={"agentdojo_real_attacks": 0.784}, false_positive_rate=0.747
    )
    challenger = DetectorMetrics(
        recall_by_attack_class={"agentdojo_real_attacks": 0.731}, false_positive_rate=0.597
    )
    decision = evaluate_promotion(champion=champion, challenger=challenger)
    assert decision.should_promote is False, (
        "Real finding-010 data: the min-param-exclusion fix has genuine recall "
        "regression despite better FP rate -- the gate should correctly reject "
        "automatic promotion, flagging it for human review instead."
    )
