from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models import TariffRule, TradeCreate
from app.services.compliance import decide_origin


def value_added_rule() -> TariffRule:
    return TariffRule(
        id=uuid4(),
        organization_id=None,
        agreement="AfCFTA",
        hs_code_prefix="6109",
        origin_country="KE",
        destination_country="GH",
        rule_type="value_added",
        minimum_value_added_pct=Decimal("35.00"),
        required_tariff_heading_prefix=None,
        excluded_inputs=[],
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )


def trade(value_added_pct: str = "40.00") -> TradeCreate:
    return TradeCreate(
        goods_description="Cotton t-shirt",
        origin_country="KE",
        destination_country="GH",
        cif_amount=Decimal("100.00"),
        currency="USD",
        value_added_pct=Decimal(value_added_pct),
    )


def test_matching_sourced_rule_requires_documentary_evidence() -> None:
    decision = decide_origin(
        trade(),
        "610910",
        [value_added_rule()],
        [],
        has_document=False,
        evidence_confidence=1,
        documented_wholly_obtained=None,
        documented_value_added_pct=40,
        documented_tariff_heading=None,
    )

    assert decision.verified is False
    assert "supporting document" in decision.reason


def test_value_added_requires_document_to_corroborate_declaration() -> None:
    decision = decide_origin(
        trade(),
        "610910",
        [value_added_rule()],
        [],
        has_document=True,
        evidence_confidence=0.91,
        documented_wholly_obtained=None,
        documented_value_added_pct=40,
        documented_tariff_heading=None,
    )

    assert decision.verified is True
    assert decision.confidence == 0.91


def test_value_added_mismatch_fails_closed() -> None:
    decision = decide_origin(
        trade(),
        "610910",
        [value_added_rule()],
        [],
        has_document=True,
        evidence_confidence=1,
        documented_wholly_obtained=None,
        documented_value_added_pct=45,
        documented_tariff_heading=None,
    )

    assert decision.verified is False


def test_missing_rule_fails_closed() -> None:
    decision = decide_origin(
        trade(),
        "610910",
        [],
        [],
        has_document=True,
        evidence_confidence=1,
        documented_wholly_obtained=None,
        documented_value_added_pct=40,
        documented_tariff_heading=None,
    )

    assert decision.verified is False
    assert decision.rule_id is None
