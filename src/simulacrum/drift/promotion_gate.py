"""
Champion/challenger promotion gate (§17): a recalibrated detector
CHALLENGER is promoted to CHAMPION only if it matches or exceeds the
current champion's recall on EVERY attack class in the labeled corpus
AND does not regress false-positive rate. Direct reuse of Palimpsest's
own gate logic, applied to Simulacrum's attack classes.

Real, honest scope: this gate operates on already-computed metric
dictionaries (per-attack-class recall + overall false-positive rate),
not on live model objects -- callers are responsible for actually
running both champion and challenger configurations against the real
labeled corpus (attack_suite/ + task_sim/) and producing these metrics,
same separation-of-concerns as the rest of this project's evaluation
code.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DetectorMetrics:
    recall_by_attack_class: dict[str, float]
    false_positive_rate: float


@dataclass(frozen=True)
class PromotionDecision:
    should_promote: bool
    reasons: tuple[str, ...]


def evaluate_promotion(
    *, champion: DetectorMetrics, challenger: DetectorMetrics
) -> PromotionDecision:
    """
    Real gate logic: challenger must have recall >= champion on EVERY
    attack class the champion was measured against (a challenger
    missing an attack class the champion covers is a regression, full
    stop), AND false_positive_rate must not increase.
    """
    reasons = []
    should_promote = True

    for attack_class, champion_recall in champion.recall_by_attack_class.items():
        challenger_recall = challenger.recall_by_attack_class.get(attack_class)
        if challenger_recall is None:
            should_promote = False
            reasons.append(
                f"Challenger has NO measurement for attack class '{attack_class}' "
                f"that champion covers (champion recall={champion_recall:.3f}) -- "
                f"cannot verify no regression, refusing promotion."
            )
        elif challenger_recall < champion_recall:
            should_promote = False
            reasons.append(
                f"Recall regression on '{attack_class}': "
                f"champion={champion_recall:.3f}, challenger={challenger_recall:.3f}"
            )

    if challenger.false_positive_rate > champion.false_positive_rate:
        should_promote = False
        reasons.append(
            f"False-positive rate regression: "
            f"champion={champion.false_positive_rate:.3f}, "
            f"challenger={challenger.false_positive_rate:.3f}"
        )

    if should_promote:
        reasons.append(
            "Challenger matches or exceeds champion on every measured attack "
            "class with no false-positive-rate regression -- promotion approved."
        )

    return PromotionDecision(should_promote=should_promote, reasons=tuple(reasons))
