from uuid import UUID

import httpx

from app.core.errors import ServiceError
from app.core.settings import Settings


class SupabaseStorage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def upload_document(
        self,
        organization_id: UUID,
        trade_id: UUID,
        media_type: str,
        data: bytes,
        sha256: str,
    ) -> str:
        if self.settings.supabase_service_role_key is None or self.settings.supabase_url is None:
            raise ServiceError(
                "document_storage_not_configured",
                "Private document storage is not configured.",
                503,
            )
        path = f"{organization_id}/{trade_id}/{sha256}"
        key = self.settings.supabase_service_role_key.get_secret_value()
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{self.settings.supabase_url.rstrip('/')}/storage/v1/object/trade-documents/{path}",
                    content=data,
                    headers={
                        "apikey": key,
                        "Authorization": f"Bearer {key}",
                        "Content-Type": media_type,
                        "x-upsert": "false",
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise ServiceError(
                "document_storage_failed", "Could not store the trade document securely.", 502
            ) from error
        return path
