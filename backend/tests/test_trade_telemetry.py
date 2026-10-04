from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

import app.auth as auth_module
import app.main as main_module
from app.auth import Principal, get_current_principal
from app.main import app, get_telemetry_principal
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
async def test_principal_falls_back_to_first_organization_for_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = UUID("35dd6995-6aeb-4f02-a4f8-82531e5a793b")

    class AuthConnection:
        async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
            if "organization_memberships" in query:
                return None
            assert "from public.organizations" in query
            return {"organization_id": ORGANIZATION_ID, "role": "viewer"}

    class AuthPool(StubPool):
        pass

    class AuthClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def __init__(self, **kwargs: object) -> None:
            pass

        async def get(self, *args: object, **kwargs: object) -> object:
            return SimpleNamespace(status_code=200, json=lambda: {"id": str(user_id)})

    monkeypatch.setattr(auth_module.httpx, "AsyncClient", AuthClient)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(
                    supabase_url="https://example.supabase.co",
                    supabase_anon_key=SecretStr("anon-key"),
                ),
                database=AuthPool(StubConnection([])),
            )
        )
    )
    request.app.state.database.connection = AuthConnection()

    principal = await get_current_principal(
        request, authorization="Bearer test-token", organization_id=None
    )

    assert principal.user_id == user_id
    assert principal.organization_id == ORGANIZATION_ID
    assert principal.role == "viewer"


@pytest.mark.asyncio
async def test_telemetry_principal_uses_guest_context_without_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class GuestConnection:
        async def fetchrow(self, query: str) -> dict[str, UUID]:
            assert "from public.organizations" in query
            return {"id": ORGANIZATION_ID}

    class GuestPool:
        @asynccontextmanager
        async def acquire(self):
            yield GuestConnection()

    async def reject_unauthenticated_request(*args: object) -> Principal:
        raise ValueError("token is missing")

    monkeypatch.setattr(main_module, "get_current_principal", reject_unauthenticated_request)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=GuestPool())))

    principal = await get_telemetry_principal(request)

    assert principal.user_id == UUID(int=0)
    assert principal.email is None
    assert principal.organization_id == ORGANIZATION_ID
    assert principal.role == "viewer"


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
async def test_list_telemetry_cases_queries_supabase_unscoped_and_maps_columns() -> None:
    class Query:
        def __init__(self) -> None:
            self.table_name = ""
            self.columns = ""

        def table(self, table_name: str) -> "Query":
            self.table_name = table_name
            return self

        def select(self, columns: str) -> "Query":
            self.columns = columns
            return self

        def execute(self) -> SimpleNamespace:
            return SimpleNamespace(
                data=[
                    {
                        "organization_id": UUID("afd7ea02-8e5d-468d-a551-8d0aa2855102"),
                        "reference_number": "TR-1",
                        "goods_description": "Coffee",
                        "origin_country": "KE",
                        "destination_country": "GH",
                        "hs_code": "090111",
                        "cif_amount": Decimal("100"),
                        "origin_eligible": True,
                        "rigs_score": 80,
                        "settlement_status": "PENDING",
                        "case_status": "verified",
                    }
                ]
            )

    query = Query()
    repository = TradeRepository(StubPool(StubConnection([])), query)  # type: ignore[arg-type]

    cases = await repository.list_telemetry_cases()

    assert query.table_name == "trade_cases"
    assert query.columns == "*"
    assert len(cases) == 1
    assert cases[0] == {
        "trade_reference": "TR-1",
        "goods": "Coffee",
        "route": "KE → GH",
        "hs_code": "090111",
        "cif_value": Decimal("100"),
        "duty_exemption": True,
        "rigs_score": 80,
        "settlement": "PENDING",
        "status": "verified",
    }
    assert set(cases[0]) == {
        "trade_reference",
        "goods",
        "route",
        "hs_code",
        "cif_value",
        "duty_exemption",
        "rigs_score",
        "settlement",
        "status",
    }


@pytest.mark.asyncio
async def test_telemetry_endpoint_calculates_metrics_from_database_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = Principal(
        user_id=UUID("35dd6995-6aeb-4f02-a4f8-82531e5a793b"),
        email="trader@example.com",
        organization_id=ORGANIZATION_ID,
        role="admin",
    )
    cases = [
        {
            "trade_reference": "TR-1",
            "goods": "Coffee",
            "route": "KE → GH",
            "hs_code": "090111",
            "cif_value": Decimal("100"),
            "duty_exemption": True,
            "rigs_score": Decimal("80"),
            "settlement": "PENDING",
            "status": "verified",
        },
        {
            "trade_reference": "TR-2",
            "goods": "Cocoa",
            "route": "GH → US",
            "hs_code": "180100",
            "cif_value": Decimal("200"),
            "duty_exemption": False,
            "rigs_score": Decimal("60"),
            "settlement": "completed",
            "status": "settled",
        },
    ]

    async def list_telemetry_cases(self: TradeRepository) -> list[dict[str, object]]:
        return cases

    monkeypatch.setitem(app.dependency_overrides, get_telemetry_principal, lambda: principal)
    monkeypatch.setattr(TradeRepository, "list_telemetry_cases", list_telemetry_cases)
    monkeypatch.setattr(app.state, "database", object(), raising=False)
    monkeypatch.setattr(app.state, "supabase", object(), raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/telemetry")

    assert response.status_code == 200
    assert response.json()["trade_cases"] == 2
    assert response.json()["trade_cases_count"] == 2
    assert response.json()["preferential_origin"] == 1
    assert response.json()["active_settlements"] == 1
    assert response.json()["avg_rigs"] == pytest.approx(70.0)
    assert response.json()["cases"][0]["trade_reference"] == "TR-1"


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

    monkeypatch.setitem(app.dependency_overrides, get_telemetry_principal, lambda: principal)
    monkeypatch.setattr(TradeRepository, "list_cases", list_cases)
    monkeypatch.setattr(app.state, "database", object(), raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/trades?limit=100")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["access-control-allow-headers"] == "*"
    assert response.json()["items"][0]["external_reference"] == "TR-2026-001"
    assert response.json()["items"][0]["cif_amount"] == "1250.00"
    assert response.json()["items"][0]["preferential_margin"] == "0.15"


@pytest.mark.asyncio
async def test_list_trades_returns_empty_zero_state_as_http_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = Principal(
        user_id=UUID("35dd6995-6aeb-4f02-a4f8-82531e5a793b"),
        email="trader@example.com",
        organization_id=ORGANIZATION_ID,
        role="viewer",
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
        return []

    monkeypatch.setitem(app.dependency_overrides, get_telemetry_principal, lambda: principal)
    monkeypatch.setattr(TradeRepository, "list_cases", list_cases)
    monkeypatch.setattr(app.state, "database", object(), raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/trades?limit=100")

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


@pytest.mark.asyncio
async def test_list_trades_uses_guest_context_without_valid_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class GuestConnection:
        async def fetchrow(self, query: str) -> dict[str, UUID]:
            assert "from public.organizations" in query
            return {"id": ORGANIZATION_ID}

    class GuestPool:
        @asynccontextmanager
        async def acquire(self):
            yield GuestConnection()

    async def reject_unauthenticated_request(*args: object) -> Principal:
        raise ValueError("token verification failed")

    async def list_cases(
        self: TradeRepository,
        organization_id: UUID,
        before: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[dict[str, object]]:
        assert organization_id == ORGANIZATION_ID
        assert before is None
        assert limit == 50
        return []

    monkeypatch.setattr(main_module, "get_current_principal", reject_unauthenticated_request)
    monkeypatch.setattr(TradeRepository, "list_cases", list_cases)
    monkeypatch.setattr(app.state, "database", GuestPool(), raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/trades")
        preflight = await client.options(
            "/api/v1/trades",
            headers={
                "Origin": "https://dashboard.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,x-organization-id",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["access-control-allow-headers"] == "*"
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "*"
    assert preflight.headers["access-control-allow-headers"] == "*"


@pytest.mark.asyncio
async def test_list_trades_database_failure_returns_empty_http_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = Principal(
        user_id=UUID("35dd6995-6aeb-4f02-a4f8-82531e5a793b"),
        email=None,
        organization_id=ORGANIZATION_ID,
        role="viewer",
    )

    async def list_cases(
        self: TradeRepository,
        organization_id: UUID,
        before: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[dict[str, object]]:
        raise RuntimeError("database unavailable")

    monkeypatch.setitem(app.dependency_overrides, get_telemetry_principal, lambda: principal)
    monkeypatch.setattr(TradeRepository, "list_cases", list_cases)
    monkeypatch.setattr(app.state, "database", object(), raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/trades")

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}
