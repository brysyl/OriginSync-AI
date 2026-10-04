from dataclasses import dataclass

from app.models import RigsComponents

WEIGHTS = {
    "risk": 0.35,
    "intent": 0.25,
    "growth": 0.15,
    "stakeholder": 0.25,
}
MINIMUM_SETTLEMENT_RIGS_SCORE = 0.75


def requires_settlement_review(score: float | None) -> bool:
    return score is not None and score < MINIMUM_SETTLEMENT_RIGS_SCORE


@dataclass(frozen=True)
class RigsResult:
    score: float | None
    components: RigsComponents


def calculate_rigs(
    *,
    risk_control_score: float | None,
    intent_alignment_score: float | None,
    growth_potential_score: float | None,
    stakeholder_trust_score: float | None,
    origin_verified: bool,
    classification_confidence: float,
) -> RigsResult:
    values = {
        "risk": risk_control_score,
        "intent": intent_alignment_score,
        "growth": growth_potential_score,
        "stakeholder": stakeholder_trust_score,
    }
    missing = [name for name, score in values.items() if score is None]
    if not origin_verified:
        missing.append("verified_origin")
    if classification_confidence < 0.8:
        missing.append("classification_confidence")

    risk = (
        min(risk_control_score, classification_confidence)
        if risk_control_score is not None and origin_verified
        else None
    )
    components = RigsComponents(
        risk=risk,
        intent=intent_alignment_score,
        growth=growth_potential_score,
        stakeholder=stakeholder_trust_score,
        missing_evidence=missing,
    )
    if missing:
        return RigsResult(score=None, components=components)

    assert risk is not None
    score = (
        WEIGHTS["risk"] * risk
        + WEIGHTS["intent"] * intent_alignment_score
        + WEIGHTS["growth"] * growth_potential_score
        + WEIGHTS["stakeholder"] * stakeholder_trust_score
    )
    return RigsResult(score=round(score, 4), components=components)
