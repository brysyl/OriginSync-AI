from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models import OriginDecisionStatus, TariffRule, TradeCreate
from app.services.compliance import decide_origin


def make_trade(**overrides: object) -> TradeCreate:
    values: dict[str, object] = {
        "goods_description": "Cotton t-shirt",
        "origin_country": "KE",
        "destination_country": "GH",
        "cif_amount": Decimal("100.00"),
        "currency": "USD",
        "value_added_pct": Decimal("40.00"),
    }
    values.update(overrides)
    return TradeCreate.model_validate(values)


def make_rule(
    *,
    rule_type: str = "value_added",
    hs_code_prefix: str = "610910",
    origin_country: str = "KE",
    destination_country: str = "GH",
    minimum_value_added_pct: Decimal | None = Decimal("40.00"),
    required_tariff_heading_prefix: str | None = None,
    excluded_inputs: list[dict[str, object]] | None = None,
) -> TariffRule:
    return TariffRule(
        id=uuid4(),
        agreement="AfCFTA",
        hs_code_prefix=hs_code_prefix,
        origin_country=origin_country,
        destination_country=destination_country,
        rule_type=rule_type,
        minimum_value_added_pct=minimum_value_added_pct,
        required_tariff_heading_prefix=required_tariff_heading_prefix,
        excluded_inputs=excluded_inputs or [],
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )


def decide(
    trade: TradeCreate,
    rule: TariffRule | None = None,
    *,
    hs_code: str = "610910",
    has_document: bool = True,
    evidence_confidence: float = 0.95,
    documented_wholly_obtained: bool | None = None,
    documented_value_added_pct: float | None = 40.0,
    documented_tariff_heading: str | None = None,
    excluded_materials: list[dict[str, object]] | None = None,
):
    return decide_origin(
        trade,
        hs_code,
        [rule] if rule is not None else [],
        excluded_materials or [],
        has_document=has_document,
        evidence_confidence=evidence_confidence,
        documented_wholly_obtained=documented_wholly_obtained,
        documented_value_added_pct=documented_value_added_pct,
        documented_tariff_heading=documented_tariff_heading,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("40.00", OriginDecisionStatus.VERIFIED),
        ("39.90", OriginDecisionStatus.REJECTED),
        ("40.10", OriginDecisionStatus.VERIFIED),
    ],
)
def test_value_addition_threshold_boundaries(
    value: str, expected: OriginDecisionStatus
) -> None:
    result = decide(
        make_trade(value_added_pct=Decimal(value)),
        make_rule(),
        documented_value_added_pct=float(value),
    )

    assert result.status is expected
    assert result.verified is (expected is OriginDecisionStatus.VERIFIED)


@pytest.mark.parametrize(
    ("rule_prefix", "required_prefix"),
    [("61", "61"), ("6109", "6109"), ("610910", "610910")],
)
def test_change_in_tariff_heading_at_two_four_and_six_digits(
    rule_prefix: str, required_prefix: str
) -> None:
    rule = make_rule(
        rule_type="change_in_tariff_classification",
        hs_code_prefix=rule_prefix,
        minimum_value_added_pct=None,
        required_tariff_heading_prefix=required_prefix,
    )
    trade = make_trade(non_originating_tariff_heading="520859")

    result = decide(
        trade,
        rule,
        documented_tariff_heading="520859",
    )

    assert result.status is OriginDecisionStatus.VERIFIED


def test_wholly_obtained_goods_require_both_declarations() -> None:
    rule = make_rule(rule_type="wholly_obtained", minimum_value_added_pct=None)
    result = decide(
        make_trade(wholly_obtained=True),
        rule,
        documented_wholly_obtained=True,
    )

    assert result.status is OriginDecisionStatus.VERIFIED


def test_wholly_obtained_claim_without_trade_declaration_is_rejected() -> None:
    rule = make_rule(rule_type="wholly_obtained", minimum_value_added_pct=None)
    result = decide(
        make_trade(wholly_obtained=None),
        rule,
        documented_wholly_obtained=True,
    )

    assert result.status is OriginDecisionStatus.REJECTED


def test_conflicting_wholly_obtained_evidence_is_rejected() -> None:
    rule = make_rule(rule_type="wholly_obtained", minimum_value_added_pct=None)
    result = decide(
        make_trade(wholly_obtained=True),
        rule,
        documented_wholly_obtained=False,
    )

    assert result.status is OriginDecisionStatus.REJECTED


@pytest.mark.parametrize("cif_amount", [Decimal("0"), Decimal("-0.01")])
def test_zero_and_negative_cif_amounts_are_invalid(cif_amount: Decimal) -> None:
    with pytest.raises(ValidationError):
        make_trade(cif_amount=cif_amount)


@pytest.mark.parametrize("hs_code", ["", "61A910", "12345", "12345678901"])
def test_malformed_classified_hs_codes_are_rejected(hs_code: str) -> None:
    result = decide(make_trade(), make_rule(), hs_code=hs_code)

    assert result.status is OriginDecisionStatus.REJECTED
    assert result.verified is False


def test_missing_origin_corridor_is_pending_audit() -> None:
    result = decide(make_trade(), make_rule(destination_country="NG"))

    assert result.status is OriginDecisionStatus.PENDING_AUDIT
    assert result.verified is False


@pytest.mark.parametrize("description", ["", "   "])
def test_nonconforming_goods_descriptions_are_invalid(description: str) -> None:
    with pytest.raises(ValidationError):
        make_trade(goods_description=description)


def test_missing_documentary_evidence_is_pending_audit() -> None:
    result = decide(make_trade(), make_rule(), has_document=False)

    assert result.status is OriginDecisionStatus.PENDING_AUDIT


def test_low_confidence_evidence_is_pending_audit() -> None:
    result = decide(make_trade(), make_rule(), evidence_confidence=0.79)

    assert result.status is OriginDecisionStatus.PENDING_AUDIT


def test_specific_process_rule_requires_manual_audit() -> None:
    rule = make_rule(rule_type="specific_process", minimum_value_added_pct=None)
    result = decide(make_trade(), rule)

    assert result.status is OriginDecisionStatus.PENDING_AUDIT


def test_excluded_materials_reject_otherwise_qualifying_origin() -> None:
    rule = make_rule(excluded_inputs=[{"code": "restricted-input"}])
    result = decide(
        make_trade(),
        rule,
        excluded_materials=[{"code": "restricted-input"}],
    )

    assert result.status is OriginDecisionStatus.REJECTED


def test_excluded_materials_reject_specific_process_rule() -> None:
    rule = make_rule(
        rule_type="specific_process",
        minimum_value_added_pct=None,
        excluded_inputs=[{"code": "restricted-input"}],
    )
    result = decide(
        make_trade(),
        rule,
        excluded_materials=[{"code": "restricted-input"}],
    )

    assert result.status is OriginDecisionStatus.REJECTED


def test_origin_decision_status_and_result_are_deterministic() -> None:
    trade = make_trade()
    rule = make_rule()
    first = decide(trade, rule)
    second = decide(trade, rule)

    assert isinstance(first.status, OriginDecisionStatus)
    assert first.status is second.status is OriginDecisionStatus.VERIFIED
    assert (first.verified, first.reason, first.confidence) == (
        second.verified,
        second.reason,
        second.confidence,
    )