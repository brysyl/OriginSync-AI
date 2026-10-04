import base64
from types import SimpleNamespace

import pytest

import app.services.vertex as vertex_module
from app.core.settings import Settings
from app.services.vertex import VertexService


class FakeConnection:
    def __init__(self) -> None:
        self.executed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, *args, **kwargs):
        self.executed = True

    async def fetchrow(self, *args, **kwargs):
        return None


class FakeDatabase:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    def acquire(self):
        return self.connection


@pytest.mark.asyncio
async def test_classify_builds_embedding_vector_for_documented_requests(monkeypatch) -> None:
    monkeypatch.setattr(vertex_module.genai, "Client", lambda **kwargs: object())
    settings = Settings(environment="test")
    database = FakeDatabase()
    service = VertexService(settings, database)

    async def fake_generate_content(*args, **kwargs):
        return SimpleNamespace(
            text=(
                '{"hs_code":"610910","confidence":0.9,"rationale":"matched garment HS code",'
                '"excluded_materials":[],"invoice_goods_match":0.92,'
                '"origin_evidence":{"evidence_confidence":0.95,"wholly_obtained":true,'
                '"value_added_pct":40.0,"non_originating_tariff_heading":null}}'
            )
        )

    service.client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))
    )

    async def fake_embedding(_text):
        return [0.5] * 768

    monkeypatch.setattr(service, "_embedding", fake_embedding)

    result = await service.classify(
        description="Cotton t-shirt",
        invoice_goods_description="Cotton t-shirt",
        document_media_type="application/pdf",
        document_data_base64=base64.b64encode(b"sample-document").decode(),
        max_document_bytes=1_048_576,
    )

    assert result.hs_code == "610910"
    assert result.confidence == 0.9
    assert result.evidence_confidence == 0.95
    assert database.connection.executed is True
