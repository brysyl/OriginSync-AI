from app.services.rigs import calculate_rigs


def test_rigs_uses_weighted_components() -> None:
    result = calculate_rigs(
        risk_control_score=0.95,
        intent_alignment_score=0.9,
        growth_potential_score=0.8,
        stakeholder_trust_score=1.0,
        origin_verified=True,
        classification_confidence=0.92,
    )

    assert result.score == 0.917
    assert result.components.risk == 0.92
    assert result.components.missing_evidence == []


def test_rigs_is_not_computed_when_evidence_is_missing() -> None:
    result = calculate_rigs(
        risk_control_score=0.99,
        intent_alignment_score=None,
        growth_potential_score=0.8,
        stakeholder_trust_score=0.9,
        origin_verified=True,
        classification_confidence=0.99,
    )

    assert result.score is None
    assert "intent" in result.components.missing_evidence


def test_unverified_origin_blocks_rigs_score() -> None:
    result = calculate_rigs(
        risk_control_score=1,
        intent_alignment_score=1,
        growth_potential_score=1,
        stakeholder_trust_score=1,
        origin_verified=False,
        classification_confidence=1,
    )

    assert result.score is None
    assert "verified_origin" in result.components.missing_evidence


def test_low_classification_confidence_blocks_rigs_score() -> None:
    result = calculate_rigs(
        risk_control_score=0.7,
        intent_alignment_score=1,
        growth_potential_score=1,
        stakeholder_trust_score=1,
        origin_verified=True,
        classification_confidence=0.79,
    )

    assert result.score is None
    assert "classification_confidence" in result.components.missing_evidence
