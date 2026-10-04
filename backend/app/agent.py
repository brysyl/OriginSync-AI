import base64
import hashlib
import json
import logging
from uuid import UUID, uuid4

from asyncpg import Pool

from app.core.errors import ServiceError
from app.core.settings import Settings
from app.models import TradeCreate, TradeResult, TradeStatus
from app.repositories import TradeRepository
from app.services.compliance import decide_origin
from app.services.paypal import PayPalService
from app.services.rigs import calculate_rigs
from app.services.storage import SupabaseStorage
from app.services.vertex import VertexService

logger = logging.getLogger(__name__)


class OrderAgent:
    def __init__(
        self,
        settings: Settings,
        database: Pool,
        vertex: VertexService,
        paypal: PayPalService,
        storage: SupabaseStorage,
    ) -> None:
        self.settings = settings
        self.repository = TradeRepository(database)
        self.vertex = vertex
        self.paypal = paypal
        self.storage = storage

    async def process(
        self,
        trade: TradeCreate,
        organization_id: UUID,
        user_id: UUID | None,
        idempotency_key: str,
    ) -> TradeResult:
        request_hash = hashlib.sha256(
            json.dumps(
                trade.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        trade_id = uuid4()
        try:
            created, existing = await self.repository.create_case(
                trade_id,
                organization_id,
                user_id,
                trade,
                idempotency_key,
                request_hash,
            )
        except ValueError as error:
            raise ServiceError("duplicate_trade_reference", str(error), 409) from error
        if not created:
            if existing is None:
                raise ServiceError(
                    "idempotency_conflict",
                    "Idempotency-Key was already used with a different request.",
                    409,
                )
            return TradeResult.model_validate(dict(existing))

        try:
            document = trade.document
            if document is not None:
                try:
                    document_bytes = base64.b64decode(document.data_base64, validate=True)
                except ValueError as error:
                    raise ServiceError(
                        "invalid_document_encoding",
                        "Document must be valid base64.",
                        422,
                    ) from error
                if len(document_bytes) > self.settings.max_document_bytes:
                    raise ServiceError(
                        "document_too_large",
                        "Document exceeds the configured size limit.",
                        413,
                    )
                digest = hashlib.sha256(document_bytes).hexdigest()
                storage_path = await self.storage.upload_document(
                    organization_id,
                    trade_id,
                    document.media_type,
                    document_bytes,
                    digest,
                )
                await self.repository.save_document(
                    organization_id,
                    trade_id,
                    document.media_type,
                    storage_path,
                    digest,
                )
            classification = await self.vertex.classify(
                description=trade.goods_description,
                invoice_goods_description=trade.invoice_goods_description,
                document_media_type=document.media_type if document else None,
                document_data_base64=document.data_base64 if document else None,
                max_document_bytes=self.settings.max_document_bytes,
            )
            await self.repository.record_stage(
                organization_id,
                trade_id,
                "observe",
                "classification_completed",
                {
                    "hs_code": classification.hs_code,
                    "confidence": classification.confidence,
                    "cache_hit": classification.cache_hit,
                    "invoice_goods_match": classification.invoice_goods_match,
                },
            )
            rules = await self.repository.applicable_rules(
                organization_id,
                trade.origin_country,
                trade.destination_country,
                classification.hs_code,
            )
            if not rules:
                suggestions = await self.vertex.similar_tariff_rules(
                    description=trade.goods_description,
                    organization_id=organization_id,
                    origin_country=trade.origin_country,
                    destination_country=trade.destination_country,
                )
                if suggestions:
                    await self.repository.record_stage(
                        organization_id,
                        trade_id,
                        "observe",
                        "semantic_tariff_rule_suggestions",
                        {"candidates": suggestions},
                    )
            origin = decide_origin(
                trade,
                classification.hs_code,
                rules,
                classification.excluded_materials,
                has_document=document is not None,
                evidence_confidence=classification.evidence_confidence,
                documented_wholly_obtained=classification.wholly_obtained,
                documented_value_added_pct=classification.value_added_pct,
                documented_tariff_heading=classification.non_originating_tariff_heading,
            )
            growth_score, stakeholder_score = await self.repository.historical_scores(
                organization_id,
                str(trade.beneficiary_email) if trade.beneficiary_email else None,
                trade.currency,
                trade.origin_country,
                trade.destination_country,
            )
            intent_score = (
                classification.invoice_goods_match
                if trade.invoice_goods_description is not None or document is not None
                else None
            )
            rigs = calculate_rigs(
                risk_control_score=classification.confidence,
                intent_alignment_score=intent_score,
                growth_potential_score=growth_score,
                stakeholder_trust_score=stakeholder_score,
                origin_verified=origin.verified,
                classification_confidence=classification.confidence,
            )
            threshold_met = (
                rigs.score is not None and rigs.score >= self.settings.settlement_threshold
            )
            beneficiary_verified = (
                await self.repository.is_verified_beneficiary(
                    organization_id,
                    str(trade.beneficiary_email),
                )
                if trade.beneficiary_email is not None
                else False
            )
            can_settle = (
                origin.verified
                and threshold_met
                and trade.beneficiary_email is not None
                and trade.settlement_amount is not None
                and beneficiary_verified
            )
            beneficiary_review_required = (
                trade.settlement_amount is not None and not beneficiary_verified
            )
            status = (
                TradeStatus.SETTLEMENT_PENDING.value
                if can_settle
                else TradeStatus.REVIEW_REQUIRED.value
                if beneficiary_review_required
                else TradeStatus.VERIFIED.value
                if origin.verified and threshold_met
                else TradeStatus.REVIEW_REQUIRED.value
            )
            settlement_status = "processing" if can_settle else "not_eligible"
            await self.repository.record_decision(
                organization_id=organization_id,
                trade_id=trade_id,
                hs_code=classification.hs_code,
                confidence=classification.confidence,
                rationale=classification.rationale,
                origin_decision=origin.model_dump(mode="json"),
                rigs_score=rigs.score,
                rigs_components=rigs.components.model_dump(mode="json"),
                rule_id=origin.rule_id,
                status=status,
                settlement_status=settlement_status,
            )
            if (
                origin.verified
                and threshold_met
                and trade.settlement_amount is not None
                and not beneficiary_verified
            ):
                await self.repository.record_stage(
                    organization_id,
                    trade_id,
                    "decide",
                    "settlement_blocked_unverified_beneficiary",
                    {"reason": "beneficiary must be verified by an organization administrator"},
                )
            if can_settle:
                await self.repository.set_payout_started(
                    organization_id,
                    trade_id,
                    f"originsync-{trade_id}",
                )
                await self.repository.record_stage(
                    organization_id,
                    trade_id,
                    "execute",
                    "payout_requested",
                    {"threshold": self.settings.settlement_threshold},
                )
                try:
                    batch_id = await self.paypal.create_payout(
                        trade_id=trade_id,
                        email=str(trade.beneficiary_email),
                        amount=trade.settlement_amount,
                        currency=trade.settlement_currency or trade.currency,
                    )
                except ServiceError as error:
                    await self.repository.record_stage(
                        organization_id,
                        trade_id,
                        "execute",
                        "payout_outcome_unknown"
                        if error.code == "paypal_payout_outcome_unknown"
                        else "payout_failed",
                        {"error_code": error.code},
                    )
                    if error.code != "paypal_payout_outcome_unknown":
                        await self.repository.set_payout(
                            organization_id,
                            trade_id,
                            "",
                            outcome="failed",
                        )
                    raise
                await self.repository.set_payout(
                    organization_id,
                    trade_id,
                    batch_id,
                    outcome="processing",
                )
                settlement_status = "processing"
            await self.repository.record_stage(
                organization_id,
                trade_id,
                "record",
                "order_completed",
                {"status": status, "settlement_status": settlement_status},
            )
        except ServiceError as error:
            await self.repository.mark_failed(organization_id, trade_id, error.code)
            raise
        except Exception as error:
            logger.exception("Unexpected ODER processing failure for trade %s", trade_id)
            await self.repository.mark_failed(
                organization_id, trade_id, "internal_processing_error"
            )
            raise ServiceError(
                "trade_processing_failed",
                "Trade processing failed unexpectedly; the case is preserved for review.",
                500,
            ) from error

        result = await self.repository.list_case_by_id(trade_id, organization_id)
        if result is None:
            raise ServiceError(
                "trade_record_missing", "Processed trade record could not be read.", 500
            )
        return TradeResult.model_validate(dict(result))
