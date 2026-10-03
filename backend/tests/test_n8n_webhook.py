import hashlib
import hmac
import json
import time
from contextlib import asynccontextmanager
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from app.core.settings import Settings
from app.main import app


class InMemoryWebhookConnection:
    def __init__(self, events: dict[tuple[str, str], dict[str, object]]) -> None:
        self.events = events

    async def fetchval(self, query: str, *args: object) -> object | None:
        provider, event_id = str(args[0]), str(args[1])
        key = (provider, event_id)
        if query.lstrip().startswith("insert into public.webhook_events"):
            assert "payload, signature_verified, payload_sha256" in query
            payload = json.loads(str(args[2]))
            payload_hash = str(args[3])
            existing = self.events.get(key)
            if existing is None:
                self.events[key] = {
                    "payload": payload,
                    "payload_sha256": payload_hash,
                    "signature_verified": True,
                    "processed_at": None,
                }
                return event_id
            if existing["processed_at"] is None and existing["payload_sha256"] == payload_hash:
                return event_id
            return None
        if query.lstrip().startswith("select payload_sha256"):
            event = self.events.get(key)
            return event["payload_sha256"] if event else None
        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query: str, *args: object) -> None:
        assert query.lstrip().startswith("update public.webhook_events")
        provider, event_id = str(args[0]), str(args[1])
        self.events[(provider, event_id)]["processed_at"] = True


class InMemoryWebhookPool:
    def __init__(self) -> None:
        self.events: dict[tuple[str, str], dict[str, object]] = {}
        self.connection = InMemoryWebhookConnection(self.events)

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


class StubOrderAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[object, UUID, None, str]] = []

    async def process(
        self,
        trade: object,
        organization_id: UUID,
        user_id: None,
        idempotency_key: str,
    ) -> None:
        self.calls.append((trade, organization_id, user_id, idempotency_key))


def _signed_headers(body: bytes, secret: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    digest = hmac.new(
        secret.encode(),
        timestamp.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-OriginSync-Timestamp": timestamp,
        "X-OriginSync-Signature": f"sha256={digest}",
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
async def test_n8n_webhook_authenticates_persists_processes_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-webhook-secret"
    pool = InMemoryWebhookPool()
    agent = StubOrderAgent()
    monkeypatch.setattr(
        app.state,
        "settings",
        Settings(n8n_webhook_hmac_secret=SecretStr(secret)),
        raising=False,
    )
    monkeypatch.setattr(app.state, "database", pool, raising=False)
    monkeypatch.setattr(app.state, "agent", agent, raising=False)
    organization_id = UUID("afd7ea02-8e6d-468d-a551-8d0aa2855102")
    body = (
        b'{"event_id":"TEST-TR-2026-001","organization_id":'
        b'"afd7ea02-8e6d-468d-a551-8d0aa2855102","trade":{'
        b'"goods_description":"Processed Cocoa Beans","origin_country":"GH",'
        b'"destination_country":"NG","cif_amount":15000.00,"currency":"USD",'
        b'"external_reference":"TEST-TR-2026-001"}}'
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhooks/n8n",
            content=body,
            headers=_signed_headers(body, secret),
        )
        duplicate = await client.post(
            "/api/v1/webhooks/n8n",
            content=body,
            headers=_signed_headers(body, secret),
        )

    assert response.status_code == 200
    assert response.json() == {"received": True, "duplicate": False}
    assert duplicate.status_code == 200
    assert duplicate.json() == {"received": True, "duplicate": True}
    assert len(pool.events) == 1
    event = pool.events[("n8n", "TEST-TR-2026-001")]
    assert event["signature_verified"] is True
    assert event["payload"]["event_id"] == "TEST-TR-2026-001"
    assert event["payload"]["trade"]["goods_description"] == "Processed Cocoa Beans"
    assert event["payload_sha256"] == hashlib.sha256(body).hexdigest()
    assert event["processed_at"] is True
    assert len(agent.calls) == 1
    trade, called_organization_id, user_id, idempotency_key = agent.calls[0]
    assert trade.goods_description == "Processed Cocoa Beans"
    assert called_organization_id == organization_id
    assert user_id is None
    assert idempotency_key == "TEST-TR-2026-001"


@pytest.mark.asyncio
async def test_n8n_webhook_rejects_invalid_hmac_without_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = InMemoryWebhookPool()
    agent = StubOrderAgent()
    secret = "test-webhook-secret"
    monkeypatch.setattr(
        app.state,
        "settings",
        Settings(n8n_webhook_hmac_secret=SecretStr(secret)),
        raising=False,
    )
    monkeypatch.setattr(app.state, "database", pool, raising=False)
    monkeypatch.setattr(app.state, "agent", agent, raising=False)
    body = (
        b'{"event_id":"event-invalid","organization_id":'
        b'"afd7ea02-8e6d-468d-a551-8d0aa2855102","trade":{'
        b'"goods_description":"Processed Cocoa Beans","origin_country":"GH",'
        b'"destination_country":"NG","cif_amount":100.00,"currency":"USD"}}'
    )
    headers = _signed_headers(body, secret)
    headers["X-OriginSync-Signature"] = "sha256=invalid"
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhooks/n8n",
            content=body,
            headers=headers,
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_webhook_signature"
    assert pool.events == {}
    assert agent.calls == []
