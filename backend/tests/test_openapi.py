from app.main import app


def test_openapi_describes_authentication_and_webhook_signing() -> None:
    schema = app.openapi()

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
