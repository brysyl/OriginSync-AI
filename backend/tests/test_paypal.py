from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.settings import Settings
from app.services.paypal import PayPalService


@pytest.mark.asyncio
async def test_transport_retry_reuses_paypal_idempotency_key(monkeypatch) -> None:
    trade_id = uuid4()
    payout_request_ids: list[str] = []
    payout_attempts = 0
    real_async_client = httpx.AsyncClient

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal payout_attempts
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "access-token"})
        payout_attempts += 1
        payout_request_ids.append(request.headers["paypal-request-id"])
        if payout_attempts == 1:
            raise httpx.ConnectError("connection reset", request=request)
        return httpx.Response(
            201,
            json={"batch_header": {"payout_batch_id": "batch-1"}},
        )

    transport = httpx.MockTransport(respond)

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        return real_async_client(
            base_url=str(kwargs["base_url"]),
            timeout=kwargs["timeout"],
            transport=transport,
        )

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    service = PayPalService(
        Settings(
            paypal_client_id=SecretStr("client-id"),
            paypal_client_secret=SecretStr("client-secret"),
            paypal_environment="sandbox",
        )
    )

    batch_id = await service.create_payout(
        trade_id=trade_id,
        email="payee@example.com",
        amount=Decimal("50.00"),
        currency="USD",
    )

    assert batch_id == "batch-1"
    assert payout_request_ids == [f"originsync-{trade_id}"] * 2
