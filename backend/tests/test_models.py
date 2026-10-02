from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import TradeCreate


def test_settlement_must_match_trade_currency() -> None:
    with pytest.raises(ValidationError, match="settlement currency must match"):
        TradeCreate(
            goods_description="Trade goods",
            origin_country="KE",
            destination_country="GH",
            cif_amount=Decimal("100.00"),
            currency="USD",
            beneficiary_email="payee@example.com",
            settlement_amount=Decimal("80.00"),
            settlement_currency="EUR",
        )


def test_settlement_cannot_exceed_cif_value() -> None:
    with pytest.raises(ValidationError, match="cannot exceed the documented CIF"):
        TradeCreate(
            goods_description="Trade goods",
            origin_country="KE",
            destination_country="GH",
            cif_amount=Decimal("100.00"),
            currency="USD",
            beneficiary_email="payee@example.com",
            settlement_amount=Decimal("100.01"),
            settlement_currency="USD",
        )
