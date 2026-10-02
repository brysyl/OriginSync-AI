from dataclasses import dataclass
from uuid import UUID

import httpx
from asyncpg import Pool
from fastapi import Depends, Header, Request

from app.core.errors import ServiceError


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    email: str | None
    organization_id: UUID
    role: str


async def get_current_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    organization_id: UUID | None = Header(default=None, alias="X-Organization-ID"),
) -> Principal:
    settings = request.app.state.settings
    pool: Pool = request.app.state.database
    if not authorization or not authorization.startswith("Bearer "):
        raise ServiceError("authentication_required", "A Supabase access token is required.", 401)
    if organization_id is None:
        raise ServiceError("organization_required", "X-Organization-ID is required.", 400)

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise ServiceError("authentication_required", "A Supabase access token is required.", 401)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_anon_key.get_secret_value(),
                    "Authorization": f"Bearer {token}",
                },
            )
    except httpx.HTTPError as error:
        raise ServiceError(
            "identity_provider_unavailable", "Could not verify access token.", 503
        ) from error
    if response.status_code != 200:
        raise ServiceError("invalid_access_token", "The access token is invalid or expired.", 401)
    try:
        user_id = UUID(response.json()["id"])
        email = response.json().get("email")
    except (KeyError, TypeError, ValueError) as error:
        raise ServiceError(
            "invalid_identity_response", "Supabase returned an invalid identity.", 502
        ) from error

    async with pool.acquire() as connection:
        role = await connection.fetchval(
            """
            select role from public.organization_memberships
            where user_id = $1 and organization_id = $2
            """,
            user_id,
            organization_id,
        )
    if role is None:
        raise ServiceError(
            "organization_access_denied", "User is not a member of this organization.", 403
        )
    return Principal(user_id=user_id, email=email, organization_id=organization_id, role=role)


CurrentPrincipal = Depends(get_current_principal)
