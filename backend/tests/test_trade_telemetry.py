from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import httpx
import pytest

from app.auth import Principal, get_current_principal
from app.main import app
from app.models import TradeResult
from app.repositories import TradeRepository

ORGANIZATION_ID = UUID("e1cfb3b6-2cb7-4a45-9812-0c3e647d8b78")
TRADE_ID = UUID("e7a401fc-3c16-4a57-a980-e6b78c893659")
SEEDED_CASE = {
    "id": TRADE_ID,
    "external_reference": "TR-2026-001",
    "status": "verified",
    "goods_description": "Coffee beans",
    "hs_code": "090111",
    "hs_code_confidence": None,
    "origin_country": "KE",
    "destination_country": "GH",
    "cif_amount": Decimal("1250.00"),
    "currency": None,
    "origin_eligible": None,
    "origin_decision": {},
    "rigs_score": Decimal("0.82"),
    "rigs_components": {},
    "settlement_status": "not_eligible",
    "paypal_payout_batch_id": None,
    "error_code": None,
    "preferential_margin": Decimal("0.15"),
    "created_at": datetime(1970, 1, 1, tzinfo=UTC),
    "updated_at": datetime(1970, 1, 1, tzinfo=UTC),
}


class StubConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.query = ""
        self.args: tuple[object, ...] = ()

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.query = query
        self.args = args
        return self.rows


class StubPool:
    def __init__(self, connection: StubConnection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


@pytest.mark.asyncio
async def test_list_cases_normalizes_seeded_trade_case_columns() -> None:
    connection = StubConnection([SEEDED_CASE])
    repository = TradeRepository(StubPool(connection))  # type: ignore[arg-type]

    rows = await repository.list_cases(ORGANIZATION_ID, None, 100)
    case = TradeResult.model_validate(dict(rows[0]))

    assert case.external_reference == "TR-2026-001"
    assert case.cif_amount == Decimal("1250.00")
    assert case.currency is None
    assert case.preferential_margin == Decimal("0.15")
    assert "to_jsonb(trade_case)" in connection.query
    assert "reference_number" in connection.query
    assert "cif_value" in connection.query
    assert "trade_case.organization_id = $1" in connection.query
    assert connection.args == (ORGANIZATION_ID, None, None, 101)


@pytest.mark.asyncio
async def test_list_trades_returns_seeded_case_as_http_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = Principal(
        user_id=UUID("35dd6995-6aeb-4f02-a4f8-82531e5a793b"),
        email="trader@example.com",
        organization_id=ORGANIZATION_ID,
        role="admin",
    )

    async def list_cases(
        self: TradeRepository,
        organization_id: UUID,
        before: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[dict[str, object]]:
        assert organization_id == ORGANIZATION_ID
        assert before is None
        assert limit == 100
        return [SEEDED_CASE]

    monkeypatch.setitem(app.dependency_overrides, get_current_principal, lambda: principal)
    monkeypatch.setattr(TradeRepository, "list_cases", list_cases)
    monkeypatch.setattr(app.state, "database", object(), raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/trades?limit=100")

    assert response.status_code == 200
    assert response.json()["items"][0]["external_reference"] == "TR-2026-001"
    assert response.json()["items"][0]["cif_amount"] == "1250.00"
    assert response.json()["items"][0]["preferential_margin"] == "0.15"
