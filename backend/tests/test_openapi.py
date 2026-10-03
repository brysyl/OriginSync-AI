import httpx
import pytest
from pydantic import SecretStr

from app import main
from app.core.settings import Settings


@pytest.mark.asyncio
async def test_root_serves_frontend_when_build_exists_and_redirects_without_it(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "frontend_dist", tmp_path / "missing")
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        fallback = await client.get("/", follow_redirects=False)

        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        (frontend_dir / "index.html").write_text("<main>OriginSync</main>")
        monkeypatch.setattr(main, "frontend_dist", frontend_dir)
        root = await client.get("/")
        client_route = await client.get("/client/route")

    assert fallback.status_code == 307
    assert fallback.headers["location"] == "/docs"
    assert root.status_code == 200
    assert root.text == "<main>OriginSync</main>"
    assert client_route.status_code == 200
    assert client_route.text == root.text
    assert "/" not in main.app.openapi()["paths"]


@pytest.mark.asyncio
async def test_frontend_fallback_does_not_capture_api_or_docs(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text("<main>OriginSync</main>")
    monkeypatch.setattr(main, "frontend_dist", frontend_dir)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        api_route = await client.get("/api/v1/not-a-route")
        docs = await client.get("/docs")
        redoc = await client.get("/redoc")
        openapi = await client.get("/openapi.json")

    assert api_route.status_code == 404
    assert api_route.json()["error"]["code"] == "http_error"
    assert docs.status_code == 200
    assert redoc.status_code == 200
    assert openapi.status_code == 200


@pytest.mark.asyncio
async def test_frontend_config_exposes_only_public_supabase_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main.app.state,
        "settings",
        Settings(
            supabase_url="https://project.supabase.co",
            supabase_anon_key=SecretStr("public-anon-key"),
            supabase_service_role_key=SecretStr("private-service-role-key"),
        ),
        raising=False,
    )
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/config.js")

    assert response.status_code == 200
    assert "https://project.supabase.co" in response.text
    assert "public-anon-key" in response.text
    assert "private-service-role-key" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_openapi_describes_authentication_and_webhook_signing() -> None:
    schema = main.app.openapi()

    assert schema["openapi"] == "3.1.0"
    assert schema["components"]["securitySchemes"]["SupabaseBearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Supabase Auth access token.",
    }
    assert schema["paths"]["/api/v1/trades"]["post"]["security"] == [{"SupabaseBearerAuth": []}]
    paypal = schema["paths"]["/api/v1/webhooks/paypal"]["post"]
    assert {parameter["name"] for parameter in paypal["parameters"]} == {
        "X-OriginSync-Timestamp",
        "X-OriginSync-Signature",
    }
    assert paypal["requestBody"]["required"] is True
    assert schema["paths"]["/api/v1/webhooks/n8n"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["required"] == ["event_id", "organization_id", "trade"]
