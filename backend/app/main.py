import base64
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from app.agent import OrderAgent
from app.auth import Principal, get_current_principal
from app.core.errors import ServiceError, service_error_handler
from app.core.middleware import PayloadSizeLimitMiddleware, TelemetryCorsHeadersMiddleware
from app.core.settings import Settings, get_settings
from app.db import create_pool
from app.models import (
    N8nTradeTrigger,
    TradeCreate,
    TradePage,
    TradeResult,
    TradeTelemetry,
)
from app.repositories import TradeRepository
from app.services.paypal import PayPalService
from app.services.storage import SupabaseStorage
from app.services.vertex import VertexService
from app.services.webhooks import require_webhook_hmac

logger = logging.getLogger(__name__)
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "out"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    from supabase import create_client

    settings = get_settings()
    settings.validate_runtime_configuration()
    database = await create_pool(settings.database_url)
    assert settings.supabase_url is not None
    assert settings.supabase_service_role_key is not None
    supabase = create_client(
        settings.supabase_url,
        settings.supabase_service_role_key.get_secret_value(),
    )
    vertex: VertexService | None = None
    try:
        vertex = VertexService(settings, database)
        application.state.settings = settings
        application.state.database = database
        application.state.supabase = supabase
        application.state.agent = OrderAgent(
            settings=settings,
            database=database,
            vertex=vertex,
            paypal=PayPalService(settings),
            storage=SupabaseStorage(settings),
        )
        yield
    finally:
        try:
            if vertex is not None:
                await vertex.close()
        finally:
            await database.close()


app = FastAPI(
    title="OriginSync AI API",
    summary="Trade origin compliance, risk scoring, and escrow settlement",
    description=(
        "Asynchronous API for trade-document classification, fail-closed preferential-origin "
        "verification, RIGS scoring, and idempotent PayPal settlement. All protected endpoints "
        "require a Supabase access token and an organization membership."
    ),
    version="1.0.0",
    contact={"name": "OriginSync API Support"},
    license_info={"name": "MIT"},
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "health", "description": "Service liveness and readiness."},
        {"name": "trades", "description": "Organization-scoped trade compliance workflows."},
        {"name": "webhooks", "description": "HMAC-authenticated provider event receivers."},
    ],
    lifespan=lifespan,
)

app.add_middleware(
    PayloadSizeLimitMiddleware,
    max_document_bytes=get_settings().max_document_bytes,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "X-Organization-ID",
        "X-OriginSync-Signature",
        "X-OriginSync-Timestamp",
    ],
)
app.add_middleware(TelemetryCorsHeadersMiddleware)
app.add_exception_handler(ServiceError, service_error_handler)


def custom_openapi() -> dict[str, object]:
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = get_openapi(
        title="OriginSync AI API",
        version="1.0.0",
        description=(
            "Trade classification, documented preferential-origin verification, RIGS scoring, "
            "and HMAC-protected settlement workflows."
        ),
        routes=app.routes,
        tags=app.openapi_tags,
        contact={"name": "OriginSync API Support"},
        license_info={"name": "MIT"},
    )
    components = schema.setdefault("components", {})
    components.setdefault("securitySchemes", {})["SupabaseBearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Supabase Auth access token.",
    }
    for operation in schema["paths"]["/api/v1/trades"].values():
        if isinstance(operation, dict):
            operation["security"] = [{"SupabaseBearerAuth": []}]
    for path in ("/api/v1/webhooks/paypal", "/api/v1/webhooks/n8n"):
        operation = schema["paths"][path]["post"]
        operation["parameters"] = [
            {
                "name": "X-OriginSync-Timestamp",
                "in": "header",
                "required": True,
                "description": "Unix timestamp included in the HMAC-SHA256 signing input.",
                "schema": {"type": "string"},
            },
            {
                "name": "X-OriginSync-Signature",
                "in": "header",
                "required": True,
                "description": (
                    "HMAC-SHA256 of `<timestamp>.<raw request body>`, prefixed with `sha256=`."
                ),
                "schema": {"type": "string"},
            },
        ]
    schema["paths"]["/api/v1/webhooks/paypal"]["post"]["requestBody"] = {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string"},
                        "event_type": {"type": "string"},
                        "resource": {"type": "object"},
                    },
                    "additionalProperties": True,
                }
            }
        },
    }
    schema["paths"]["/api/v1/webhooks/n8n"]["post"]["requestBody"] = {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["event_id", "organization_id", "trade"],
                    "properties": {
                        "event_id": {"type": "string"},
                        "organization_id": {"type": "string", "format": "uuid"},
                        "trade": {"$ref": "#/components/schemas/TradeCreate"},
                    },
                    "additionalProperties": False,
                }
            }
        },
    }
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


@app.get("/", include_in_schema=False, response_model=None)
async def root() -> FileResponse | RedirectResponse:
    index_file = frontend_dist / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return RedirectResponse(url="/docs")


@app.get("/config.js", include_in_schema=False)
async def frontend_config(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    config = json.dumps(
        {
            "supabaseUrl": settings.supabase_url,
            "supabaseAnonKey": (
                settings.supabase_anon_key.get_secret_value()
                if settings.supabase_anon_key is not None
                else None
            ),
        }
    )
    return Response(
        (
            f"window.__ORIGINSYNC_CONFIG__ = {config};"
            'window.dispatchEvent(new Event("originsync-config-ready"));'
        ),
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, error: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "The request does not match the API schema.",
                "details": [
                    {
                        "location": item["loc"],
                        "message": item["msg"],
                        "type": item["type"],
                    }
                    for item in error.errors()
                ],
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, error: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        headers=error.headers,
        content={
            "error": {
                "code": "http_error",
                "message": str(error.detail),
                "details": {},
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, error: Exception) -> JSONResponse:
    logger.exception("Unhandled API error on %s", request.url.path, exc_info=error)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "The request could not be completed.",
                "details": {},
            }
        },
    )


@app.get("/health", tags=["health"], operation_id="healthCheck")
async def health(request: Request) -> dict[str, str]:
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise ServiceError(
            "service_not_ready", "Application dependencies are not initialized.", 503
        )
    async with database.acquire() as connection:
        await connection.fetchval("select 1")
    return {"status": "ok"}


def _encode_cursor(created_at: datetime, case_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{case_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_at, case_id = base64.urlsafe_b64decode(padded).decode().split("|", maxsplit=1)
        parsed_time = datetime.fromisoformat(created_at)
        if parsed_time.tzinfo is None:
            raise ValueError("cursor timestamp must include timezone")
        return parsed_time, UUID(case_id)
    except (ValueError, UnicodeDecodeError) as error:
        raise ServiceError("invalid_cursor", "Pagination cursor is invalid.", 422) from error


async def get_telemetry_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    organization_id: UUID | None = Header(default=None, alias="X-Organization-ID"),
) -> Principal:
    try:
        return await get_current_principal(request, authorization, organization_id)
    except Exception:
        logger.exception("Telemetry identity verification failed; using guest context")

    guest_organization_id = UUID(int=0)
    try:
        async with request.app.state.database.acquire() as connection:
            organization = await connection.fetchrow(
                """
                select id from public.organizations
                order by created_at, id
                limit 1
                """
            )
        if organization is not None:
            guest_organization_id = organization["id"]
    except Exception:
        logger.exception("Could not resolve the default telemetry organization")

    return Principal(
        user_id=UUID(int=0),
        email=None,
        organization_id=guest_organization_id,
        role="viewer",
    )


@app.post(
    "/api/v1/trades",
    response_model=TradeResult,
    status_code=status.HTTP_201_CREATED,
    tags=["trades"],
    operation_id="createTradeCase",
)
async def create_trade(
    trade: TradeCreate,
    request: Request,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
    principal: Principal = Depends(get_current_principal),
) -> TradeResult:
    if principal.role == "viewer":
        raise ServiceError(
            "organization_role_denied", "Viewer role cannot submit trade cases.", 403
        )
    if trade.settlement_amount is not None and principal.role not in {"owner", "admin"}:
        raise ServiceError(
            "settlement_role_denied",
            "Only organization owners and admins can initiate an eligible settlement.",
            403,
        )
    agent: OrderAgent = request.app.state.agent
    return await agent.process(
        trade,
        principal.organization_id,
        principal.user_id,
        idempotency_key,
    )


@app.get(
    "/api/v1/trades",
    response_model=TradePage,
    tags=["trades"],
    operation_id="listTradeCases",
)
async def list_trades(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=256),
    principal: Principal = Depends(get_telemetry_principal),
) -> TradePage:
    try:
        repository = TradeRepository(request.app.state.database)
        rows = await repository.list_cases(
            principal.organization_id,
            _decode_cursor(cursor),
            limit,
        )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = [TradeResult.model_validate(dict(row)) for row in page_rows]
        next_cursor = (
            _encode_cursor(page_rows[-1]["created_at"], page_rows[-1]["id"])
            if has_more and page_rows
            else None
        )
        return TradePage(items=items, next_cursor=next_cursor)
    except Exception:
        logger.exception(
            "Trade telemetry request failed for organization %s",
            principal.organization_id,
        )
        return TradePage(items=[], next_cursor=None)


@app.get(
    "/api/v1/telemetry",
    response_model=TradeTelemetry,
    tags=["trades"],
    operation_id="getTradeTelemetry",
)
async def get_trade_telemetry(
    request: Request,
    principal: Principal = Depends(get_telemetry_principal),
) -> TradeTelemetry:
    repository = TradeRepository(request.app.state.database, request.app.state.supabase)
    cases = await repository.list_telemetry_cases()
    rigs_scores = [
        float(case["rigs_score"])
        for case in cases
        if isinstance(case.get("rigs_score"), (int, float, Decimal))
        and not isinstance(case.get("rigs_score"), bool)
    ]
    return TradeTelemetry(
        cases=cases,
        trade_cases=len(cases),
        trade_cases_count=len(cases),
        preferential_origin=sum(score >= 70.0 for score in rigs_scores),
        active_settlements=sum(
            str(case.get("settlement", "")).upper() in {"PENDING", "PROCESSING"}
            for case in cases
        ),
        avg_rigs=sum(rigs_scores) / len(rigs_scores) if rigs_scores else 0.0,
    )


async def _webhook_payload(request: Request, provider: str) -> tuple[dict[str, object], str]:
    body = await request.body()
    if len(body) > 1_000_000:
        raise ServiceError(
            "webhook_payload_too_large", "Webhook payload exceeds the size limit.", 413
        )
    settings: Settings = request.app.state.settings
    secret = (
        settings.paypal_webhook_hmac_secret.get_secret_value()
        if provider == "paypal" and settings.paypal_webhook_hmac_secret
        else settings.n8n_webhook_hmac_secret.get_secret_value()
        if provider == "n8n" and settings.n8n_webhook_hmac_secret
        else None
    )
    require_webhook_hmac(
        body=body,
        signature=request.headers.get("X-OriginSync-Signature"),
        timestamp=request.headers.get("X-OriginSync-Timestamp"),
        secret=secret,
        settings=settings,
    )
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ServiceError(
            "invalid_webhook_payload", "Webhook body must be valid JSON.", 400
        ) from error
    if not isinstance(payload, dict):
        raise ServiceError("invalid_webhook_payload", "Webhook body must be a JSON object.", 400)
    return payload, hashlib.sha256(body).hexdigest()


@app.post(
    "/api/v1/webhooks/paypal",
    tags=["webhooks"],
    operation_id="receivePayPalWebhook",
)
async def paypal_webhook(request: Request) -> dict[str, bool]:
    payload, payload_hash = await _webhook_payload(request, "paypal")
    event_id = payload.get("id")
    if not isinstance(event_id, str) or not event_id or len(event_id) > 200:
        raise ServiceError("invalid_webhook_event_id", "PayPal event id is required.", 422)
    repository = TradeRepository(request.app.state.database)
    try:
        created = await repository.record_webhook("paypal", event_id, payload, payload_hash)
    except ValueError as error:
        raise ServiceError("webhook_event_conflict", str(error), 409) from error
    if not created:
        return {"received": True, "duplicate": True}

    event_type = payload.get("event_type")
    resource = payload.get("resource")
    batch_header = resource.get("batch_header") if isinstance(resource, dict) else None
    batch_id = batch_header.get("payout_batch_id") if isinstance(batch_header, dict) else None
    sender_batch_id = (
        batch_header.get("sender_batch_id") if isinstance(batch_header, dict) else None
    )
    outcome_by_event = {
        "PAYMENT.PAYOUTSBATCH.SUCCESS": "processing",
        "PAYMENT.PAYOUTSBATCH.DENIED": "failed",
        "PAYMENT.PAYOUTS-ITEM.SUCCEEDED": "completed",
        "PAYMENT.PAYOUTS-ITEM.FAILED": "failed",
        "PAYMENT.PAYOUTS-ITEM.BLOCKED": "failed",
        "PAYMENT.PAYOUTS-ITEM.DENIED": "failed",
    }
    payout_item = resource.get("payout_item") if isinstance(resource, dict) else None
    sender_item_id = payout_item.get("sender_item_id") if isinstance(payout_item, dict) else None
    trade_id = None
    if isinstance(sender_item_id, str):
        try:
            trade_id = UUID(sender_item_id)
        except ValueError:
            trade_id = None
    if (
        isinstance(event_type, str)
        and event_type in outcome_by_event
        and (isinstance(batch_id, str) or isinstance(sender_batch_id, str) or trade_id is not None)
    ):
        await repository.apply_paypal_payout_event(
            event_id,
            batch_id if isinstance(batch_id, str) else None,
            sender_batch_id if isinstance(sender_batch_id, str) else None,
            trade_id,
            outcome_by_event[event_type],
        )
    await repository.finish_webhook("paypal", event_id)
    return {"received": True, "duplicate": False}


@app.post(
    "/api/v1/webhooks/n8n",
    tags=["webhooks"],
    operation_id="receiveN8nWebhook",
)
async def n8n_webhook(request: Request) -> dict[str, bool]:
    payload, payload_hash = await _webhook_payload(request, "n8n")
    try:
        trigger = N8nTradeTrigger.model_validate(payload)
    except ValidationError as error:
        raise ServiceError(
            "invalid_webhook_payload",
            "n8n payload does not match the trade trigger schema.",
            422,
        ) from error
    repository = TradeRepository(request.app.state.database)
    try:
        created = await repository.record_webhook("n8n", trigger.event_id, payload, payload_hash)
    except ValueError as error:
        raise ServiceError("webhook_event_conflict", str(error), 409) from error
    if not created:
        return {"received": True, "duplicate": True}
    agent: OrderAgent = request.app.state.agent
    await agent.process(trigger.trade, trigger.organization_id, None, trigger.event_id)
    await repository.finish_webhook("n8n", trigger.event_id)
    return {"received": True, "duplicate": False}


if frontend_dist.is_dir():
    next_static_dir = frontend_dist / "_next" / "static"
    if next_static_dir.is_dir():
        app.mount(
            "/_next/static",
            StaticFiles(directory=next_static_dir),
            name="frontend-static",
        )


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str) -> FileResponse:
    if (
        full_path == "api"
        or full_path.startswith("api/")
        or full_path in {"docs", "redoc", "openapi.json"}
        or full_path.startswith(("docs/", "redoc/"))
    ):
        raise StarletteHTTPException(status_code=404, detail="Not Found")

    frontend_root = frontend_dist.resolve()
    target_file = (frontend_root / full_path).resolve()
    try:
        target_file.relative_to(frontend_root)
    except ValueError:
        raise StarletteHTTPException(status_code=404, detail="Not Found") from None
    if target_file.is_file():
        return FileResponse(target_file)

    index_file = frontend_root / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    raise StarletteHTTPException(status_code=404, detail="Frontend build not found.")
