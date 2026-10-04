import base64
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from google import genai
from google.genai import types
from google.oauth2 import service_account

from app.core.errors import ServiceError
from app.core.settings import Settings


@dataclass(frozen=True)
class Classification:
    hs_code: str
    confidence: float
    rationale: str
    excluded_materials: list[dict[str, object]]
    invoice_goods_match: float | None
    evidence_confidence: float
    wholly_obtained: bool | None
    value_added_pct: float | None
    non_originating_tariff_heading: str | None
    cache_hit: bool = False


class VertexService:
    def __init__(self, settings: Settings, database: Any) -> None:
        options: dict[str, object] = {
            "vertexai": True,
            "project": settings.vertex_project_id,
            "location": settings.vertex_location,
        }
        if settings.vertex_service_account_json is not None:
            try:
                info = json.loads(settings.vertex_service_account_json.get_secret_value())
                credentials = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            except (json.JSONDecodeError, ValueError, KeyError) as error:
                raise ValueError("VERTEX_SERVICE_ACCOUNT_JSON is invalid.") from error
            options["credentials"] = credentials
        self.client = genai.Client(**options)
        self.settings = settings
        self.database = database

    async def close(self) -> None:
        await self.client.aio.aclose()

    async def _embedding(self, text: str) -> list[float]:
        try:
            response = await self.client.aio.models.embed_content(
                model=self.settings.vertex_embedding_model,
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=768),
            )
        except Exception as error:
            raise ServiceError(
                "embedding_unavailable", "Vertex AI embedding generation failed.", 502
            ) from error
        if not response.embeddings or not response.embeddings[0].values:
            raise ServiceError("embedding_failed", "Vertex AI returned no embedding.", 502)
        values = list(response.embeddings[0].values)
        if len(values) != 768 or any(not math.isfinite(value) for value in values):
            raise ServiceError(
                "invalid_embedding", "Vertex AI returned an invalid embedding vector.", 502
            )
        return values

    @staticmethod
    def _vector_literal(values: list[float]) -> str:
        return "[" + ",".join(f"{value:.8f}" for value in values) + "]"

    async def classify(
        self,
        description: str,
        invoice_goods_description: str | None,
        document_media_type: str | None,
        document_data_base64: str | None,
        max_document_bytes: int,
    ) -> Classification:
        binary: bytes | None = None
        if document_data_base64 is not None and document_media_type is not None:
            try:
                binary = base64.b64decode(document_data_base64, validate=True)
            except ValueError as error:
                raise ServiceError(
                    "invalid_document_encoding", "Document must be valid base64.", 422
                ) from error
            if len(binary) > max_document_bytes:
                raise ServiceError(
                    "document_too_large", "Document exceeds the configured size limit.", 413
                )
        query_text = description.strip()
        query_hash = hashlib.sha256(query_text.casefold().encode()).hexdigest()
        vector: str | None = None
        if binary is None and invoice_goods_description is None:
            async with self.database.acquire() as connection:
                cached_exact = await connection.fetchrow(
                    """
                    select hs_code, confidence, rationale
                    from public.classification_cache
                    where query_hash = $1 and expires_at > now()
                      and source_version = $2 and embedding_model = $3
                    """,
                    query_hash,
                    self.settings.vertex_model,
                    self.settings.vertex_embedding_model,
                )
            if cached_exact:
                return Classification(
                    hs_code=cached_exact["hs_code"],
                    confidence=float(cached_exact["confidence"]),
                    rationale=cached_exact["rationale"],
                    excluded_materials=[],
                    invoice_goods_match=None,
                    evidence_confidence=0,
                    wholly_obtained=None,
                    value_added_pct=None,
                    non_originating_tariff_heading=None,
                    cache_hit=True,
                )

            embedding = await self._embedding(query_text)
            vector = self._vector_literal(embedding)
            async with self.database.acquire() as connection:
                cached = await connection.fetchrow(
                    """
                    select hs_code, confidence, rationale
                    from public.match_classification_cache($1::extensions.vector, $2, 1, $3, $4)
                    """,
                    vector,
                    self.settings.classification_cache_similarity,
                    self.settings.vertex_model,
                    self.settings.vertex_embedding_model,
                )
            if cached:
                return Classification(
                    hs_code=cached["hs_code"],
                    confidence=float(cached["confidence"]),
                    rationale=cached["rationale"],
                    excluded_materials=[],
                    invoice_goods_match=None,
                    evidence_confidence=0,
                    wholly_obtained=None,
                    value_added_pct=None,
                    non_originating_tariff_heading=None,
                    cache_hit=True,
                )

        contents: list[Any] = [
            (
                "Classify this item for customs using the Harmonized System. Return only JSON with "
                "keys hs_code (six digits), confidence (0..1), rationale, excluded_materials "
                "(array of objects with code and description), invoice_goods_match (0..1 or null), "
                "and origin_evidence with evidence_confidence (0..1), "
                "wholly_obtained (boolean or null), value_added_pct (number or null), "
                "and non_originating_tariff_heading (string or null). "
                "Use the supplied invoice/document only as evidence; do not infer country-specific "
                "preferential origin. Only report origin_evidence that is directly present in the "
                "provided document; otherwise use null and evidence_confidence 0. "
                "If classification "
                "is ambiguous, return confidence below 0.8. "
                f"Goods description: {query_text}\n"
                f"Invoice goods description: {invoice_goods_description or 'not provided'}"
            )
        ]
        if binary is not None and document_media_type is not None:
            contents.append(types.Part.from_bytes(data=binary, mime_type=document_media_type))

        try:
            response = await self.client.aio.models.generate_content(
                model=self.settings.vertex_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
        except Exception as error:
            raise ServiceError(
                "classification_unavailable", "Vertex AI classification failed.", 502
            ) from error
        try:
            result = json.loads(response.text or "")
            hs_code = str(result["hs_code"])
            confidence = float(result["confidence"])
            rationale = str(result["rationale"])
            excluded_materials = result["excluded_materials"]
            invoice_value = result.get("invoice_goods_match")
            invoice_goods_match = float(invoice_value) if invoice_value is not None else None
            if (
                len(hs_code) < 6
                or len(hs_code) > 10
                or not hs_code.isdigit()
                or not 0 <= confidence <= 1
                or (invoice_goods_match is not None and not 0 <= invoice_goods_match <= 1)
                or not isinstance(excluded_materials, list)
                or any(not isinstance(item, dict) for item in excluded_materials)
            ):
                raise ValueError("model response fields are out of range")
            evidence = result["origin_evidence"]
            evidence_confidence = float(evidence["evidence_confidence"])
            wholly_obtained = evidence.get("wholly_obtained")
            value_added_pct = evidence.get("value_added_pct")
            value_added_pct = float(value_added_pct) if value_added_pct is not None else None
            non_originating_tariff_heading = evidence.get("non_originating_tariff_heading")
            if (
                not 0 <= evidence_confidence <= 1
                or (wholly_obtained is not None and not isinstance(wholly_obtained, bool))
                or (value_added_pct is not None and not 0 <= value_added_pct <= 100)
                or (
                    non_originating_tariff_heading is not None
                    and (
                        not isinstance(non_originating_tariff_heading, str)
                        or not non_originating_tariff_heading.isdigit()
                        or not 2 <= len(non_originating_tariff_heading) <= 6
                    )
                )
            ):
                raise ValueError("model origin evidence fields are out of range")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ServiceError(
                "invalid_classification_response",
                "Vertex AI returned invalid classification data.",
                502,
            ) from error

        if vector is None:
            vector = self._vector_literal(await self._embedding(query_text))

        async with self.database.acquire() as connection:
            await connection.execute(
                """
                insert into public.classification_cache
                    (query_hash, embedding, hs_code, confidence, rationale, source_version,
                     embedding_model, expires_at)
                values ($1, $2::extensions.vector, $3, $4, $5, $6, $7, now() + interval '30 days')
                on conflict (query_hash) do update
                set embedding = excluded.embedding, hs_code = excluded.hs_code,
                    confidence = excluded.confidence, rationale = excluded.rationale,
                    source_version = excluded.source_version,
                    embedding_model = excluded.embedding_model, expires_at = excluded.expires_at
                """,
                query_hash,
                vector,
                hs_code,
                confidence,
                rationale,
                self.settings.vertex_model,
                self.settings.vertex_embedding_model,
            )
        return Classification(
            hs_code=hs_code,
            confidence=confidence,
            rationale=rationale,
            excluded_materials=excluded_materials,
            invoice_goods_match=invoice_goods_match,
            evidence_confidence=evidence_confidence,
            wholly_obtained=wholly_obtained,
            value_added_pct=value_added_pct,
            non_originating_tariff_heading=non_originating_tariff_heading,
        )

    async def similar_tariff_rules(
        self,
        *,
        description: str,
        organization_id: UUID,
        origin_country: str,
        destination_country: str,
    ) -> list[dict[str, object]]:
        embedding = await self._embedding(
            f"Goods: {description}; origin: {origin_country}; destination: {destination_country}"
        )
        async with self.database.acquire() as connection:
            rows = await connection.fetch(
                """
                select id, agreement, hs_code_prefix, rule_type, similarity
                from public.match_tariff_rules(
                    $1::extensions.vector, $2, $3, $4, 5, 0.75, $5
                )
                """,
                self._vector_literal(embedding),
                organization_id,
                origin_country,
                destination_country,
                self.settings.vertex_embedding_model,
            )
        return [dict(row) for row in rows]
